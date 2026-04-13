"""
Location Service for Vani-Kanoon
Detects user state from text or IP address and returns state-specific
legal information, court details, and jurisdiction guidance.
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency: httpx for IP geo-location (non-blocking)
# ---------------------------------------------------------------------------
try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False
    logger.info("httpx not installed — IP-based state detection will be limited.")

# ---------------------------------------------------------------------------
# Data file
# ---------------------------------------------------------------------------
_STATE_LAWS_FILE = Path(__file__).parent / "data" / "state_laws.json"
_state_laws_cache: Optional[Dict[str, Any]] = None


def _load_state_laws() -> Dict[str, Any]:
    """Load and cache the state_laws.json data file."""
    global _state_laws_cache
    if _state_laws_cache is not None:
        return _state_laws_cache
    try:
        with open(_STATE_LAWS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        _state_laws_cache = data
        return data
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load state_laws.json: %s", exc)
        return {"states": {}}


# ---------------------------------------------------------------------------
# State keyword mapping for text detection
# ---------------------------------------------------------------------------
_STATE_KEYWORDS: Dict[str, List[str]] = {
    "Maharashtra": [
        "maharashtra", "mumbai", "pune", "nagpur", "aurangabad", "nashik",
        "thane", "kolhapur", "solapur", "bombay",
    ],
    "Karnataka": [
        "karnataka", "bengaluru", "bangalore", "mysuru", "mysore", "hubli",
        "dharwad", "mangaluru", "mangalore", "belagavi", "belgaum",
        "kalaburagi", "gulbarga",
    ],
    "Tamil Nadu": [
        "tamil nadu", "tamilnadu", "chennai", "madras", "coimbatore",
        "madurai", "tiruchirappalli", "trichy", "salem", "vellore",
        "tirunelveli", "erode",
    ],
    "Telangana": [
        "telangana", "hyderabad", "warangal", "nizamabad", "karimnagar",
        "khammam", "rangareddy",
    ],
    "Andhra Pradesh": [
        "andhra pradesh", "andhra", "visakhapatnam", "vizag", "vijayawada",
        "guntur", "tirupati", "rajahmundry", "kurnool",
    ],
    "Kerala": [
        "kerala", "thiruvananthapuram", "trivandrum", "kochi", "cochin",
        "kozhikode", "calicut", "thrissur", "kollam", "malappuram",
    ],
    "West Bengal": [
        "west bengal", "kolkata", "calcutta", "howrah", "siliguri",
        "asansol", "durgapur", "darjeeling",
    ],
    "Uttar Pradesh": [
        "uttar pradesh", "up", "lucknow", "kanpur", "agra", "varanasi",
        "allahabad", "prayagraj", "meerut", "ghaziabad", "noida",
        "mathura", "bareilly",
    ],
    "Delhi": [
        "delhi", "new delhi", "dwarka", "rohini", "south delhi",
        "north delhi", "east delhi",
    ],
    "Rajasthan": [
        "rajasthan", "jaipur", "jodhpur", "udaipur", "kota", "ajmer",
        "bikaner", "alwar",
    ],
    "Madhya Pradesh": [
        "madhya pradesh", "mp", "bhopal", "indore", "jabalpur", "gwalior",
        "ujjain", "sagar",
    ],
    "Gujarat": [
        "gujarat", "ahmedabad", "surat", "vadodara", "baroda", "rajkot",
        "bhavnagar", "jamnagar", "gandhinagar",
    ],
    "Bihar": [
        "bihar", "patna", "gaya", "bhagalpur", "muzaffarpur", "darbhanga",
    ],
    "Jharkhand": [
        "jharkhand", "ranchi", "jamshedpur", "dhanbad", "bokaro",
    ],
    "Odisha": [
        "odisha", "orissa", "bhubaneswar", "cuttack", "rourkela", "berhampur",
    ],
    "Chhattisgarh": [
        "chhattisgarh", "raipur", "bhilai", "bilaspur", "durg",
    ],
    "Haryana": [
        "haryana", "gurugram", "gurgaon", "faridabad", "hisar",
        "rohtak", "panipat", "ambala",
    ],
    "Punjab": [
        "punjab", "chandigarh", "ludhiana", "amritsar", "jalandhar",
        "patiala", "bathinda",
    ],
    "Himachal Pradesh": [
        "himachal pradesh", "shimla", "manali", "dharamshala", "solan",
    ],
    "Uttarakhand": [
        "uttarakhand", "uttaranchal", "dehradun", "haridwar", "rishikesh",
        "nainital", "roorkee",
    ],
    "Assam": [
        "assam", "guwahati", "dibrugarh", "jorhat", "silchar",
    ],
    "Goa": [
        "goa", "panaji", "margao", "vasco",
    ],
}

# Offense → jurisdiction type mapping
_OFFENSE_JURISDICTION: Dict[str, Dict[str, Any]] = {
    "murder": {
        "court": "Sessions Court",
        "trial": "Sessions trial",
        "appeal": "High Court",
        "police": "Cognizable, non-bailable",
        "note": "Investigated by police; charges filed in Sessions Court.",
    },
    "rape": {
        "court": "Special Fast Track Court / Sessions Court",
        "trial": "In-camera trial mandatory",
        "appeal": "High Court",
        "police": "Cognizable, non-bailable",
        "note": "Statement of victim recorded by female magistrate; fast-track proceedings.",
    },
    "theft": {
        "court": "Magistrate Court (Judicial Magistrate First Class)",
        "trial": "Summary trial if value < ₹2 lakh",
        "appeal": "Sessions Court",
        "police": "Cognizable, bailable (minor theft)",
        "note": "Can be compounded with victim consent for petty theft.",
    },
    "domestic violence": {
        "court": "Magistrate Court / Family Court",
        "trial": "Protection order proceedings",
        "appeal": "Sessions Court / High Court",
        "police": "Cognizable (under Section 498A IPC)",
        "note": "Parallel civil remedies under PWDVA 2005; free legal aid available.",
    },
    "fraud": {
        "court": "Magistrate Court / Special CBI Court (if central government involved)",
        "trial": "Regular trial",
        "appeal": "Sessions Court",
        "police": "Cognizable if cheating above certain threshold",
        "note": "Parallel civil suit for damages possible.",
    },
    "cyber crime": {
        "court": "Designated Cyber Crime Court / Magistrate",
        "trial": "IT Act proceedings",
        "appeal": "High Court",
        "police": "Cyber Crime Cell",
        "note": "Report at cybercrime.gov.in or nearest cyber crime police station.",
    },
    "consumer complaint": {
        "court": "District Consumer Commission (< ₹50 lakh), State Commission (< ₹2 crore), NCDRC (> ₹2 crore)",
        "trial": "Consumer forum proceedings",
        "appeal": "Next tier commission or High Court",
        "police": "Not applicable",
        "note": "File complaint at consumerhelpline.gov.in; limitation period 2 years.",
    },
    "land dispute": {
        "court": "Civil Court / Revenue Court",
        "trial": "Civil suit",
        "appeal": "High Court",
        "police": "Non-cognizable in most cases",
        "note": "Mediation / Lok Adalat recommended for faster resolution.",
    },
    "bail": {
        "court": "Magistrate (regular bail) / Sessions Court (anticipatory bail)",
        "trial": "N/A",
        "appeal": "Sessions Court / High Court / Supreme Court",
        "police": "N/A",
        "note": "Anticipatory bail under Section 438 CrPC filed before arrest.",
    },
}


class LocationService:
    """
    Determines user's geographic location and provides state-specific
    legal information, court details, and jurisdiction guidance.
    """

    def __init__(self) -> None:
        self._state_data = _load_state_laws()
        logger.info(
            "LocationService initialised — %d states loaded.",
            len(self._state_data.get("states", {})),
        )

    # ------------------------------------------------------------------
    # State detection
    # ------------------------------------------------------------------

    def detect_state_from_text(self, text: str) -> Optional[str]:
        """
        Detect Indian state from mentions of cities or state names in text.

        Returns the canonical state name (e.g. "Maharashtra") or None.
        """
        if not text:
            return None
        text_lower = text.lower()
        # Prioritise more specific (longer) keyword matches first
        best_state: Optional[str] = None
        best_len = 0
        for state, keywords in _STATE_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower and len(kw) > best_len:
                    best_state = state
                    best_len = len(kw)
        return best_state

    def detect_state_from_ip(self, ip: str) -> Dict[str, Any]:
        """
        Detect state from IP address using ip-api.com (free tier).

        Args:
            ip: IPv4 or IPv6 address string.

        Returns:
            {
                "state": str | None,
                "city": str,
                "country": str,
                "source": str,   # "ip_api" | "placeholder"
            }
        """
        if not ip or ip in ("127.0.0.1", "::1", "localhost"):
            return {"state": None, "city": "", "country": "IN", "source": "placeholder"}

        if not _HTTPX_AVAILABLE:
            logger.warning("httpx not installed — IP location lookup unavailable.")
            return {"state": None, "city": "", "country": "IN", "source": "placeholder"}

        try:
            url = f"http://ip-api.com/json/{ip}?fields=status,country,regionName,city"
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()

            if data.get("status") == "success" and data.get("country") == "India":
                region = data.get("regionName", "")
                # Map API region name to canonical state name
                canonical = self._normalise_state_name(region)
                return {
                    "state": canonical,
                    "city": data.get("city", ""),
                    "country": "IN",
                    "source": "ip_api",
                }
            return {"state": None, "city": "", "country": data.get("country", ""), "source": "ip_api"}
        except Exception as exc:  # noqa: BLE001
            logger.warning("IP location lookup failed for %s: %s", ip, exc)
            return {"state": None, "city": "", "country": "IN", "source": "error"}

    def _normalise_state_name(self, region: str) -> Optional[str]:
        """Map a region string (from IP API) to a canonical Indian state name."""
        region_lower = region.lower().strip()
        for state in self._state_data.get("states", {}):
            if state.lower() == region_lower:
                return state
        # Fuzzy keyword match
        for state, keywords in _STATE_KEYWORDS.items():
            if any(kw in region_lower for kw in keywords):
                return state
        return region if region else None

    # ------------------------------------------------------------------
    # State-specific legal information
    # ------------------------------------------------------------------

    def get_state_laws(self, state: str) -> Dict[str, Any]:
        """
        Retrieve state-specific laws and legal information.

        Args:
            state: Canonical state name, e.g. "Maharashtra".

        Returns:
            Dict with keys: state, laws, courts, legal_aid, contacts.
            Returns empty structure if state not found.
        """
        states = self._state_data.get("states", {})
        state_data = states.get(state)

        if state_data is None:
            # Case-insensitive fallback
            for k, v in states.items():
                if k.lower() == state.lower():
                    state_data = v
                    state = k
                    break

        if state_data is None:
            logger.warning("State '%s' not found in database.", state)
            return {
                "state": state,
                "laws": [],
                "courts": [],
                "legal_aid": {},
                "contacts": {},
                "found": False,
            }

        return {
            "state": state,
            "capital": state_data.get("capital", ""),
            "high_court": state_data.get("high_court", ""),
            "official_language": state_data.get("official_language", ""),
            "laws": state_data.get("specific_laws", []),
            "courts": state_data.get("local_courts", []),
            "legal_aid": state_data.get("legal_aid", {}),
            "contacts": state_data.get("important_contact", {}),
            "found": True,
        }

    def get_local_courts(
        self,
        state: str,
        district: Optional[str] = None,
        jurisdiction_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get court information for a state with optional filtering.

        Args:
            state:             State name.
            district:          District name to narrow down (optional).
            jurisdiction_type: Filter by jurisdiction keyword (optional),
                               e.g. "family", "consumer", "criminal".

        Returns:
            List of court dicts with name and jurisdiction.
        """
        state_info = self.get_state_laws(state)
        courts = state_info.get("courts", [])

        if district:
            # Keep courts that mention the district or have generic jurisdiction
            courts = [
                c for c in courts
                if district.lower() in c.get("name", "").lower()
                or "jurisdiction" in c
            ]

        if jurisdiction_type:
            jtype_lower = jurisdiction_type.lower()
            courts = [
                c for c in courts
                if jtype_lower in c.get("jurisdiction", "").lower()
                or jtype_lower in c.get("name", "").lower()
            ]

        return courts

    def get_legal_aid_info(self, state: str) -> Dict[str, Any]:
        """
        Return legal aid authority and contact info for a state.

        Returns dict with: authority, contact, eligibility, services.
        """
        state_info = self.get_state_laws(state)
        legal_aid = state_info.get("legal_aid", {})
        if not legal_aid:
            return {
                "authority": "State Legal Services Authority",
                "contact": "15100",
                "eligibility": "Annual income below ₹3 lakh; SC/ST/women/children/persons with disability",
                "services": ["Free legal representation", "Lok Adalat"],
                "note": f"Contact SLSA for {state}.",
            }
        return legal_aid

    # ------------------------------------------------------------------
    # Jurisdiction
    # ------------------------------------------------------------------

    def get_jurisdiction(
        self,
        offense_type: str,
        state: str,
    ) -> Dict[str, Any]:
        """
        Return jurisdiction information for an offense type and state.

        Args:
            offense_type: e.g. "murder", "rape", "theft", "domestic violence".
            state:        Indian state name.

        Returns:
            {
                "offense_type": str,
                "court": str,
                "trial": str,
                "appeal": str,
                "police_action": str,
                "state_specific_notes": List[str],
                "high_court": str,
            }
        """
        offense_lower = offense_type.lower()

        # Fuzzy match offense type
        jurisdiction_info: Optional[Dict[str, Any]] = None
        for key, info in _OFFENSE_JURISDICTION.items():
            if key in offense_lower or offense_lower in key:
                jurisdiction_info = info
                break

        if jurisdiction_info is None:
            jurisdiction_info = {
                "court": "Appropriate Magistrate / Sessions Court",
                "trial": "Based on severity of offense",
                "appeal": "Sessions Court → High Court → Supreme Court",
                "police": "Determine cognizability from FIR",
                "note": "Consult a lawyer to determine the appropriate forum.",
            }

        state_info = self.get_state_laws(state)
        high_court = state_info.get("high_court", "State High Court")

        # Collect state-specific notes relevant to the offense
        state_specific_notes: List[str] = []
        for law in state_info.get("laws", []):
            law_name = law.get("name", "").lower()
            if any(kw in law_name for kw in offense_lower.split()):
                state_specific_notes.append(
                    f"{law.get('name', '')}: {law.get('description', '')}"
                )

        return {
            "offense_type": offense_type,
            "court": jurisdiction_info.get("court", ""),
            "trial": jurisdiction_info.get("trial", ""),
            "appeal": jurisdiction_info.get("appeal", ""),
            "police_action": jurisdiction_info.get("police", ""),
            "note": jurisdiction_info.get("note", ""),
            "state_specific_notes": state_specific_notes[:3],
            "high_court": high_court,
            "state": state,
        }

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_emergency_contacts(self, state: str) -> Dict[str, str]:
        """Return emergency contact numbers for the given state."""
        state_info = self.get_state_laws(state)
        contacts = state_info.get("contacts", {})

        # National defaults always present
        defaults = {
            "police_emergency": "100",
            "women_helpline": "1091",
            "legal_aid_helpline": "15100",
            "child_helpline": "1098",
            "ambulance": "108",
            "cybercrime_helpline": "1930",
            "domestic_violence_helpline": "181",
        }
        defaults.update(contacts)
        return defaults

    def list_available_states(self) -> List[str]:
        """Return all state names present in the database."""
        return sorted(self._state_data.get("states", {}).keys())

    def get_state_summary(self, state: str) -> str:
        """
        Return a brief human-readable summary of the state's legal landscape.
        """
        info = self.get_state_laws(state)
        if not info.get("found"):
            return f"No information available for {state}."
        lines = [
            f"State: {state}",
            f"High Court: {info.get('high_court', 'N/A')}",
            f"Official Language: {info.get('official_language', 'N/A')}",
            f"State-specific laws: {len(info.get('laws', []))}",
            f"Local courts listed: {len(info.get('courts', []))}",
        ]
        legal_aid = info.get("legal_aid", {})
        if legal_aid.get("contact"):
            lines.append(f"Legal Aid Helpline: {legal_aid['contact']}")
        return " | ".join(lines)
