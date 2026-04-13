"""
Location-aware legal context service for Vani-Kanoon.
Provides state-specific laws, courts, and jurisdiction information.
"""
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    logger.warning("requests not available; reverse geocoding disabled.")


# Canonical state name → key (as used in state_laws.json)
STATE_NAME_MAP = {
    # Full names
    "Karnataka": "Karnataka",
    "Maharashtra": "Maharashtra",
    "Tamil Nadu": "Tamil Nadu",
    "Delhi": "Delhi",
    "Telangana": "Telangana",
    "Rajasthan": "Rajasthan",
    "Gujarat": "Gujarat",
    # Common aliases
    "karnataka": "Karnataka",
    "maharashtra": "Maharashtra",
    "tamilnadu": "Tamil Nadu",
    "tamilnad": "Tamil Nadu",
    "delhi": "Delhi",
    "ncr": "Delhi",
    "new delhi": "Delhi",
    "telangana": "Telangana",
    "rajasthan": "Rajasthan",
    "gujarat": "Gujarat",
    "bengaluru": "Karnataka",
    "bangalore": "Karnataka",
    "mumbai": "Maharashtra",
    "bombay": "Maharashtra",
    "chennai": "Tamil Nadu",
    "madras": "Tamil Nadu",
    "hyderabad": "Telangana",
    "jaipur": "Rajasthan",
    "ahmedabad": "Gujarat",
    # Other major states (no detailed data yet, returns empty dict gracefully)
    "Uttar Pradesh": "Uttar Pradesh",
    "West Bengal": "West Bengal",
    "Bihar": "Bihar",
    "Madhya Pradesh": "Madhya Pradesh",
    "Andhra Pradesh": "Andhra Pradesh",
    "Odisha": "Odisha",
    "Kerala": "Kerala",
    "Punjab": "Punjab",
    "Haryana": "Haryana",
    "Jharkhand": "Jharkhand",
    "Assam": "Assam",
    "Uttarakhand": "Uttarakhand",
    "Himachal Pradesh": "Himachal Pradesh",
    "Chhattisgarh": "Chhattisgarh",
    "Goa": "Goa",
}

JURISDICTION_INFO = {
    "criminal": {
        "central": True,
        "primary_court": "Sessions Court / Chief Judicial Magistrate",
        "high_court": "State High Court",
        "apex_court": "Supreme Court of India",
        "police_role": "File FIR at nearest police station",
    },
    "civil": {
        "central": False,
        "primary_court": "Civil Judge / District Court",
        "high_court": "State High Court",
        "apex_court": "Supreme Court of India",
    },
    "property": {
        "central": False,
        "primary_court": "Civil Court / Revenue Court",
        "high_court": "State High Court",
        "apex_court": "Supreme Court of India",
        "special_tribunal": "RERA Tribunal (for real estate disputes)",
    },
    "family": {
        "central": False,
        "primary_court": "Family Court / District Court",
        "high_court": "State High Court",
        "apex_court": "Supreme Court of India",
    },
}


class LocationService:
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
    # Reverse geocoding
    # ------------------------------------------------------------------

    def get_state_from_location(self, lat: float, lon: float) -> str:
        """
        Reverse geocode *lat*/*lon* to an Indian state name.
        Uses Nominatim (OpenStreetMap) — no API key required.
        Falls back to "Unknown" if unavailable.
        """
        if not REQUESTS_AVAILABLE:
            return "Unknown"
        try:
            url = "https://nominatim.openstreetmap.org/reverse"
            params = {
                "lat": lat,
                "lon": lon,
                "format": "json",
                "zoom": 5,
                "addressdetails": 1,
            }
            headers = {"User-Agent": "VaniKanoon/1.0 (https://github.com/Vani/Vani)"}
            resp = requests.get(url, params=params, headers=headers, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            address = data.get("address", {})
            state = (
                address.get("state")
                or address.get("state_district")
                or address.get("county")
                or "Unknown"
            )
            return self._normalize_state_name(state)
        except Exception as e:
            logger.error("Reverse geocoding failed: %s", e)
            return "Unknown"

    def _normalize_state_name(self, raw: str) -> str:
        return STATE_NAME_MAP.get(raw, STATE_NAME_MAP.get(raw.lower(), raw))

    # ------------------------------------------------------------------
    # State laws
    # ------------------------------------------------------------------

    def get_state_laws(self, state: str) -> dict:
        """Return state-specific legal data from state_laws.json."""
        key = STATE_NAME_MAP.get(state, state)
        data = self._state_data.get(key, {})
        if not data:
            return {"message": f"Detailed state law data not yet available for {state}."}
        return data

    # ------------------------------------------------------------------
    # Courts
    # ------------------------------------------------------------------

    def get_local_courts(self, state: str, city: Optional[str] = None) -> list[dict]:
        """Return court list for the given state (filtered by city if provided)."""
        key = STATE_NAME_MAP.get(state, state)
        state_info = self._state_data.get(key, {})
        courts = state_info.get("courts", [])
        if city:
            city_lower = city.lower()
            filtered = [c for c in courts if city_lower in c.get("location", "").lower()]
            return filtered if filtered else courts
        return courts

    # ------------------------------------------------------------------
    # Jurisdiction
    # ------------------------------------------------------------------

    def get_jurisdiction_info(self, query_type: str, state: str) -> dict:
        """Combine generic jurisdiction info with state-specific court data."""
        base = JURISDICTION_INFO.get(query_type, {}).copy()
        key = STATE_NAME_MAP.get(state, state)
        state_info = self._state_data.get(key, {})
        if state_info:
            high_court = next(
                (c["name"] for c in state_info.get("courts", []) if "High Court" in c["name"]),
                f"{state} High Court",
            )
            base["state_high_court"] = high_court
            base["state"] = state
            tenancy = state_info.get("tenancy", {})
            if tenancy:
                base["tenancy_forum"] = tenancy.get("dispute_forum", "")
        return base

    # ------------------------------------------------------------------
    # State name normalisation
    # ------------------------------------------------------------------

    def get_state_from_name(self, state_name: str) -> dict:
        """Normalize a raw state name and return its metadata."""
        canonical = STATE_NAME_MAP.get(state_name, STATE_NAME_MAP.get(state_name.lower(), state_name))
        return {
            "canonical_name": canonical,
            "has_detailed_data": canonical in self._state_data,
        }
