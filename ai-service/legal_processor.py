"""
Legal Query Processor for Vani-Kanoon
Normalises and processes legal queries to improve RAG search accuracy.
Handles keyword extraction, query expansion, entity extraction, and intent classification.
"""

import logging
import re
from typing import Dict, List, Optional, Any, Set

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Legal keyword dictionaries
# ---------------------------------------------------------------------------

# IPC / BNS section numbers and their common descriptions
_IPC_SECTIONS: Dict[str, str] = {
    "302": "murder",
    "307": "attempt to murder",
    "304": "culpable homicide",
    "304b": "dowry death",
    "306": "abetment of suicide",
    "354": "assault on woman",
    "354a": "sexual harassment",
    "375": "rape",
    "376": "rape punishment",
    "420": "cheating",
    "406": "criminal breach of trust",
    "498a": "cruelty by husband",
    "406": "breach of trust",
    "379": "theft",
    "380": "theft in dwelling",
    "384": "extortion",
    "395": "dacoity",
    "300": "murder definition",
    "34": "common intention",
    "120b": "criminal conspiracy",
    "147": "rioting",
    "186": "obstructing public servant",
    "294": "obscene acts",
    "323": "voluntarily causing hurt",
    "325": "grievous hurt",
    "326": "hurt by dangerous weapons",
    "363": "kidnapping",
    "364": "kidnapping for ransom",
    "366": "abduction of woman",
    "392": "robbery",
    "396": "dacoity with murder",
    "427": "mischief",
    "447": "criminal trespass",
    "448": "house trespass",
    "465": "forgery",
    "468": "forgery for cheating",
    "500": "defamation",
    "503": "criminal intimidation",
    "509": "outraging modesty",
}

# BNS (Bharatiya Nyaya Sanhita 2023) sections
_BNS_SECTIONS: Dict[str, str] = {
    "101": "murder",
    "103": "murder punishment",
    "109": "attempt to murder",
    "105": "culpable homicide",
    "80": "sexual harassment",
    "63": "rape",
    "64": "rape punishment",
    "316": "cheating",
    "318": "cheating",
    "85": "cruelty by husband",
    "303": "theft",
    "310": "robbery",
    "111": "organised crime",
}

# Common legal terms and their synonyms
_LEGAL_SYNONYMS: Dict[str, List[str]] = {
    "murder": ["murder", "302", "103", "homicide", "killing", "death", "culpable homicide"],
    "rape": ["rape", "375", "376", "63", "64", "sexual assault", "sexual offence"],
    "theft": ["theft", "379", "303", "stealing", "robbery", "dacoity", "larceny"],
    "assault": ["assault", "323", "325", "hurt", "beating", "attack", "battery"],
    "fraud": ["fraud", "420", "cheating", "316", "forgery", "misrepresentation", "deception"],
    "harassment": ["harassment", "354a", "80", "molestation", "intimidation", "stalking"],
    "domestic violence": ["domestic violence", "498a", "85", "cruelty", "dowry", "dowry death"],
    "bail": ["bail", "anticipatory bail", "regular bail", "pre-arrest bail", "section 436", "section 437"],
    "fir": ["fir", "first information report", "complaint", "police complaint"],
    "arrest": ["arrest", "custody", "detention", "remand", "police custody", "judicial custody"],
    "divorce": ["divorce", "dissolution", "separation", "matrimonial", "talaq", "khula"],
    "property": ["property", "land", "plot", "real estate", "immovable property", "title deed"],
    "tenancy": ["tenancy", "rent", "tenant", "landlord", "eviction", "lease"],
    "kidnapping": ["kidnapping", "363", "364", "abduction", "missing person"],
    "cyber crime": ["cyber crime", "it act", "section 66", "hacking", "phishing", "online fraud"],
    "consumer": ["consumer", "consumer court", "product defect", "consumer forum", "complaint"],
    "corruption": ["corruption", "bribery", "pc act", "prevention of corruption", "public servant"],
    "right to information": ["rti", "right to information", "information act", "transparency"],
}

