"""
Legal RAG Service - Retrieval Augmented Generation for Indian Legal Database
Uses FAISS for vector search and Google Gemini for embeddings and generation
"""
import json
import os
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    logger.warning("FAISS not available, using simple keyword search fallback")

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

DATA_DIR = Path(__file__).parent / "data"


class LegalRAGService:
    def __init__(self):
        self.sections = []
        self.index = None
        self.embeddings = []
        self._load_all_legal_data()
        if FAISS_AVAILABLE and GEMINI_AVAILABLE:
            self._build_faiss_index()

    def _load_all_legal_data(self):
        """Load all legal data files"""
        for filename, source in [
            ("ipc_sections.json", "IPC"),
            ("bns_sections.json", "BNS"),
        ]:
            path = DATA_DIR / filename
            if path.exists():
                with open(path) as f:
                    data = json.load(f)
                for s in data.get("sections", []):
                    s["source"] = source
                    self.sections.append(s)

        for filename, source_name in [
            ("tenancy_act.json", "Tenancy Act"),
            ("family_law.json", "Family Law"),
            ("property_law.json", "Property Law"),
        ]:
            path = DATA_DIR / filename
            if path.exists():
                with open(path) as f:
                    data = json.load(f)
                self._extract_sections_recursive(data, source_name)

        logger.info(f"Loaded {len(self.sections)} total legal sections")

    def _extract_sections_recursive(self, data, source_name: str, depth: int = 0):
        """Recursively extract sections from nested JSON structure"""
        if depth > 5:
            return
        if isinstance(data, dict):
            if "sections" in data and isinstance(data["sections"], list):
                for s in data["sections"]:
                    if isinstance(s, dict) and ("section" in s or "title" in s):
                        s["source"] = source_name
                        self.sections.append(s)
            for v in data.values():
                self._extract_sections_recursive(v, source_name, depth + 1)
        elif isinstance(data, list):
            for item in data:
                self._extract_sections_recursive(item, source_name, depth + 1)

    def _get_embedding(self, text: str) -> Optional[np.ndarray]:
        """Get embedding for text using Gemini"""
        if not GEMINI_AVAILABLE:
            return None
        try:
            result = genai.embed_content(
                model="models/text-embedding-004",
                content=text,
                task_type="retrieval_document"
            )
            return np.array(result["embedding"], dtype=np.float32)
        except Exception as e:
            logger.error(f"Embedding error: {e}")
            return None

    def _build_faiss_index(self):
        """Build FAISS index from legal sections"""
        if not FAISS_AVAILABLE or not GEMINI_AVAILABLE:
            return
        try:
            embeddings = []
            valid_sections = []
            for section in self.sections:
                text = self._section_to_text(section)
                emb = self._get_embedding(text)
                if emb is not None:
                    embeddings.append(emb)
                    valid_sections.append(section)

            if embeddings:
                matrix = np.stack(embeddings)
                dim = matrix.shape[1]
                self.index = faiss.IndexFlatIP(dim)
                faiss.normalize_L2(matrix)
                self.index.add(matrix)
                self.embeddings = embeddings
                self.sections = valid_sections
                logger.info(f"FAISS index built with {len(valid_sections)} sections")
        except Exception as e:
            logger.error(f"FAISS index build error: {e}")

    def _section_to_text(self, section: Dict) -> str:
        """Convert a section to searchable text"""
        parts = []
        for key in ["title", "description", "keywords", "category", "section"]:
            val = section.get(key)
            if val:
                if isinstance(val, list):
                    parts.append(" ".join(str(v) for v in val))
                else:
                    parts.append(str(val))
        return " ".join(parts)

    def search(self, query: str, top_k: int = 5, state: Optional[str] = None) -> List[Dict]:
        """Search legal sections for a query"""
        if FAISS_AVAILABLE and self.index is not None:
            return self._faiss_search(query, top_k, state)
        return self._keyword_search(query, top_k, state)

    def _faiss_search(self, query: str, top_k: int, state: Optional[str]) -> List[Dict]:
        """FAISS vector search"""
        try:
            query_emb = self._get_embedding(query)
            if query_emb is None:
                return self._keyword_search(query, top_k, state)
            q = query_emb.reshape(1, -1).astype(np.float32)
            faiss.normalize_L2(q)
            scores, indices = self.index.search(q, min(top_k * 2, len(self.sections)))
            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < len(self.sections):
                    section = dict(self.sections[idx])
                    section["relevance_score"] = float(score)
                    results.append(section)
            return results[:top_k]
        except Exception as e:
            logger.error(f"FAISS search error: {e}")
            return self._keyword_search(query, top_k, state)

    def _keyword_search(self, query: str, top_k: int, state: Optional[str]) -> List[Dict]:
        """Fallback keyword search"""
        query_words = set(query.lower().split())
        scored = []
        for section in self.sections:
            text = self._section_to_text(section).lower()
            score = sum(1 for w in query_words if w in text)
            if score > 0:
                s = dict(section)
                s["relevance_score"] = score
                scored.append(s)
        scored.sort(key=lambda x: x["relevance_score"], reverse=True)
        return scored[:top_k]

    def get_context_for_query(self, query: str, state: Optional[str] = None) -> str:
        """Get formatted legal context for a query"""
        results = self.search(query, top_k=5, state=state)
        if not results:
            return "No specific legal sections found for this query."

        context_parts = []
        for r in results:
            source = r.get("source", "Indian Law")
            section_num = r.get("section", "")
            title = r.get("title", "")
            description = r.get("description", "")
            punishment = r.get("punishment", "")

            part = f"[{source}"
            if section_num:
                part += f" Section {section_num}"
            part += f"] {title}: {description}"
            if punishment:
                part += f" Punishment: {punishment}"
            context_parts.append(part)

        return "\n\n".join(context_parts)


_rag_service = None


def get_rag_service() -> LegalRAGService:
    global _rag_service
    if _rag_service is None:
        _rag_service = LegalRAGService()
    return _rag_service
