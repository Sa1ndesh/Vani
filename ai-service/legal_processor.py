"""
Legal query processor for Vani-Kanoon.
Classifies queries, extracts keywords, normalises text, and maps IPC→BNS.
"""
import json
import os
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# ---------------------------------------------------------------------------
# Static keyword taxonomy
# ---------------------------------------------------------------------------
QUERY_TYPE_KEYWORDS = {
    "criminal": [
        "murder", "theft", "rape", "assault", "robbery", "dacoity", "cheating",
        "fraud", "FIR", "arrest", "police", "bail", "homicide", "forgery",
        "kidnap", "extortion", "intimidation", "IPC", "BNS", "crime", "offense",
        "offence", "चोरी", "हत्या", "धोखा", "गिरफ्तारी", "ಕೊಲೆ", "ಕಳ್ಳತನ",
        "திருட்டு", "కొలే", "गुन्हा", "defamation", "dowry",
    ],
    "civil": [
        "tenant", "landlord", "rent", "eviction", "tenancy", "lease", "deposit",
        "किराया", "किरायेदार", "बाडिगेदार", "consumer", "dispute", "contract",
        "agreement", "compensation", "damages", "court", "suit",
    ],
    "property": [
        "property", "land", "sale deed", "registration", "RERA", "builder",
        "plot", "flat", "apartment", "mortgage", "title", "ownership",
        "stamp duty", "transfer", "gift deed", "संपत्ति", "ज़मीन", "ಆಸ್ತಿ",
        "சொத்து", "ఆస్తి", "मालमत्ता",
    ],
    "family": [
        "divorce", "marriage", "dowry", "custody", "alimony", "maintenance",
        "inheritance", "succession", "will", "तलाक", "विवाह", "विरासत",
        "विच्छेद", "ವಿಚ್ಛೇದನ", "விவாகரத்து", "విడాకులు", "घटस्फोट",
        "domestic violence", "cruelty", "498A",
    ],
}

# IPC → BNS mapping (key = old IPC section number)
IPC_TO_BNS_MAP = {
    "IPC 299": "BNS 101",
    "IPC 300": "BNS 103",
    "IPC 302": "BNS 103",
    "IPC 304": "BNS 105",
    "IPC 304A": "BNS 106",
    "IPC 304B": "BNS 80",
    "IPC 307": "BNS 109",
    "IPC 319": "BNS 114",
    "IPC 320": "BNS 114",
    "IPC 323": "BNS 115",
    "IPC 324": "BNS 117",
    "IPC 325": "BNS 116",
    "IPC 354": "BNS 74",
    "IPC 354A": "BNS 66",
    "IPC 354B": "BNS 75",
    "IPC 354C": "BNS 77",
    "IPC 354D": "BNS 78",
    "IPC 375": "BNS 63",
    "IPC 376": "BNS 64",
    "IPC 378": "BNS 303",
    "IPC 379": "BNS 304",
    "IPC 380": "BNS 305",
    "IPC 381": "BNS 306",
    "IPC 383": "BNS 308",
    "IPC 384": "BNS 308",
    "IPC 387": "BNS 309",
    "IPC 390": "BNS 310",
    "IPC 392": "BNS 310",
    "IPC 395": "BNS 311",
    "IPC 403": "BNS 317",
    "IPC 405": "BNS 316",
    "IPC 406": "BNS 316",
    "IPC 415": "BNS 318",
    "IPC 420": "BNS 318",
    "IPC 425": "BNS 324",
    "IPC 441": "BNS 329",
    "IPC 447": "BNS 330",
    "IPC 448": "BNS 331",
    "IPC 463": "BNS 336",
    "IPC 465": "BNS 336",
    "IPC 468": "BNS 339",
    "IPC 494": "BNS 82",
    "IPC 498A": "BNS 85",
    "IPC 499": "BNS 356",
    "IPC 500": "BNS 357",
    "IPC 503": "BNS 351",
    "IPC 506": "BNS 351",
    "IPC 509": "BNS 79",
}

APPLICABLE_LAWS = {
    "criminal": ["Indian Penal Code 1860", "Bharatiya Nyaya Sanhita 2023",
                 "Code of Criminal Procedure 1973", "Bharatiya Nagarik Suraksha Sanhita 2023"],
    "civil":    ["Civil Procedure Code 1908", "Specific Relief Act 1963",
                 "Limitation Act 1963", "Indian Contract Act 1872"],
    "property": ["Transfer of Property Act 1882", "Registration Act 1908",
                 "Indian Stamp Act 1899", "RERA 2016", "Land Acquisition Act 2013"],
    "family":   ["Hindu Marriage Act 1955", "Special Marriage Act 1954",
                 "Hindu Succession Act 1956", "Muslim Personal Law",
                 "Protection of Women from Domestic Violence Act 2005"],
    "general":  ["Constitution of India", "Legal Services Authorities Act 1987"],
}


