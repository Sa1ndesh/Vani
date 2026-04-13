"""
Legal RAG (Retrieval-Augmented Generation) Service for Vani-Kanoon.
Uses FAISS vector store with multilingual sentence embeddings for semantic search.
Falls back to keyword search when FAISS/sentence-transformers are unavailable.
"""
import json
import os
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    logger.warning("sentence-transformers not available; falling back to keyword search.")

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    logger.warning("faiss-cpu not available; falling back to keyword search.")


class LegalRAGService:
    def __init__(self):
        self.documents: list[dict] = []
        self.index = None
        self.embeddings_model = None
        self._load_legal_documents()
        if EMBEDDINGS_AVAILABLE and FAISS_AVAILABLE:
            try:
                self.embeddings_model = SentenceTransformer(
                    "paraphrase-multilingual-MiniLM-L12-v2"
                )
                self._build_vector_store()
            except Exception as exc:
                logger.error("Failed to build vector store: %s", exc)

    # ------------------------------------------------------------------
    # Document loading
    # ------------------------------------------------------------------

    def _load_json_file(self, filename: str) -> dict:
        path = os.path.join(DATA_DIR, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error("Could not load %s: %s", filename, e)
            return {}

    def _load_legal_documents(self) -> None:
        """Load all JSON data files and flatten them into self.documents."""
        self.documents = []

        # IPC sections
        ipc_data = self._load_json_file("ipc_sections.json")
        for sec in ipc_data.get("sections", []):
            self.documents.append({
                "id": sec.get("section", ""),
                "title": sec.get("title", ""),
                "text": f"{sec.get('section', '')} - {sec.get('title', '')}: {sec.get('description', '')} Punishment: {sec.get('punishment', '')}",
                "source": "IPC",
                "keywords": sec.get("keywords", []),
                "raw": sec,
            })

        # BNS sections
        bns_data = self._load_json_file("bns_sections.json")
        for sec in bns_data.get("sections", []):
            self.documents.append({
                "id": sec.get("section", ""),
                "title": sec.get("title", ""),
                "text": f"{sec.get('section', '')} - {sec.get('title', '')}: {sec.get('description', '')} Punishment: {sec.get('punishment', '')}",
                "source": "BNS",
                "keywords": sec.get("keywords", []),
                "raw": sec,
            })

        # Tenancy act
        tenancy_data = self._load_json_file("tenancy_act.json")
        mta = tenancy_data.get("model_tenancy_act", {})
        for sec in mta.get("sections", []):
            self.documents.append({
                "id": sec.get("section", ""),
                "title": sec.get("title", ""),
                "text": f"{sec.get('section', '')} - {sec.get('title', '')}: {sec.get('description', '')}",
                "source": "Tenancy Law",
                "keywords": sec.get("keywords", []),
                "raw": sec,
            })
        for state, info in tenancy_data.get("state_variations", {}).items():
            self.documents.append({
                "id": f"Tenancy-{state}",
                "title": f"{state} Tenancy Law",
                "text": f"{state} Tenancy: {info.get('act_name', '')}. Security deposit: {info.get('security_deposit', '')}. Notice period: {info.get('notice_period', '')}. {' '.join(info.get('key_provisions', []))}",
                "source": "State Tenancy",
                "keywords": ["tenancy", "rent", state.lower(), "landlord", "tenant"],
                "raw": info,
            })

        # Family law
        family_data = self._load_json_file("family_law.json")
        for act in family_data.get("acts", []):
            act_name = act.get("act_name", "")
            for sec in act.get("sections", []):
                self.documents.append({
                    "id": sec.get("section", ""),
                    "title": f"{act_name} - {sec.get('title', '')}",
                    "text": f"{act_name}, {sec.get('section', '')} - {sec.get('title', '')}: {sec.get('description', '')}",
                    "source": act_name,
                    "keywords": sec.get("keywords", []),
                    "raw": sec,
                })

        # Property law
        property_data = self._load_json_file("property_law.json")
        for act in property_data.get("acts", []):
            act_name = act.get("act_name", "")
            for sec in act.get("sections", []):
                self.documents.append({
                    "id": sec.get("section", ""),
                    "title": f"{act_name} - {sec.get('title', '')}",
                    "text": f"{act_name}, {sec.get('section', '')} - {sec.get('title', '')}: {sec.get('description', '')}",
                    "source": act_name,
                    "keywords": sec.get("keywords", []),
                    "raw": sec,
                })

        # State laws
        state_data = self._load_json_file("state_laws.json")
        for state, info in state_data.get("states", {}).items():
            court_text = "; ".join(
                f"{c['name']} ({c['jurisdiction']})"
                for c in info.get("courts", [])
            )
            acts_text = ", ".join(info.get("key_acts", []))
            tenancy_info = info.get("tenancy", {})
            self.documents.append({
                "id": f"State-{state}",
                "title": f"{state} State Laws Overview",
                "text": f"{state}: Key acts: {acts_text}. Courts: {court_text}. Tenancy: {tenancy_info.get('act', '')}. Stamp duty on sale: {info.get('stamp_duty', {}).get('sale_deed', '')}.",
                "source": "State Laws",
                "keywords": ["state law", state.lower(), "courts", "jurisdiction"],
                "raw": info,
            })

        logger.info("Loaded %d legal documents.", len(self.documents))

    # ------------------------------------------------------------------
    # Vector store
    # ------------------------------------------------------------------

    def _build_vector_store(self) -> None:
        """Build a FAISS index from document texts."""
        if not FAISS_AVAILABLE or not EMBEDDINGS_AVAILABLE or not self.embeddings_model:
            return
        try:
            texts = [doc["text"] for doc in self.documents]
            vectors = self.embeddings_model.encode(texts, show_progress_bar=False)
            dim = vectors.shape[1]
            self.index = faiss.IndexFlatL2(dim)
            self.index.add(vectors.astype("float32"))
            logger.info("FAISS index built with %d vectors (dim=%d).", len(texts), dim)
        except Exception as exc:
            logger.error("Vector store build failed: %s", exc)
            self.index = None

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def retrieve_relevant_sections(
        self, query: str, language: str = "en", top_k: int = 5
    ) -> list[dict]:
        """Return the top_k most relevant legal sections for *query*."""
        if self.index is not None and self.embeddings_model is not None:
            return self._semantic_search(query, top_k)
        return self._keyword_search(query, top_k)

    def _semantic_search(self, query: str, top_k: int) -> list[dict]:
        try:
            vec = self.embeddings_model.encode([query])
            distances, indices = self.index.search(vec.astype("float32"), top_k)
            results = []
            for idx, dist in zip(indices[0], distances[0]):
                if 0 <= idx < len(self.documents):
                    doc = self.documents[idx].copy()
                    doc["score"] = float(dist)
                    results.append(doc)
            return results
        except Exception as exc:
            logger.error("Semantic search failed: %s", exc)
            return self._keyword_search(query, top_k)

    def _keyword_search(self, query: str, top_k: int) -> list[dict]:
        """Simple TF-style keyword overlap fallback."""
        query_tokens = set(re.findall(r"\w+", query.lower()))
        scored = []
        for doc in self.documents:
            doc_text = (doc["text"] + " " + " ".join(doc.get("keywords", []))).lower()
            doc_tokens = set(re.findall(r"\w+", doc_text))
            overlap = len(query_tokens & doc_tokens)
            if overlap:
                scored.append((overlap, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, doc in scored[:top_k]:
            d = doc.copy()
            d["score"] = score
            results.append(d)
        return results

    # ------------------------------------------------------------------
    # Context formatting
    # ------------------------------------------------------------------

    def format_context_for_llm(self, sections: list[dict]) -> str:
        """Format retrieved sections into a readable context block for the LLM."""
        if not sections:
            return "No specific legal sections found for this query."
        lines = ["RELEVANT LEGAL PROVISIONS:\n"]
        for i, sec in enumerate(sections, 1):
            lines.append(f"{i}. [{sec.get('source', 'Law')}] {sec.get('title', sec.get('id', ''))}")
            # Trim long text
            text = sec.get("text", "")
            if len(text) > 600:
                text = text[:600] + "..."
            lines.append(f"   {text}")
            lines.append("")
        return "\n".join(lines)

    def get_document_count(self) -> int:
        return len(self.documents)
