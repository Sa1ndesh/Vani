"""
Language Detection for Vani-Kanoon
Detects language and regional dialect from text or audio transcription.
Uses langdetect with Unicode script analysis as a fallback.
"""

import logging
import re
import unicodedata
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependencies
# ---------------------------------------------------------------------------
try:
    from langdetect import detect as _langdetect_detect
    from langdetect import detect_langs as _langdetect_detect_langs
    from langdetect import DetectorFactory
    # Deterministic results
    DetectorFactory.seed = 0
    _LANGDETECT_AVAILABLE = True
    logger.info("langdetect is available.")
except ImportError:
    _LANGDETECT_AVAILABLE = False
    logger.warning("langdetect not installed — falling back to script-based language detection.")

# ---------------------------------------------------------------------------
# Unicode script ranges (inclusive)
# ---------------------------------------------------------------------------
_SCRIPT_RANGES: List[Tuple[int, int, str]] = [
    (0x0900, 0x097F, "Devanagari"),   # Hindi, Marathi, Sanskrit
    (0x0980, 0x09FF, "Bengali"),
    (0x0A00, 0x0A7F, "Gurmukhi"),     # Punjabi
    (0x0A80, 0x0AFF, "Gujarati"),
    (0x0B00, 0x0B7F, "Oriya"),
    (0x0B80, 0x0BFF, "Tamil"),
    (0x0C00, 0x0C7F, "Telugu"),
    (0x0C80, 0x0CFF, "Kannada"),
    (0x0D00, 0x0D7F, "Malayalam"),
    (0x0E00, 0x0E7F, "Thai"),
    (0x0600, 0x06FF, "Arabic"),       # includes Urdu
    (0x0000, 0x007F, "Latin"),
]

# Script → primary language code (when langdetect is unavailable)
_SCRIPT_TO_LANGUAGE: Dict[str, str] = {
    "Devanagari": "hi",   # defaults to Hindi; Marathi needs vocab check
    "Bengali": "bn",
    "Gurmukhi": "pa",
    "Gujarati": "gu",
    "Oriya": "or",
    "Tamil": "ta",
    "Telugu": "te",
    "Kannada": "kn",
    "Malayalam": "ml",
    "Arabic": "ur",       # Urdu is written in Arabic script in South Asia
    "Latin": "en",
}

# ---------------------------------------------------------------------------
# Dialect vocabulary patterns
# ---------------------------------------------------------------------------
_DIALECT_VOCABULARY: Dict[str, Dict[str, List[str]]] = {
    "hi": {
        "braj": ["मैं", "तुम", "है", "होय", "जाय", "आय"],
        "awadhi": ["हम", "तोहार", "हउवे", "रहत", "जात"],
        "bhojpuri": ["हम", "रउरा", "बाटे", "हवे", "बानी"],
        "maithili": ["हम", "अहाँ", "छी", "केने", "गेलाह"],
        "standard_hindi": ["मैं", "आप", "है", "हैं", "करना"],
    },
    "kn": {
        "bangalore": ["enu", "yenu", "aagide", "illa", "sari", "okay"],
        "hubli": ["haange", "houdu", "hoom", "mokaddame"],
        "north_karnataka": ["hein", "naan", "avnu"],
        "coorg": ["da", "di", "ninge", "namdu"],
    },
    "mr": {
        "standard_marathi": ["मी", "तू", "आहे", "होते", "केले"],
        "varhadi": ["मी", "आस", "हाय", "बापू"],
        "khandeshi": ["म्या", "त्या", "हाये"],
        "chitpavani": ["मी", "आहे", "होतो"],
    },
    "ta": {
        "standard_tamil": ["நான்", "நீ", "அவன்", "இருக்கிறேன்"],
        "colloquial_tamil": ["நான்", "நீ", "ஆமா", "வேணும்"],
        "brahmin_tamil": ["நான்", "நீர்", "வந்தீர்"],
        "madurai": ["என்னா", "ஏய்", "டா", "டி"],
    },
    "te": {
        "standard_telugu": ["నేను", "నువ్వు", "అతడు", "ఉన్నాను"],
        "telangana": ["నేను", "ఉన్నా", "వస్తా", "కదా"],
        "andhra": ["నేను", "నీవు", "మీరు", "వస్తారు"],
    },
}

# ---------------------------------------------------------------------------
# Marathi vs Hindi disambiguation (both Devanagari)
# ---------------------------------------------------------------------------
_MARATHI_MARKERS = [
    "आहे", "होते", "केले", "मला", "तुला", "आणि", "परंतु", "कारण",
    "महाराष्ट्र", "मुंबई", "पुणे", "वकील", "न्यायालय",
]
_HINDI_MARKERS = [
    "है", "था", "किया", "मुझे", "तुम्हें", "और", "लेकिन", "क्योंकि",
    "दिल्ली", "उत्तर", "प्रदेश",
]