class LegalProcessor:
    def __init__(self):
        self._state_data: dict = {}
        self._load_state_data()

    def _load_state_data(self) -> None:
        path = os.path.join(DATA_DIR, "state_laws.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._state_data = json.load(f).get("states", {})
        except Exception as e:
            logger.error("Failed to load state_laws.json: %s", e)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def process_query(
        self, query: str, language: str, state: Optional[str] = None
    ) -> dict:
        """
        Analyse *query* and return structured metadata.
        Returns {
            "normalized_query": str,
            "query_type": "criminal|civil|property|family|general",
            "relevant_acts": [...],
            "jurisdiction": "state|central",
            "keywords": [...],
        }
        """
        normalized = self.normalize_query(query, language)
        keywords = self.extract_legal_keywords(normalized)
        query_type = self.classify_query_type(normalized, keywords)
        relevant_acts = self.get_applicable_laws(query_type, state)
        jurisdiction = "state" if query_type in ("civil", "property") and state else "central"

        return {
            "normalized_query": normalized,
            "query_type": query_type,
            "relevant_acts": relevant_acts,
            "jurisdiction": jurisdiction,
            "keywords": keywords,
        }

    # ------------------------------------------------------------------
    # Keyword extraction
    # ------------------------------------------------------------------

    def extract_legal_keywords(self, text: str) -> list[str]:
        """Return a deduplicated list of legal keywords found in *text*."""
        text_lower = text.lower()
        found = []
        for category, terms in QUERY_TYPE_KEYWORDS.items():
            for term in terms:
                if term.lower() in text_lower and term not in found:
                    found.append(term)
        # Also extract any IPC/BNS section references
        ipc_refs = re.findall(r"(?:IPC|BNS|Section|Sec\.?)\s*\d+[A-Z]?", text, re.IGNORECASE)
        found.extend(ipc_refs)
        return list(dict.fromkeys(found))  # preserve order, remove dupes

    # ------------------------------------------------------------------
    # Query classification
    # ------------------------------------------------------------------

    def classify_query_type(self, text: str, keywords: list[str]) -> str:
        """Return the dominant query type for the given *text* and *keywords*."""
        scores: dict[str, int] = {t: 0 for t in QUERY_TYPE_KEYWORDS}
        combined = text.lower() + " " + " ".join(k.lower() for k in keywords)
        for qtype, terms in QUERY_TYPE_KEYWORDS.items():
            for term in terms:
                if term.lower() in combined:
                    scores[qtype] += 1
        best_type = max(scores, key=scores.get)
        if scores[best_type] == 0:
            return "general"
        return best_type

    # ------------------------------------------------------------------
    # Query normalisation
    # ------------------------------------------------------------------

    def normalize_query(self, text: str, language: str) -> str:
        """Clean up and lightly normalize *text*. Does not translate."""
        text = re.sub(r"\s+", " ", text).strip()
        # Normalize common Indic legal abbreviations to English equivalents
        replacements = {
            "FIR": "First Information Report (FIR)",
            "PIL": "Public Interest Litigation (PIL)",
        }
        for abbr, full in replacements.items():
            text = re.sub(r"\b" + abbr + r"\b", full, text, flags=re.IGNORECASE)
        return text

    # ------------------------------------------------------------------
    # Applicable laws
    # ------------------------------------------------------------------

    def get_applicable_laws(
        self, query_type: str, state: Optional[str] = None
    ) -> list[str]:
        """Return the relevant acts for *query_type*, adding state acts where available."""
        laws = list(APPLICABLE_LAWS.get(query_type, APPLICABLE_LAWS["general"]))
        if state and state in self._state_data:
            state_info = self._state_data[state]
            laws.extend(state_info.get("key_acts", [])[:3])
        return laws

    # ------------------------------------------------------------------
    # IPC → BNS mapping
    # ------------------------------------------------------------------

    def map_ipc_to_bns(self, ipc_section: str) -> str:
        """Return the BNS equivalent of an IPC section, or the original if unknown."""
        # Normalise input: "302", "IPC302", "IPC 302" → "IPC 302"
        normalized = re.sub(r"[^\d]", "", ipc_section)
        key = f"IPC {normalized}"
        return IPC_TO_BNS_MAP.get(key, ipc_section)
