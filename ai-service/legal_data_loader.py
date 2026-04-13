"""
Legal Data Loader for Vani-Kanoon
Loads Indian legal data from JSON files, generates embeddings, and initializes a search index.
Falls back to TF-IDF + cosine similarity if sentence-transformers / FAISS are not available.
"""

import os
import json
import logging
import pickle
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional heavy dependencies — graceful fallback
# ---------------------------------------------------------------------------
try:
    from sentence_transformers import SentenceTransformer
    _SENTENCE_TRANSFORMERS_AVAILABLE = True
    logger.info("sentence-transformers is available.")
except ImportError:
    _SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning("sentence-transformers not installed — falling back to TF-IDF embeddings.")

try:
    import faiss
    _FAISS_AVAILABLE = True
    logger.info("faiss is available.")
except ImportError:
    _FAISS_AVAILABLE = False
    logger.warning("faiss not installed — falling back to numpy cosine similarity search.")

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False
    logger.warning("scikit-learn not installed — TF-IDF fallback disabled.")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).parent / "data"
CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

CACHE_FILE = CACHE_DIR / "legal_index.pkl"
EMBEDDINGS_FILE = CACHE_DIR / "embeddings.npy"

# ---------------------------------------------------------------------------
# Model name for sentence-transformers (multilingual, lightweight)
# ---------------------------------------------------------------------------
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# Singleton index state
_index_state: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _flatten_sections(
    data: Dict[str, Any],
    source_file: str,
    act_title: str,
    act_short: str,
) -> List[Dict[str, Any]]:
    """Flatten a list of section dicts into the canonical record format."""
    records: List[Dict[str, Any]] = []
    sections = data.get("sections", [])
    for sec in sections:
        if not isinstance(sec, dict):
            continue
        section_num = str(sec.get("section", sec.get("section_number", "")))
        title = sec.get("title", sec.get("heading", ""))
        description = sec.get("description", sec.get("text", sec.get("content", "")))
        punishment = sec.get("punishment", "")
        keywords = sec.get("keywords", [])
        example = sec.get("example", "")

        # Build a rich text blob for embedding
        parts = [f"{act_short} Section {section_num}: {title}"]
        if description:
            parts.append(description)
        if punishment:
            parts.append(f"Punishment: {punishment}")
        if keywords:
            parts.append("Keywords: " + ", ".join(keywords))
        if example:
            parts.append(f"Example: {example}")
        text = " | ".join(filter(None, parts))

        records.append(
            {
                "id": f"{act_short.lower().replace(' ', '_')}_{section_num}",
                "text": text,
                "metadata": {
                    "act": act_title,
                    "act_short": act_short,
                    "section": section_num,
                    "title": title,
                    "description": description,
                    "punishment": punishment,
                    "bailable": sec.get("bailable"),
                    "cognizable": sec.get("cognizable"),
                    "compoundable": sec.get("compoundable"),
                    "keywords": keywords,
                    "source_file": source_file,
                    "type": "section",
                },
            }
        )
    return records


def _flatten_acts(
    data: Dict[str, Any],
    source_file: str,
) -> List[Dict[str, Any]]:
    """Flatten acts structure (family_law.json / property_law.json pattern)."""
    records: List[Dict[str, Any]] = []
    acts = data.get("acts", [])
    for act in acts:
        if not isinstance(act, dict):
            continue
        act_name = act.get("name", act.get("title", "Unknown Act"))
        act_short = act.get("short_title", act.get("abbreviation", act_name[:20]))
        act_records = _flatten_sections(act, source_file, act_name, act_short)
        if not act_records:
            # Act itself has no sections sub-list — store act description as a record
            desc = act.get("description", act.get("overview", ""))
            key_provisions = act.get("key_provisions", [])
            text_parts = [f"{act_name}: {desc}"]
            if key_provisions:
                if isinstance(key_provisions, list) and key_provisions and isinstance(key_provisions[0], str):
                    text_parts.append("Key provisions: " + "; ".join(key_provisions))
            records.append(
                {
                    "id": f"act_{act_name[:40].lower().replace(' ', '_')}",
                    "text": " | ".join(filter(None, text_parts)),
                    "metadata": {
                        "act": act_name,
                        "act_short": act_short,
                        "section": None,
                        "title": act_name,
                        "description": desc,
                        "source_file": source_file,
                        "type": "act",
                    },
                }
            )
        records.extend(act_records)
    return records