# Intent patterns — (pattern, intent_label)
_INTENT_PATTERNS = [
    (r"\b(what is|define|explain|meaning|tell me about|describe)\b", "seeking_information"),
    (r"\b(help|assist|need help|please help|guide|advice|advise|suggest)\b", "seeking_help"),
    (r"\b(how to|procedure|process|steps|file|apply|submit)\b", "seeking_procedure"),
    (r"\b(been|got|suffered|victim|attacked|cheated|harassed|abused|they did)\b", "reporting_incident"),
    (r"\b(punish|punishment|sentence|penalty|jail|imprisonment|fine)\b", "seeking_punishment_info"),
    (r"\b(can i|am i allowed|is it legal|illegal|lawful|right to|allowed to)\b", "seeking_legality"),
    (r"\b(fir|complaint|police|report|register)\b", "reporting_incident"),
    (r"\b(bail|arrested|custody|remand|in jail)\b", "seeking_bail_info"),
    (r"\b(court|hearing|case|lawsuit|file case|legal action)\b", "seeking_court_procedure"),
    (r"\b(lawyer|advocate|legal aid|free legal|attorney)\b", "seeking_legal_representation"),
]

# Act name patterns for entity extraction
_ACT_PATTERNS = [
    r"indian penal code",
    r"i\.?p\.?c\.?",
    r"bharatiya nyaya sanhita",
    r"b\.?n\.?s\.?",
    r"code of criminal procedure",
    r"cr\.?p\.?c\.?",
    r"code of civil procedure",
    r"c\.?p\.?c\.?",
    r"protection of women from domestic violence",
    r"p\.?c\.?m\.?a\.?",
    r"dowry prohibition act",
    r"pocso",
    r"prevention of children from sexual offences",
    r"information technology act",
    r"i\.?t\.? act",
    r"consumer protection act",
    r"right to information act",
    r"r\.?t\.?i\.?",
    r"motor vehicles act",
    r"evidence act",
    r"contract act",
    r"transfer of property act",
    r"hindu marriage act",
    r"special marriage act",
    r"muslim personal law",
    r"negotiable instruments act",
    r"prevention of corruption act",
    r"p\.?c\.? act",
    r"scheduled castes and scheduled tribes",
    r"s\.?c\.?\/s\.?t\.? act",
    r"atrocities act",
    r"narcotic drugs.*act",
    r"ndps",
    r"forest act",
    r"arms act",
    r"explosives act",
    r"passport act",
]

# Filler / stop words to strip during normalisation
_FILLER_WORDS = {
    "please", "kindly", "can you", "could you", "would you", "hello", "hi",
    "hey", "thanks", "thank you", "sorry", "excuse me", "sir", "madam",
    "dear", "respected", "actually", "basically", "honestly", "so",
}

# Section reference patterns
_SECTION_REF_PATTERNS = [
    r"section(?:s)?\s+(\d+[A-Za-z]*(?:\s*,\s*\d+[A-Za-z]*)*)",
    r"sec\.?\s*(\d+[A-Za-z]*)",
    r"s\.?\s*(\d+[A-Za-z]*)",
    r"(?:ipc|bns|crpc|cpc)\s+(\d+[A-Za-z]*)",
    r"\b(302|376|498a|354|420|406|304b|307|392|395|363|465|500|120b|147)\b",
]


