"""
Language and dialect detection for Vani-Kanoon.
Uses langdetect + Unicode script range heuristics + dialect vocabulary patterns.
"""
import json
import os
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

try:
    from langdetect import detect, detect_langs, LangDetectException
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False
    logger.warning("langdetect not available; using script-range heuristics only.")


# Unicode script ranges for Indic scripts
SCRIPT_RANGES = {
    "Devanagari": (0x0900, 0x097F),   # Hindi, Marathi, Sanskrit
    "Kannada":    (0x0C80, 0x0CFF),
    "Tamil":      (0x0B80, 0x0BFF),
    "Telugu":     (0x0C00, 0x0C7F),
    "Malayalam":  (0x0D00, 0x0D7F),
    "Gujarati":   (0x0A80, 0x0AFF),
    "Gurmukhi":   (0x0A00, 0x0A7F),  # Punjabi
    "Bengali":    (0x0980, 0x09FF),
    "Odia":       (0x0B00, 0x0B7F),
    "Latin":      (0x0041, 0x007A),
}

# langdetect code → friendly name
LANG_CODE_MAP = {
    "hi": "Hindi",
    "kn": "Kannada",
    "mr": "Marathi",
    "ta": "Tamil",
    "te": "Telugu",
    "en": "English",
    "gu": "Gujarati",
    "pa": "Punjabi",
    "bn": "Bengali",
    "ml": "Malayalam",
}

# Script → most likely language
SCRIPT_TO_LANG = {
    "Kannada":    "Kannada",
    "Tamil":      "Tamil",
    "Telugu":     "Telugu",
    "Malayalam":  "Malayalam",
    "Gujarati":   "Gujarati",
    "Gurmukhi":   "Punjabi",
    "Bengali":    "Bengali",
    "Odia":       "Odia",
    # Devanagari is shared by Hindi & Marathi; resolved below
}


class LanguageDetector:
    def __init__(self):
        self._dialect_data: dict = {}
        self._load_dialect_data()

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_dialect_data(self) -> None:
        path = os.path.join(DATA_DIR, "dialect_mapping.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._dialect_data = data.get("languages", {})
        except Exception as e:
            logger.error("Failed to load dialect_mapping.json: %s", e)
            self._dialect_data = {}

    # ------------------------------------------------------------------
    # Script detection
    # ------------------------------------------------------------------

    def get_script_type(self, text: str) -> str:
        """Return the dominant Unicode script used in *text*."""
        counts: dict[str, int] = {s: 0 for s in SCRIPT_RANGES}
        for ch in text:
            cp = ord(ch)
            for script, (lo, hi) in SCRIPT_RANGES.items():
                if lo <= cp <= hi:
                    counts[script] += 1
                    break
        dominant = max(counts, key=counts.get)
        if counts[dominant] == 0:
            return "Latin"
        return dominant

    # ------------------------------------------------------------------
    # Language detection
    # ------------------------------------------------------------------

    def detect_language(self, text: str) -> dict:
        """
        Detect the language of *text*.
        Returns {"language": "Kannada", "script": "Kannada", "confidence": 0.95}
        """
        text = self.preprocess_text(text)
        if not text.strip():
            return {"language": "English", "script": "Latin", "confidence": 0.5}

        script = self.get_script_type(text)

        # For unambiguous scripts, no need for langdetect
        if script in SCRIPT_TO_LANG:
            lang = SCRIPT_TO_LANG[script]
            return {"language": lang, "script": script, "confidence": 0.95}

        # Devanagari: distinguish Hindi vs Marathi
        if script == "Devanagari":
            lang, conf = self._distinguish_devanagari(text)
            return {"language": lang, "script": script, "confidence": conf}

        # Latin script → use langdetect
        if LANGDETECT_AVAILABLE:
            try:
                langs = detect_langs(text)
                top = langs[0]
                lang_name = LANG_CODE_MAP.get(str(top.lang), "English")
                return {
                    "language": lang_name,
                    "script": "Latin",
                    "confidence": round(float(top.prob), 2),
                }
            except LangDetectException:
                pass

        return {"language": "English", "script": "Latin", "confidence": 0.5}

    def _distinguish_devanagari(self, text: str) -> tuple[str, float]:
        """
        Heuristic to tell Hindi from Marathi using distinctive vocabulary.
        """
        marathi_markers = ["आहे", "नाही", "मला", "तुम्ही", "करतो", "सांगा", "होय", "झाले", "माझे", "आपले"]
        hindi_markers = ["है", "नहीं", "मुझे", "आप", "करता", "बताओ", "हाँ", "हुआ", "मेरा", "आपका"]
        marathi_score = sum(1 for w in marathi_markers if w in text)
        hindi_score = sum(1 for w in hindi_markers if w in text)
        if marathi_score > hindi_score:
            return "Marathi", min(0.5 + 0.1 * marathi_score, 0.95)
        if hindi_score > marathi_score:
            return "Hindi", min(0.5 + 0.1 * hindi_score, 0.95)

        # Fall back to langdetect if available
        if LANGDETECT_AVAILABLE:
            try:
                code = detect(text)
                lang = LANG_CODE_MAP.get(code, "Hindi")
                return lang, 0.7
            except Exception:
                pass
        return "Hindi", 0.6

    # ------------------------------------------------------------------
    # Dialect detection
    # ------------------------------------------------------------------

    def detect_dialect(self, text: str, language: str) -> dict:
        """
        Detect the dialect of *text* for a given *language*.
        Returns {"dialect": "Hubli Kannada", "region": "North Karnataka", "confidence": 0.85}
        """
        lang_data = self._dialect_data.get(language)
        if not lang_data:
            return {"dialect": f"Standard {language}", "region": "General", "confidence": 0.5}

        dialects = lang_data.get("dialects", [])
        if not dialects:
            return {"dialect": f"Standard {language}", "region": "General", "confidence": 0.5}

        best_dialect = None
        best_score = 0

        for d in dialects:
            keywords = d.get("keywords", [])
            score = sum(1 for kw in keywords if kw.lower() in text.lower())
            # Also check sample phrases
            for phrase in d.get("sample_phrases", []):
                if any(word in text for word in phrase.split()):
                    score += 0.5
            if score > best_score:
                best_score = score
                best_dialect = d

        if best_dialect and best_score > 0:
            conf = min(0.5 + 0.1 * best_score, 0.95)
            return {
                "dialect": best_dialect["name"],
                "region": best_dialect.get("region", ""),
                "confidence": round(conf, 2),
                "tone": best_dialect.get("tone", ""),
            }

        # Default to first dialect
        default = dialects[0]
        return {
            "dialect": default["name"],
            "region": default.get("region", ""),
            "confidence": 0.5,
            "tone": default.get("tone", ""),
        }

    # ------------------------------------------------------------------
    # Text preprocessing
    # ------------------------------------------------------------------

    def preprocess_text(self, text: str) -> str:
        """Basic text normalization: strip excess whitespace, remove URLs."""
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text