def _flatten_state_laws(data: Dict[str, Any], source_file: str) -> List[Dict[str, Any]]:
    """Flatten state_laws.json into records."""
    records: List[Dict[str, Any]] = []
    states = data.get("states", {})
    for state_name, state_data in states.items():
        if not isinstance(state_data, dict):
            continue
        for law in state_data.get("specific_laws", []):
            law_name = law.get("name", "")
            desc = law.get("description", "")
            key_offences = law.get("key_offences", law.get("key_provisions", []))
            text_parts = [f"{state_name} Law: {law_name}", desc]
            if key_offences:
                text_parts.append("Key aspects: " + "; ".join(key_offences))
            records.append(
                {
                    "id": f"state_{state_name.lower()}_{law_name[:30].lower().replace(' ', '_')}",
                    "text": " | ".join(filter(None, text_parts)),
                    "metadata": {
                        "act": law_name,
                        "act_short": law_name[:20],
                        "section": None,
                        "title": law_name,
                        "description": desc,
                        "state": state_name,
                        "source_file": source_file,
                        "type": "state_law",
                    },
                }
            )
        # Legal aid record
        legal_aid = state_data.get("legal_aid", {})
        if legal_aid:
            text = (
                f"{state_name} Legal Aid: {legal_aid.get('authority', '')}. "
                f"Contact: {legal_aid.get('contact', '')}. "
                f"Eligibility: {legal_aid.get('eligibility', '')}."
            )
            records.append(
                {
                    "id": f"legal_aid_{state_name.lower().replace(' ', '_')}",
                    "text": text,
                    "metadata": {
                        "act": "Legal Aid",
                        "act_short": "Legal Aid",
                        "state": state_name,
                        "title": f"{state_name} Legal Aid",
                        "description": text,
                        "source_file": source_file,
                        "type": "legal_aid",
                    },
                }
            )
    return records


def _flatten_tenancy(data: Dict[str, Any], source_file: str) -> List[Dict[str, Any]]:
    """Flatten tenancy_act.json."""
    records: List[Dict[str, Any]] = []
    central_act = data.get("central_act", {})
    if central_act:
        records.extend(
            _flatten_sections(
                central_act,
                source_file,
                central_act.get("name", "Tenancy Act"),
                central_act.get("short_title", "Tenancy"),
            )
        )
    for principle in data.get("general_legal_principles", []):
        if not isinstance(principle, dict):
            continue
        text = f"Tenancy Legal Principle: {principle.get('principle', '')} — {principle.get('explanation', '')}"
        records.append(
            {
                "id": f"tenancy_principle_{principle.get('principle', '')[:30].lower().replace(' ', '_')}",
                "text": text,
                "metadata": {
                    "act": "Tenancy Law",
                    "act_short": "Tenancy",
                    "section": None,
                    "title": principle.get("principle", ""),
                    "description": principle.get("explanation", ""),
                    "source_file": source_file,
                    "type": "legal_principle",
                },
            }
        )
    return records