class LanguageDetector:
    """
    Detects language and dialect from text with confidence scoring.
    Combines langdetect (statistical) with script analysis (rule-based).
    """

    def __init__(self) -> None:
        logger.info(
            "LanguageDetector init — langdetect=%s",
            "available" if _LANGDETECT_AVAILABLE else "unavailable",
        )

    # ------------------------------------------------------------------
    # Script detection
    # ------------------------------------------------------------------

    def detect_script(self, text: str) -> str:
        """
        Identify the primary Unicode script used in the text.

        Returns one of: Devanagari, Bengali, Tamil, Telugu, Kannada,
        Malayalam, Gurmukhi, Gujarati, Arabic, Latin, or "Unknown".
        """
        if not text:
            return "Unknown"

        script_counts: Dict[str, int] = {}
        for char in text:
            cp = ord(char)
            for start, end, script_name in _SCRIPT_RANGES:
                if start <= cp <= end:
                    script_counts[script_name] = script_counts.get(script_name, 0) + 1
                    break

        if not script_counts:
            return "Unknown"

        # Exclude Latin from dominance check to prefer Indic scripts
        indic_counts = {k: v for k, v in script_counts.items() if k != "Latin"}
        dominant_pool = indic_counts if indic_counts else script_counts
        dominant_script = max(dominant_pool, key=dominant_pool.get)
        return dominant_script

    # ------------------------------------------------------------------
    # Language detection
    # ------------------------------------------------------------------

    def detect_language(self, text: str) -> Dict[str, Any]:
        """
        Detect the language of the input text.

        Returns:
            {
                "language": str,      # BCP-47 language code, e.g. "hi"
                "confidence": float,  # 0–1
                "script": str,        # Unicode script name
                "method": str,        # "langdetect" | "script" | "fallback"
                "candidates": list,   # top candidate list [{lang, prob}]
            }
        """
        if not text or not text.strip():
            return {
                "language": "unknown",
                "confidence": 0.0,
                "script": "Unknown",
                "method": "fallback",
                "candidates": [],
            }

        script = self.detect_script(text)

        # Attempt langdetect first
        if _LANGDETECT_AVAILABLE:
            lang_code, confidence, candidates = self._langdetect(text)
            if confidence >= 0.50:
                # Devanagari ambiguity: langdetect often confuses hi/mr
                if script == "Devanagari" and lang_code in ("hi", "mr"):
                    lang_code = self._disambiguate_devanagari(text)
                return {
                    "language": lang_code,
                    "confidence": confidence,
                    "script": script,
                    "method": "langdetect",
                    "candidates": candidates,
                }

        # Script-based fallback
        lang_code = _SCRIPT_TO_LANGUAGE.get(script, "en")
        if script == "Devanagari":
            lang_code = self._disambiguate_devanagari(text)

        return {
            "language": lang_code,
            "confidence": 0.70 if script != "Unknown" else 0.10,
            "script": script,
            "method": "script",
            "candidates": [{"lang": lang_code, "prob": 0.70}],
        }

    def _langdetect(
        self, text: str
    ) -> Tuple[str, float, List[Dict[str, float]]]:
        """Run langdetect and return (top_lang, confidence, candidates)."""
        try:
            langs = _langdetect_detect_langs(text)
            top = langs[0]
            candidates = [{"lang": l.lang, "prob": round(l.prob, 3)} for l in langs[:5]]
            return top.lang, round(top.prob, 3), candidates
        except Exception as exc:  # noqa: BLE001
            logger.debug("langdetect failed: %s", exc)
            return "unknown", 0.0, []

    def _disambiguate_devanagari(self, text: str) -> str:
        """
        Distinguish Hindi from Marathi (both use Devanagari script)
        by counting script-specific vocabulary markers.
        """
        mr_count = sum(1 for w in _MARATHI_MARKERS if w in text)
        hi_count = sum(1 for w in _HINDI_MARKERS if w in text)
        if mr_count > hi_count:
            return "mr"
        return "hi"

    # ------------------------------------------------------------------
    # Dialect detection
    # ------------------------------------------------------------------

    def detect_dialect(
        self, text: str, language: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Classify the regional dialect within a detected language.

        Args:
            text:     Input text.
            language: BCP-47 language code. If None, it is auto-detected.

        Returns:
            {
                "dialect": str,       # dialect label, e.g. "bhojpuri"
                "confidence": float,
                "language": str,
                "all_scores": dict,   # dialect → score
            }
        """
        if language is None:
            lang_result = self.detect_language(text)
            language = lang_result["language"]

        vocab_map = _DIALECT_VOCABULARY.get(language)
        if not vocab_map:
            return {
                "dialect": "standard",
                "confidence": 0.5,
                "language": language,
                "all_scores": {},
            }

        scores: Dict[str, int] = {}
        text_lower = text.lower()
        for dialect, markers in vocab_map.items():
            scores[dialect] = sum(1 for m in markers if m.lower() in text_lower)

        if not any(scores.values()):
            # No markers found — default to "standard_*" variant if present
            standard_key = next(
                (k for k in vocab_map if k.startswith("standard")), list(vocab_map.keys())[0]
            )
            return {
                "dialect": standard_key,
                "confidence": 0.40,
                "language": language,
                "all_scores": {k: 0 for k in vocab_map},
            }

        top_dialect = max(scores, key=scores.get)
        total = sum(scores.values()) or 1
        confidence = round(scores[top_dialect] / total, 3)

        return {
            "dialect": top_dialect,
            "confidence": confidence,
            "language": language,
            "all_scores": scores,
        }

    # ------------------------------------------------------------------
    # Preprocessing configuration
    # ------------------------------------------------------------------

    def get_preprocessing_config(
        self, language: str, dialect: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Return NLP preprocessing config for a language/dialect pair.

        The config guides text normalisation before embedding or LLM prompting.

        Returns a dict with:
            tokenizer, normalise_unicode, remove_diacritics,
            stemmer, stopword_list, transliterate, script
        """
        language_configs: Dict[str, Dict[str, Any]] = {
            "hi": {
                "tokenizer": "indic",
                "normalise_unicode": True,
                "remove_diacritics": False,
                "stemmer": "hindi_stemmer",
                "stopwords": ["है", "हैं", "था", "थे", "में", "को", "से", "के", "की", "का"],
                "transliterate": False,
                "script": "Devanagari",
                "legal_terms_normalisation": {
                    "धारा": "section",
                    "अधिनियम": "act",
                    "न्यायालय": "court",
                    "वकील": "lawyer",
                    "अपराध": "offense",
                },
            },
            "mr": {
                "tokenizer": "indic",
                "normalise_unicode": True,
                "remove_diacritics": False,
                "stemmer": None,
                "stopwords": ["आहे", "होते", "मला", "तुला", "आणि", "म्हणून", "परंतु"],
                "transliterate": False,
                "script": "Devanagari",
                "legal_terms_normalisation": {
                    "कलम": "section",
                    "कायदा": "act",
                    "न्यायालय": "court",
                    "वकील": "lawyer",
                },
            },
            "kn": {
                "tokenizer": "indic",
                "normalise_unicode": True,
                "remove_diacritics": False,
                "stemmer": None,
                "stopwords": ["ಇದೆ", "ಇಲ್ಲ", "ಮತ್ತು", "ಆದರೆ", "ಕಾರಣ"],
                "transliterate": False,
                "script": "Kannada",
                "legal_terms_normalisation": {
                    "ಸೆಕ್ಷನ್": "section",
                    "ಕಾಯ್ದೆ": "act",
                    "ನ್ಯಾಯಾಲಯ": "court",
                    "ವಕೀಲ": "lawyer",
                },
            },
            "ta": {
                "tokenizer": "indic",
                "normalise_unicode": True,
                "remove_diacritics": False,
                "stemmer": None,
                "stopwords": ["இருக்கிறேன்", "ஆமா", "இல்லை", "மற்றும்"],
                "transliterate": False,
                "script": "Tamil",
                "legal_terms_normalisation": {
                    "பிரிவு": "section",
                    "சட்டம்": "act",
                    "நீதிமன்றம்": "court",
                    "வழக்கறிஞர்": "lawyer",
                },
            },
            "te": {
                "tokenizer": "indic",
                "normalise_unicode": True,
                "remove_diacritics": False,
                "stemmer": None,
                "stopwords": ["ఉన్నాను", "లేదు", "మరియు", "కానీ", "కాబట్టి"],
                "transliterate": False,
                "script": "Telugu",
                "legal_terms_normalisation": {
                    "సెక్షన్": "section",
                    "చట్టం": "act",
                    "న్యాయస్థానం": "court",
                    "న్యాయవాది": "lawyer",
                },
            },
            "en": {
                "tokenizer": "whitespace",
                "normalise_unicode": False,
                "remove_diacritics": False,
                "stemmer": "porter",
                "stopwords": ["the", "a", "an", "is", "are", "was", "were", "in", "on", "at"],
                "transliterate": False,
                "script": "Latin",
                "legal_terms_normalisation": {},
            },
        }

        config = language_configs.get(language, language_configs["en"]).copy()

        # Dialect-specific overrides
        if dialect and language == "hi":
            if dialect == "bhojpuri":
                config["stopwords"] = config["stopwords"] + ["हम", "रउरा", "बाटे", "हवे"]
            elif dialect == "awadhi":
                config["stopwords"] = config["stopwords"] + ["हम", "तोहार", "हउवे"]
        if dialect and language == "kn":
            if dialect == "bangalore":
                # Bangalore Kannada has heavy English code-switching
                config["transliterate"] = True

        config["dialect"] = dialect or "standard"
        return config

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def batch_detect(self, texts: List[str]) -> List[Dict[str, Any]]:
        """Detect language for each text in a list."""
        return [self.detect_language(t) for t in texts]

    def is_indic_script(self, text: str) -> bool:
        """Return True if the text contains primarily Indic script characters."""
        script = self.detect_script(text)
        indic_scripts = {"Devanagari", "Bengali", "Tamil", "Telugu", "Kannada",
                         "Malayalam", "Gurmukhi", "Gujarati", "Oriya"}
        return script in indic_scripts
