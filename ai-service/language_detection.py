"""
Language Detection Service for Indian Languages
Detects language and regional dialect from text input
"""
import re
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

SCRIPT_RANGES = {
    "devanagari": (0x0900, 0x097F),
    "kannada": (0x0C80, 0x0CFF),
    "tamil": (0x0B80, 0x0BFF),
    "telugu": (0x0C00, 0x0C7F),
    "gujarati": (0x0A80, 0x0AFF),
    "bengali": (0x0980, 0x09FF),
    "gurmukhi": (0x0A00, 0x0A7F),
    "malayalam": (0x0D00, 0x0D7F),
    "odia": (0x0B00, 0x0B7F),
}

DIALECT_MARKERS = {
    "hindi": {
        "bhojpuri": ["हम", "रहल", "बानी", "कहत", "भइल", "हउ"],
        "awadhi": ["अहै", "हौ", "तोहार", "मोहे", "जाऊं", "काहे"],
        "braj": ["ब्रज", "कह्यो", "गयो", "सखी", "मोहन"],
        "haryanvi": ["घणा", "भाई", "थारो", "म्हारो", "सा"],
        "standard": [],
    },
    "marathi": {
        "mumbai": ["काय", "मला", "तुम्हाला", "आहे", "कुठे"],
        "nagpuri": ["हाय", "काय करतो", "बघ"],
        "standard": [],
    },
}


class LanguageDetector:
    def __init__(self):
        self.langdetect_available = False
        self._detect = None
        self._detect_langs = None
        self._try_load_langdetect()

    def _try_load_langdetect(self):
        try:
            from langdetect import detect, detect_langs
            self._detect = detect
            self._detect_langs = detect_langs
            self.langdetect_available = True
        except ImportError:
            logger.warning("langdetect not available, using script-based detection")

    def detect_script(self, text: str) -> Optional[str]:
        """Detect script/language from Unicode ranges"""
        counts = {lang: 0 for lang in SCRIPT_RANGES}
        for char in text:
            cp = ord(char)
            for lang, (start, end) in SCRIPT_RANGES.items():
                if start <= cp <= end:
                    counts[lang] += 1

        max_lang = max(counts, key=counts.get)
        if counts[max_lang] > 0:
            script_to_lang = {
                "devanagari": "hindi",
                "kannada": "kannada",
                "tamil": "tamil",
                "telugu": "telugu",
                "gujarati": "gujarati",
                "bengali": "bengali",
                "gurmukhi": "punjabi",
                "malayalam": "malayalam",
                "odia": "odia",
            }
            detected = script_to_lang.get(max_lang, max_lang)
            if detected == "hindi":
                detected = self._distinguish_hindi_marathi(text)
            return detected
        return "english"

    def _distinguish_hindi_marathi(self, text: str) -> str:
        """Distinguish between Hindi and Marathi (both use Devanagari)"""
        marathi_markers = ["आहे", "नाही", "आणि", "किंवा", "ते", "ही", "त्यांनी", "मराठी"]
        hindi_markers = ["है", "नहीं", "और", "या", "वे", "यह", "उन्होंने", "हिंदी"]
        marathi_score = sum(1 for m in marathi_markers if m in text)
        hindi_score = sum(1 for m in hindi_markers if m in text)
        return "marathi" if marathi_score > hindi_score else "hindi"

    def detect_dialect(self, text: str, language: str) -> Tuple[str, float]:
        """Detect regional dialect within a language"""
        if language not in DIALECT_MARKERS:
            return "standard", 1.0
        dialects = DIALECT_MARKERS[language]
        scores = {}
        for dialect, markers in dialects.items():
            if not markers:
                continue
            score = sum(1 for m in markers if m in text)
            scores[dialect] = score
        if scores and max(scores.values()) > 0:
            best_dialect = max(scores, key=scores.get)
            total = sum(scores.values())
            confidence = scores[best_dialect] / total if total > 0 else 0
            return best_dialect, confidence
        return "standard", 1.0

    def detect(self, text: str) -> Dict:
        """Full language and dialect detection"""
        if not text or not text.strip():
            return {"language": "english", "dialect": "standard", "confidence": 0.0, "script": "latin"}

        script_lang = self.detect_script(text)

        if script_lang == "english" and self.langdetect_available:
            try:
                langs = self._detect_langs(text)
                if langs:
                    top = langs[0]
                    lang_map = {
                        "hi": "hindi", "kn": "kannada", "mr": "marathi",
                        "ta": "tamil", "te": "telugu", "gu": "gujarati",
                        "bn": "bengali", "pa": "punjabi", "en": "english",
                        "ml": "malayalam",
                    }
                    script_lang = lang_map.get(str(top.lang), "english")
            except Exception:
                pass

        dialect, dialect_confidence = self.detect_dialect(text, script_lang)

        script_map = {
            "hindi": "devanagari", "marathi": "devanagari",
            "kannada": "kannada", "tamil": "tamil", "telugu": "telugu",
            "gujarati": "gujarati", "bengali": "bengali",
            "punjabi": "gurmukhi", "malayalam": "malayalam",
            "english": "latin",
        }

        return {
            "language": script_lang,
            "dialect": dialect,
            "confidence": dialect_confidence,
            "script": script_map.get(script_lang, "latin"),
        }


_detector = None


def get_language_detector() -> LanguageDetector:
    global _detector
    if _detector is None:
        _detector = LanguageDetector()
    return _detector