def load_all_legal_data() -> List[Dict[str, Any]]:
    """
    Load all JSON files from the data directory and return a flat list of records.

    Each record has the shape:
        {
            "id": str,
            "text": str,       # rich text for embedding
            "metadata": dict,  # original structured data
        }
    """
    if not DATA_DIR.exists():
        logger.error("Data directory not found: %s", DATA_DIR)
        return []

    records: List[Dict[str, Any]] = []
    json_files = list(DATA_DIR.glob("*.json"))
    if not json_files:
        logger.warning("No JSON files found in %s", DATA_DIR)
        return records

    loaders = {
        "ipc_sections.json": lambda d, f: _flatten_sections(
            d, f, d.get("title", "IPC"), d.get("short_title", "IPC")
        ),
        "bns_sections.json": lambda d, f: _flatten_sections(
            d, f, d.get("title", "BNS"), d.get("short_title", "BNS")
        ),
        "family_law.json": _flatten_acts,
        "property_law.json": _flatten_acts,
        "state_laws.json": _flatten_state_laws,
        "tenancy_act.json": _flatten_tenancy,
        "dialect_mapping.json": lambda d, f: [],  # metadata only, not indexed
    }

    for json_file in json_files:
        try:
            with open(json_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            loader_fn = loaders.get(json_file.name)
            if loader_fn is None:
                # Generic fallback — treat as acts structure
                loader_fn = _flatten_acts
            file_records = loader_fn(data, json_file.name)
            logger.info("Loaded %d records from %s", len(file_records), json_file.name)
            records.extend(file_records)
        except json.JSONDecodeError as exc:
            logger.error("JSON parse error in %s: %s", json_file.name, exc)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load %s: %s", json_file.name, exc)

    # Deduplicate by id
    seen_ids: set = set()
    unique_records: List[Dict[str, Any]] = []
    for rec in records:
        if rec["id"] not in seen_ids:
            seen_ids.add(rec["id"])
            unique_records.append(rec)

    logger.info("Total unique records loaded: %d", len(unique_records))
    return unique_records


def validate_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter out malformed records and warn about them."""
    valid = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        if not rec.get("text") or not rec.get("id"):
            logger.debug("Skipping record with missing text/id: %s", rec.get("id"))
            continue
        valid.append(rec)
    skipped = len(records) - len(valid)
    if skipped:
        logger.warning("Skipped %d invalid records during validation.", skipped)
    return valid


# ---------------------------------------------------------------------------
# Embedding generation
# ---------------------------------------------------------------------------

_sentence_model: Optional[Any] = None
_tfidf_vectorizer: Optional[Any] = None


def _get_sentence_model() -> Optional[Any]:
    global _sentence_model
    if _sentence_model is not None:
        return _sentence_model
    if not _SENTENCE_TRANSFORMERS_AVAILABLE:
        return None
    try:
        _sentence_model = SentenceTransformer(EMBEDDING_MODEL)
        logger.info("Loaded SentenceTransformer model: %s", EMBEDDING_MODEL)
        return _sentence_model
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load SentenceTransformer: %s", exc)
        return None


def generate_embeddings(
    texts: List[str],
    batch_size: int = 64,
) -> Tuple[np.ndarray, str]:
    """
    Generate embeddings for a list of texts.

    Returns:
        (embeddings_array, method_used)
        method_used is either 'sentence_transformers' or 'tfidf'
    """
    if not texts:
        return np.array([]), "none"

    model = _get_sentence_model()
    if model is not None:
        try:
            embeddings = model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=False,
                normalize_embeddings=True,
            )
            return embeddings.astype(np.float32), "sentence_transformers"
        except Exception as exc:  # noqa: BLE001
            logger.error("SentenceTransformer encoding failed: %s — falling back to TF-IDF", exc)

    # TF-IDF fallback
    if not _SKLEARN_AVAILABLE:
        logger.error("Neither sentence-transformers nor scikit-learn are available.")
        dim = 128
        return np.zeros((len(texts), dim), dtype=np.float32), "zeros"

    global _tfidf_vectorizer
    try:
        if _tfidf_vectorizer is None:
            _tfidf_vectorizer = TfidfVectorizer(
                max_features=2048,
                sublinear_tf=True,
                analyzer="word",
                token_pattern=r"(?u)\b\w+\b",
            )
            matrix = _tfidf_vectorizer.fit_transform(texts)
        else:
            matrix = _tfidf_vectorizer.transform(texts)
        dense = matrix.toarray().astype(np.float32)
        # L2-normalise for cosine similarity
        norms = np.linalg.norm(dense, axis=1, keepdims=True) + 1e-10
        return dense / norms, "tfidf"
    except Exception as exc:  # noqa: BLE001
        logger.error("TF-IDF embedding failed: %s", exc)
        return np.zeros((len(texts), 128), dtype=np.float32), "zeros"


def embed_query(query: str, method: str) -> np.ndarray:
    """Embed a single query string using the same method as the corpus."""
    if method == "sentence_transformers":
        model = _get_sentence_model()
        if model is not None:
            vec = model.encode([query], normalize_embeddings=True)
            return vec[0].astype(np.float32)
    if method == "tfidf" and _tfidf_vectorizer is not None:
        try:
            sparse = _tfidf_vectorizer.transform([query])
            dense = sparse.toarray().astype(np.float32)[0]
            norm = np.linalg.norm(dense) + 1e-10
            return dense / norm
        except Exception as exc:  # noqa: BLE001
            logger.error("TF-IDF query embedding failed: %s", exc)
    # Zeros fallback — will return low similarity for everything (safe)
    dim = 128
    return np.zeros(dim, dtype=np.float32)


# ---------------------------------------------------------------------------
# Index construction
# ---------------------------------------------------------------------------

class NumpyIndex:
    """Lightweight cosine-similarity index backed by a numpy matrix."""

    def __init__(self, embeddings: np.ndarray) -> None:
        self.embeddings = embeddings  # shape (N, D), already normalised

    def search(self, query_vec: np.ndarray, top_k: int = 5) -> Tuple[np.ndarray, np.ndarray]:
        """Return (distances, indices) — distances are cosine similarities."""
        if self.embeddings.shape[0] == 0:
            return np.array([]), np.array([], dtype=np.int64)
        sims = self.embeddings @ query_vec  # cosine similarity (vecs are unit-length)
        top_k = min(top_k, len(sims))
        indices = np.argsort(sims)[::-1][:top_k]
        distances = sims[indices]
        return distances, indices


def build_faiss_index(
    embeddings: np.ndarray,
) -> Tuple[Any, str]:
    """
    Build a FAISS inner-product index (equivalent to cosine similarity on
    normalised vectors) or fall back to the lightweight NumpyIndex.

    Returns:
        (index_object, index_type)
    """
    if embeddings.shape[0] == 0:
        return NumpyIndex(embeddings), "numpy"

    dim = embeddings.shape[1]

    if _FAISS_AVAILABLE:
        try:
            index = faiss.IndexFlatIP(dim)  # inner product == cosine for unit vecs
            index.add(embeddings)
            logger.info("Built FAISS IndexFlatIP with %d vectors (dim=%d).", embeddings.shape[0], dim)
            return index, "faiss"
        except Exception as exc:  # noqa: BLE001
            logger.error("FAISS index build failed: %s — using numpy fallback", exc)

    logger.info("Building NumpyIndex with %d vectors.", embeddings.shape[0])
    return NumpyIndex(embeddings), "numpy"


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------

def _data_checksum() -> str:
    """Hash the modification times of all JSON files to detect staleness."""
    h = hashlib.md5()
    for f in sorted(DATA_DIR.glob("*.json")):
        h.update(str(f.stat().st_mtime).encode())
    return h.hexdigest()


def save_cache(
    index: Any,
    embeddings: np.ndarray,
    metadata: List[Dict[str, Any]],
    method: str,
    index_type: str,
) -> None:
    """Persist the index and metadata to disk."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        np.save(str(EMBEDDINGS_FILE), embeddings)
        payload = {
            "metadata": metadata,
            "method": method,
            "index_type": index_type,
            "checksum": _data_checksum(),
        }
        if index_type == "numpy":
            payload["numpy_embeddings"] = embeddings  # stored in payload for convenience
        else:
            import faiss as _faiss  # noqa: PLC0415
            faiss_bytes = faiss.serialize_index(index)
            payload["faiss_bytes"] = faiss_bytes
        with open(CACHE_FILE, "wb") as fh:
            pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
        logger.info("Saved index cache to %s", CACHE_FILE)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to save cache: %s", exc)


def load_cache() -> Optional[Dict[str, Any]]:
    """
    Load cached index from disk. Returns None if cache is missing or stale.
    """
    if not CACHE_FILE.exists():
        return None
    try:
        with open(CACHE_FILE, "rb") as fh:
            payload = pickle.load(fh)  # noqa: S301
        if payload.get("checksum") != _data_checksum():
            logger.info("Cache checksum mismatch — will rebuild index.")
            return None
        embeddings = np.load(str(EMBEDDINGS_FILE))
        index_type = payload.get("index_type", "numpy")
        if index_type == "faiss" and _FAISS_AVAILABLE:
            import faiss as _faiss  # noqa: PLC0415
            index = faiss.deserialize_index(payload["faiss_bytes"])
        else:
            index = NumpyIndex(embeddings)
            index_type = "numpy"
        logger.info("Loaded index from cache (type=%s, records=%d).", index_type, len(payload["metadata"]))
        return {
            "index": index,
            "embeddings": embeddings,
            "metadata": payload["metadata"],
            "method": payload.get("method", "unknown"),
            "index_type": index_type,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cache load failed: %s — rebuilding.", exc)
        return None


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def initialize_legal_index(force_rebuild: bool = False) -> Dict[str, Any]:
    """
    Main entry-point.  Loads data → generates embeddings → builds index.
    Uses on-disk cache when available and up-to-date.

    Returns a state dict consumed by search_index().
    """
    global _index_state

    if _index_state is not None and not force_rebuild:
        return _index_state

    if not force_rebuild:
        cached = load_cache()
        if cached is not None:
            _index_state = cached
            return _index_state

    logger.info("Building legal search index from scratch …")
    records = load_all_legal_data()
    records = validate_records(records)

    if not records:
        logger.error("No records loaded — index will be empty.")
        _index_state = {
            "index": NumpyIndex(np.zeros((0, 128), dtype=np.float32)),
            "embeddings": np.zeros((0, 128), dtype=np.float32),
            "metadata": [],
            "method": "none",
            "index_type": "numpy",
        }
        return _index_state

    texts = [r["text"] for r in records]
    embeddings, method = generate_embeddings(texts)
    index, index_type = build_faiss_index(embeddings)

    state = {
        "index": index,
        "embeddings": embeddings,
        "metadata": records,
        "method": method,
        "index_type": index_type,
    }
    save_cache(index, embeddings, records, method, index_type)
    _index_state = state
    logger.info(
        "Index ready: %d records, method=%s, backend=%s",
        len(records), method, index_type,
    )
    return _index_state


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_index(
    query: str,
    top_k: int = 5,
    state_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Search the legal index for the top-k most relevant records.

    Args:
        query:        Natural language or keyword query.
        top_k:        Number of results to return.
        state_filter: If given, prefer records from this Indian state.
        type_filter:  If given, filter by record type ('section', 'act', 'state_law', …).

    Returns:
        List of dicts with keys: id, text, metadata, score.
    """
    state = initialize_legal_index()
    index = state["index"]
    metadata = state["metadata"]
    method = state["method"]

    if not metadata:
        return []

    query_vec = embed_query(query, method)

    # Fetch more candidates when filters are active so we have enough after filtering
    fetch_k = top_k * 4 if (state_filter or type_filter) else top_k

    if state["index_type"] == "faiss" and _FAISS_AVAILABLE:
        distances, indices = index.search(
            query_vec.reshape(1, -1),
            min(fetch_k, len(metadata)),
        )
        distances = distances[0]
        indices = indices[0]
    else:
        distances, indices = index.search(query_vec, min(fetch_k, len(metadata)))

    results: List[Dict[str, Any]] = []
    for dist, idx in zip(distances, indices):
        if idx < 0 or idx >= len(metadata):
            continue
        rec = metadata[idx]
        meta = rec.get("metadata", {})

        if type_filter and meta.get("type") != type_filter:
            continue
        if state_filter:
            rec_state = meta.get("state", "")
            if rec_state and rec_state.lower() != state_filter.lower():
                continue

        results.append(
            {
                "id": rec["id"],
                "text": rec["text"],
                "metadata": meta,
                "score": float(dist),
            }
        )
        if len(results) >= top_k:
            break

    return results