class LegalQueryProcessor:
    """
    Pre-processes legal queries for improved RAG retrieval and LLM prompting.

    Pipeline:
        1. Normalise text (case, whitespace, filler words)
        2. Detect language
        3. Extract entities (section numbers, act names)
        4. Expand query with legal synonyms
        5. Classify intent
    """

    def __init__(self) -> None:
        logger.info("LegalQueryProcessor initialised.")

    # ------------------------------------------------------------------
    # Main processing pipeline
    # ------------------------------------------------------------------

    def process_query(
        self,
        query: str,
        language: str = "en",
    ) -> Dict[str, Any]:
        """
        Full processing pipeline for a raw user query.

        Args:
            query:    Raw user input text.
            language: Language code hint (e.g. "hi", "en", "kn").

        Returns:
            {
                "original_query": str,
                "normalised_query": str,
                "expanded_query": str,
                "keywords": List[str],
                "entities": Dict,
                "intent": str,
                "language": str,
            }
        """
        if not query or not query.strip():
            return {
                "original_query": query,
                "normalised_query": "",
                "expanded_query": "",
                "keywords": [],
                "entities": {},
                "intent": "unknown",
                "language": language,
            }

        normalised = self._normalise(query)
        keywords = self.extract_keywords(normalised)
        entities = self.extract_entities(normalised)
        expanded = self.expand_query(normalised)
        intent = self.classify_intent(normalised)

        return {
            "original_query": query,
            "normalised_query": normalised,
            "expanded_query": expanded,
            "keywords": keywords,
            "entities": entities,
            "intent": intent,
            "language": language,
        }

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------

    def _normalise(self, text: str) -> str:
        """
        Lowercase, strip filler words, collapse whitespace, and
        standardise common abbreviations.
        """
        text = text.strip()
        # Standardise common legal abbreviations
        text = re.sub(r"\bipc\b", "Indian Penal Code", text, flags=re.IGNORECASE)
        text = re.sub(r"\bbns\b", "Bharatiya Nyaya Sanhita", text, flags=re.IGNORECASE)
        text = re.sub(r"\bcrpc\b", "Code of Criminal Procedure", text, flags=re.IGNORECASE)
        text = re.sub(r"\bfir\b", "First Information Report", text, flags=re.IGNORECASE)
        text = re.sub(r"\bsc/st\b", "Scheduled Castes Scheduled Tribes", text, flags=re.IGNORECASE)
        # Collapse multiple spaces
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def remove_filler_words(self, text: str) -> str:
        """Remove common filler/politeness words from the query."""
        words = text.split()
        cleaned = [w for w in words if w.lower() not in _FILLER_WORDS]
        return " ".join(cleaned)

    def normalize_section_reference(self, text: str) -> str:
        """
        Normalise textual section references to bare numbers.

        Examples:
            "Section 302 IPC"  →  "302"
            "sec 498A"         →  "498A"
        """
        for pattern in _SECTION_REF_PATTERNS[:2]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip().upper()
        return text.strip()

    # ------------------------------------------------------------------
    # Keyword extraction
    # ------------------------------------------------------------------

    def extract_keywords(self, text: str) -> List[str]:
        """
        Extract legally relevant keywords from normalised text.

        Returns deduplicated list sorted by importance (legal terms first).
        """
        text_lower = text.lower()
        keywords: Set[str] = set()

        # 1. Direct match against known legal synonyms
        for canonical, synonyms in _LEGAL_SYNONYMS.items():
            for syn in synonyms:
                if syn in text_lower:
                    keywords.add(canonical)
                    break

        # 2. Section numbers
        for pattern in _SECTION_REF_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                sec = match.group(1).strip().lower()
                keywords.add(f"section_{sec}")

        # 3. Act names
        for act_pattern in _ACT_PATTERNS:
            if re.search(act_pattern, text_lower):
                act_keyword = re.sub(r"[^a-z0-9 ]", "", act_pattern).strip()
                keywords.add(act_keyword)

        # 4. Long nouns from the text (simple heuristic for domain terms)
        words = re.findall(r"\b[a-zA-Z]{4,}\b", text)
        legal_nouns = {
            w.lower() for w in words
            if w.lower() in {
                "murder", "theft", "rape", "fraud", "assault", "kidnapping",
                "bail", "arrest", "divorce", "property", "tenant", "landlord",
                "court", "judge", "lawyer", "police", "complaint", "victim",
                "accused", "witness", "evidence", "sentence", "appeal",
                "injunction", "custody", "alimony", "maintenance", "inheritance",
                "will", "partition", "contempt", "perjury", "extortion",
                "bribery", "corruption", "trespass", "nuisance", "defamation",
                "contract", "agreement", "breach", "damages", "compensation",
                "negligence", "consumer", "harassment", "stalking", "trafficking",
            }
        }
        keywords.update(legal_nouns)

        return sorted(keywords)

    # ------------------------------------------------------------------
    # Query expansion
    # ------------------------------------------------------------------

    def expand_query(self, query: str) -> str:
        """
        Expand a query with legally related synonyms and section numbers.

        Example:
            "What is the punishment for murder?"
            → "What is the punishment for murder homicide 302 103 culpable homicide?"
        """
        query_lower = query.lower()
        expansion_terms: Set[str] = set()

        for canonical, synonyms in _LEGAL_SYNONYMS.items():
            if canonical in query_lower or any(s in query_lower for s in synonyms):
                expansion_terms.update(synonyms)

        # Remove terms already present in the query
        new_terms = [t for t in expansion_terms if t.lower() not in query_lower]
        if not new_terms:
            return query
        expansion_str = " ".join(sorted(set(new_terms)))
        return f"{query} {expansion_str}"

    # ------------------------------------------------------------------
    # Entity extraction
    # ------------------------------------------------------------------

    def extract_entities(self, text: str) -> Dict[str, Any]:
        """
        Extract structured entities from the text.

        Returns:
            {
                "section_numbers": List[str],
                "act_names": List[str],
                "offense_types": List[str],
                "raw_section_refs": List[str],
            }
        """
        entities: Dict[str, Any] = {
            "section_numbers": [],
            "act_names": [],
            "offense_types": [],
            "raw_section_refs": [],
        }
        text_lower = text.lower()

        # Section numbers
        seen_sections: Set[str] = set()
        for pattern in _SECTION_REF_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                raw_ref = match.group(0).strip()
                sec_num = match.group(1).strip().upper()
                if sec_num not in seen_sections:
                    seen_sections.add(sec_num)
                    entities["section_numbers"].append(sec_num)
                    entities["raw_section_refs"].append(raw_ref)

        # Act names
        for act_pattern in _ACT_PATTERNS:
            matches = re.findall(act_pattern, text_lower)
            if matches:
                canonical = re.sub(r"[^a-z0-9 /.]", " ", act_pattern).strip()
                entities["act_names"].append(canonical)
        entities["act_names"] = list(dict.fromkeys(entities["act_names"]))  # deduplicate

        # Offense types from synonyms
        for canonical, synonyms in _LEGAL_SYNONYMS.items():
            if any(s in text_lower for s in synonyms):
                entities["offense_types"].append(canonical)

        return entities

    # ------------------------------------------------------------------
    # Intent classification
    # ------------------------------------------------------------------

    def classify_intent(self, query: str) -> str:
        """
        Classify the user's intent from their query.

        Returns one of:
            seeking_information | seeking_help | seeking_procedure |
            reporting_incident  | seeking_punishment_info | seeking_legality |
            seeking_bail_info   | seeking_court_procedure |
            seeking_legal_representation | unknown
        """
        query_lower = query.lower()
        scores: Dict[str, int] = {}

        for pattern, intent_label in _INTENT_PATTERNS:
            if re.search(pattern, query_lower):
                scores[intent_label] = scores.get(intent_label, 0) + 1

        if not scores:
            return "unknown"

        return max(scores, key=scores.get)

    # ------------------------------------------------------------------
    # Section reference normalisation
    # ------------------------------------------------------------------

    def get_sections_from_query(self, query: str) -> List[Dict[str, str]]:
        """
        Extract all section references from a query and annotate them with
        known descriptions.

        Returns list of {section, description, act_hint}.
        """
        entities = self.extract_entities(query)
        results = []
        for sec_num in entities["section_numbers"]:
            sec_key = sec_num.lower()
            description = (
                _IPC_SECTIONS.get(sec_key)
                or _BNS_SECTIONS.get(sec_key)
                or "unknown"
            )
            act_hint = "BNS" if sec_key in _BNS_SECTIONS else ("IPC" if sec_key in _IPC_SECTIONS else "unknown")
            results.append(
                {
                    "section": sec_num,
                    "description": description,
                    "act_hint": act_hint,
                }
            )
        return results

    def get_query_summary(self, query: str, language: str = "en") -> str:
        """
        Return a short human-readable summary of what the query is asking.
        Useful for logging and debugging.
        """
        processed = self.process_query(query, language)
        keywords = ", ".join(processed["keywords"][:5]) or "general"
        intent = processed["intent"].replace("_", " ")
        entities = processed["entities"]
        sections = ", ".join(entities.get("section_numbers", []))
        parts = [f"Intent: {intent}", f"Keywords: {keywords}"]
        if sections:
            parts.append(f"Sections: {sections}")
        return " | ".join(parts)
