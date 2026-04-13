"""
Legal Data Loader - Loads and validates all legal data files
"""
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"

REQUIRED_FILES = [
    "ipc_sections.json",
    "bns_sections.json",
    "tenancy_act.json",
    "family_law.json",
    "property_law.json",
    "state_laws.json",
    "dialect_mapping.json",
]


def _count_sections(data) -> int:
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        if "sections" in data:
            return len(data["sections"])
        total = 0
        for v in data.values():
            if isinstance(v, dict) and "sections" in v:
                total += len(v["sections"])
            elif isinstance(v, list):
                total += len(v)
        return total
    return 0


def load_and_validate():
    results = {}
    all_ok = True
    for filename in REQUIRED_FILES:
        path = DATA_DIR / filename
        if not path.exists():
            logger.error(f"MISSING: {filename}")
            results[filename] = {"status": "missing", "count": 0}
            all_ok = False
            continue
        try:
            with open(path) as f:
                data = json.load(f)
            count = _count_sections(data)
            logger.info(f"OK: {filename} - {count} entries")
            results[filename] = {"status": "ok", "count": count}
        except json.JSONDecodeError as e:
            logger.error(f"INVALID JSON: {filename} - {e}")
            results[filename] = {"status": "invalid_json", "error": str(e)}
            all_ok = False
        except Exception as e:
            logger.error(f"ERROR: {filename} - {e}")
            results[filename] = {"status": "error", "error": str(e)}
            all_ok = False
    return results, all_ok


def get_summary() -> dict:
    results, all_ok = load_and_validate()
    total_sections = sum(r.get("count", 0) for r in results.values())
    return {
        "all_ok": all_ok,
        "files": results,
        "total_sections": total_sections,
        "data_dir": str(DATA_DIR),
    }


if __name__ == "__main__":
    results, all_ok = load_and_validate()
    total = sum(r.get("count", 0) for r in results.values())
    print(f"\nTotal sections/entries: {total}")
    print(f"All files valid: {all_ok}")
    if not all_ok:
        sys.exit(1)
    print("✅ All legal data files loaded successfully!")
