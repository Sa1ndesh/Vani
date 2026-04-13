"""
Legal Query Processor - Normalizes queries and extracts legal context
"""
import re
import json
import logging
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"

# Common query patterns and their legal categories
QUERY_PATTERNS = {
    "criminal": [
        r"\b(murder|theft|robbery|assault|rape|cheating|fraud|arrest|FIR|bail)\b",
        r"\b(IPC|BNS|section \d+|criminal case)\b",
        r"\b(हत्या|चोरी|डकैती|बलात्कार|धोखाधड़ी|गिरफ्तारी|जमानत)\b",
        r"\b(ಕೊಲೆ|ಕಳ್ಳತನ|ಅತ್ಯಾಚಾರ|ಬೆಲ್|ಬಂಧನ)\b",
    ],
    "property": [
        r"\b(property|land|plot|house|sale|purchase|deed|registry|stamp duty)\b",
        r"\b(transfer|lease|mortgage|encumbrance|title|ownership)\b",
        r"\b(संपत्ति|जमीन|मकान|रजिस्ट्री|बिक्री)\b",
    ],
    "family": [
        r"\b(divorce|marriage|maintenance|custody|inheritance|succession|dowry)\b",
        r"\b(talaq|mehr|guardian|adoption|alimony)\b",
        r"\b(तलाक|विवाह|गुजारा भत्ता|हिरासत|विरासत|दहेज)\b",
    ],
    "tenancy": [
        r"\b(rent|tenant|landlord|eviction|lease|tenancy|notice)\b",
        r"\b(किराया|किरायेदार|मकान मालिक|बेदखली)\b",
        r"\b(ಬಾಡಿಗೆ|ಬಾಡಿಗೆದಾರ|ಮನೆಮಾಲೀಕ|ಒಕ್ಕಲೆಬ್ಬಿಸುವಿಕೆ)\b",
    ],
    "consumer": [
        r"\b(consumer|product|defect|complaint|refund|warranty|e-commerce)\b",
        r"\b(उपभोक्ता|शिकायत|वापसी|वारंटी)\b",
    ],
    "labour": [
        r"\b(labour|labor|employee|employer|salary|wages|termination|PF|ESI|gratuity)\b",
        r"\b(श्रमिक|कर्मचारी|वेतन|बर्खास्तगी|भविष्य निधि)\b",
    ],
}

# Legal section patterns
SECTION_PATTERN = re.compile(r'[Ss]ection\s+(\d+[A-Za-z]?)', re.IGNORECASE)
IPC_PATTERN = re.compile(r'IPC\s*(\d+[A-Za-z]?)', re.IGNORECASE)
BNS_PATTERN = re.compile(r'BNS\s*(\d+[A-Za-z]?)', re.IGNORECASE)


class LegalQueryProcessor:
    def __init__(self):
        self.ipc_data = self._load_json("ipc_sections.json")
        self.bns_data = self._load_json("bns_sections.json")
        self.state_data = self._load_json("state_laws.json")

    def _load_json(self, filename: str) -> Dict:
        path = DATA_DIR / filename
        if path.exists():
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading {filename}: {e}")
        return {}

    def categorize_query(self, query: str) -> List[str]:
        """Identify legal categories relevant to the query"""
        categories = []
        for category, patterns in QUERY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query, re.IGNORECASE):
                    if category not in categories:
                        categories.append(category)
                    break
        return categories or ["general"]

    def extract_section_references(self, query: str) -> List[Dict]:
        """Extract explicit section references from query"""
        refs = []
        for match in IPC_PATTERN.finditer(query):
            refs.append({"type": "IPC", "number": match.group(1)})
        for match in BNS_PATTERN.finditer(query):
            refs.append({"type": "BNS", "number": match.group(1)})
        for match in SECTION_PATTERN.finditer(query):
            refs.append({"type": "section", "number": match.group(1)})
        return refs

    def normalize_query(self, query: str, language: str = "english") -> str:
        """Normalize and clean query for better search"""
        query = re.sub(r'\s+', ' ', query.strip())
        abbreviations = {
            "FIR": "First Information Report",
            "PIL": "Public Interest Litigation",
            "HC": "High Court",
            "SC": "Supreme Court",
            "CrPC": "Code of Criminal Procedure",
            "CPC": "Civil Procedure Code",
        }
        for abbr, full in abbreviations.items():
            query = re.sub(r'\b' + re.escape(abbr) + r'\b', f"{abbr} ({full})", query)
        return query

    def _find_section(self, data: Dict, section_num: str) -> Optional[Dict]:
        """Find a specific section in legal data"""
        for s in data.get("sections", []):
            if str(s.get("section", "")).strip() == str(section_num).strip():
                return dict(s)
        return None

    def process(self, query: str, language: str = "english", state: Optional[str] = None) -> Dict:
        """Process a legal query and return structured context"""
        categories = self.categorize_query(query)
        section_refs = self.extract_section_references(query)
        normalized = self.normalize_query(query, language)

        specific_sections = []
        for ref in section_refs:
            if ref["type"] == "IPC":
                section = self._find_section(self.ipc_data, ref["number"])
                if section:
                    section["source"] = "IPC"
                    specific_sections.append(section)
            elif ref["type"] == "BNS":
                section = self._find_section(self.bns_data, ref["number"])
                if section:
                    section["source"] = "BNS"
                    specific_sections.append(section)

        return {
            "original_query": query,
            "normalized_query": normalized,
            "categories": categories,
            "section_references": section_refs,
            "specific_sections": specific_sections,
            "language": language,
            "state": state,
        }


_processor = None


def get_legal_processor() -> LegalQueryProcessor:
    global _processor
    if _processor is None:
        _processor = LegalQueryProcessor()
    return _processor
