"""
Location Service - Geolocation and state-specific legal context
"""
import json
import logging
from typing import Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"

STATE_ALIASES = {
    "karnataka": "Karnataka",
    "maharashtra": "Maharashtra",
    "tamil nadu": "Tamil Nadu",
    "tamilnadu": "Tamil Nadu",
    "andhra pradesh": "Andhra Pradesh",
    "telangana": "Telangana",
    "gujarat": "Gujarat",
    "rajasthan": "Rajasthan",
    "uttar pradesh": "Uttar Pradesh",
    "up": "Uttar Pradesh",
    "west bengal": "West Bengal",
    "delhi": "Delhi",
    "ncr": "Delhi",
    "mp": "Madhya Pradesh",
    "madhya pradesh": "Madhya Pradesh",
    "punjab": "Punjab",
    "haryana": "Haryana",
    "bihar": "Bihar",
    "odisha": "Odisha",
    "orissa": "Odisha",
    "kerala": "Kerala",
    "assam": "Assam",
    "jharkhand": "Jharkhand",
    "uttarakhand": "Uttarakhand",
    "himachal pradesh": "Himachal Pradesh",
    "goa": "Goa",
    "chhattisgarh": "Chhattisgarh",
    "jammu and kashmir": "Jammu and Kashmir",
    "j&k": "Jammu and Kashmir",
}

LANGUAGE_STATE_MAP = {
    "kannada": "Karnataka",
    "marathi": "Maharashtra",
    "tamil": "Tamil Nadu",
    "telugu": "Andhra Pradesh",
    "hindi": "Delhi",
    "gujarati": "Gujarat",
    "bengali": "West Bengal",
    "punjabi": "Punjab",
    "malayalam": "Kerala",
    "odia": "Odisha",
    "assamese": "Assam",
}


class LocationService:
    def __init__(self):
        self.state_data = self._load_state_data()
        self.tenancy_data = self._load_tenancy_data()

    def _load_state_data(self) -> Dict:
        path = DATA_DIR / "state_laws.json"
        if path.exists():
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading state laws: {e}")
        return {}

    def _load_tenancy_data(self) -> Dict:
        path = DATA_DIR / "tenancy_act.json"
        if path.exists():
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading tenancy data: {e}")
        return {}

    def normalize_state(self, state_input: str) -> Optional[str]:
        """Normalize state name to standard form"""
        if not state_input:
            return None
        normalized = STATE_ALIASES.get(state_input.lower().strip())
        if normalized:
            return normalized
        states = self.state_data.get("states", {})
        for state_name in states:
            if state_name.lower() == state_input.lower().strip():
                return state_name
        return state_input.title()

    def get_state_from_language(self, language: str) -> Optional[str]:
        """Get default state based on language"""
        return LANGUAGE_STATE_MAP.get(language.lower())

    def get_state_laws(self, state: str) -> Dict:
        """Get state-specific legal information"""
        normalized = self.normalize_state(state)
        states = self.state_data.get("states", {})
        if normalized and normalized in states:
            return states[normalized]
        return {}

    def get_tenancy_laws(self, state: str) -> Dict:
        """Get tenancy laws for a specific state"""
        normalized = self.normalize_state(state)
        state_variations = self.tenancy_data.get("state_variations", {})
        if normalized and normalized in state_variations:
            return {
                "state": normalized,
                "state_specific": state_variations[normalized],
                "model_act": self.tenancy_data.get("model_tenancy_act", {}),
            }
        return {
            "state": normalized,
            "state_specific": None,
            "model_act": self.tenancy_data.get("model_tenancy_act", {}),
        }

    def get_legal_context(self, state: str, query_categories: list) -> str:
        """Get formatted state-specific legal context"""
        state_laws = self.get_state_laws(state)
        if not state_laws:
            return f"Legal queries for {state}: Please consult local courts and legal aid services."

        parts = []

        if "high_court" in state_laws:
            parts.append(f"High Court: {state_laws['high_court']}")

        if "tenancy" in query_categories:
            tenancy = self.get_tenancy_laws(state)
            ts = tenancy.get("state_specific")
            if ts:
                act_name = ts.get("act_name", "")
                if act_name:
                    parts.append(f"Tenancy Law: {act_name}")

        if "property" in query_categories and "stamp_duty_percent" in state_laws:
            parts.append(f"Stamp Duty: {state_laws['stamp_duty_percent']}%")

        if "key_local_laws" in state_laws:
            laws = state_laws["key_local_laws"][:3]
            if laws:
                parts.append("Key local laws: " + ", ".join(laws))

        return "\n".join(parts) if parts else f"State: {state}"


_location_service = None


def get_location_service() -> LocationService:
    global _location_service
    if _location_service is None:
        _location_service = LocationService()
    return _location_service
