"""
Legal RAG Service for Vani-Kanoon
Retrieval-Augmented Generation: queries the legal index, ranks results,
and returns formatted context with citations for the language model.
"""

import logging
import re
from typing import Dict, List, Optional, Any

from legal_data_loader import initialize_legal_index, search_index

logger = logging.getLogger(__name__)

# Minimum cosine-similarity score to include a result in context
_MIN_RELEVANCE_SCORE = 0.10


class LegalRAGService:
    """
    Retrieval-Augmented Generation service for Indian legal queries.

    Wraps the legal data loader's search capabilities and formats
    retrieved passages as structured context for an LLM prompt.
    """

    def __init__(self) -> None:
        """Initialise the RAG service and ensure the index is loaded."""
        logger.info("Initialising LegalRAGService …")
        try:
            self._state = initialize_legal_index()
            logger.info(
                "LegalRAGService ready — %d indexed records.",
                len(self._state.get("metadata", [])),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to initialise legal index: %s", exc)
            self._state = {"metadata": [], "index": None, "method": "none"}

    # ------------------------------------------------------------------
    # Core search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        state: Optional[str] = None,
        top_k: int = 5,
        min_score: float = _MIN_RELEVANCE_SCORE,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search over the legal corpus.

        Args:
            query:    User's natural-language question.
            state:    Optional Indian state to bias results toward
                      state-specific laws (e.g. "Maharashtra").
            top_k:    Maximum number of results to return.
            min_score: Minimum relevance score threshold (0–1).

        Returns:
            List of result dicts with keys: id, text, metadata, score.
        """
        if not query or not query.strip():
            logger.warning("Empty query passed to search().")
            return []

        try:
            results = search_index(query, top_k=top_k, state_filter=state)
        except Exception as exc:  # noqa: BLE001
            logger.error("search_index raised an exception: %s", exc)
            return []

        filtered = [r for r in results if r.get("score", 0) >= min_score]

        # If state filter yielded too few results, fall back to global search
        if state and len(filtered) < 2:
            try:
                global_results = search_index(query, top_k=top_k)
                global_filtered = [r for r in global_results if r.get("score", 0) >= min_score]
                # Merge — state results first, then globals that aren't duplicates
                seen_ids = {r["id"] for r in filtered}
                for gr in global_filtered:
                    if gr["id"] not in seen_ids:
                        filtered.append(gr)
                        seen_ids.add(gr["id"])
                filtered = filtered[:top_k]
            except Exception as exc:  # noqa: BLE001
                logger.warning("Fallback global search failed: %s", exc)

        return filtered

    # ------------------------------------------------------------------
    # Context formatting
    # ------------------------------------------------------------------

    def get_context(
        self,
        query: str,
        state: Optional[str] = None,
        top_k: int = 5,
        include_citations: bool = True,
    ) -> Dict[str, Any]:
        """
        Retrieve relevant legal passages and format them as an LLM context block.

        Returns a dict:
            {
                "context_text": str,         # formatted text for the LLM prompt
                "citations": List[dict],     # structured citation list
                "num_sources": int,
                "search_results": List[dict] # raw search results
            }
        """
        results = self.search(query, state=state, top_k=top_k)

        if not results:
            return {
                "context_text": "No relevant legal provisions found in the database.",
                "citations": [],
                "num_sources": 0,
                "search_results": [],
            }

        context_parts: List[str] = []
        citations: List[Dict[str, Any]] = []

        for i, result in enumerate(results, start=1):
            meta = result.get("metadata", {})
            act = meta.get("act", "Unknown Act")
            act_short = meta.get("act_short", act)
            section = meta.get("section")
            title = meta.get("title", "")
            description = meta.get("description", result.get("text", ""))
            punishment = meta.get("punishment", "")
            rec_type = meta.get("type", "")
            state_name = meta.get("state", "")
            score = result.get("score", 0.0)

            # Build the context passage
            if section:
                heading = f"[{i}] {act_short} Section {section}: {title}"
            elif state_name and rec_type == "state_law":
                heading = f"[{i}] {state_name} — {title}"
            else:
                heading = f"[{i}] {title or act}"

            passage_lines = [heading]
            if description:
                passage_lines.append(description)
            if punishment:
                passage_lines.append(f"Punishment: {punishment}")

            context_parts.append("\n".join(passage_lines))

            citation: Dict[str, Any] = {
                "ref_num": i,
                "act": act,
                "act_short": act_short,
                "section": section,
                "title": title,
                "type": rec_type,
                "relevance_score": round(score, 3),
            }
            if state_name:
                citation["state"] = state_name
            citations.append(citation)

        context_text = "\n\n---\n\n".join(context_parts)
        if include_citations:
            refs = ", ".join(
                f"{c['act_short']} §{c['section']}" if c.get("section") else c["act_short"]
                for c in citations
            )
            context_text += f"\n\n[Sources: {refs}]"

        return {
            "context_text": context_text,
            "citations": citations,
            "num_sources": len(results),
            "search_results": results,
        }

    # ------------------------------------------------------------------
    # Direct section look-up
    # ------------------------------------------------------------------

    def get_section_by_number(
        self,
        section_num: str,
        act: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific section by number and optionally by act name.

        Args:
            section_num: Section number, e.g. "302" or "34".
            act:         Act short title, e.g. "IPC", "BNS", "CrPC".
                         If None, searches all acts.

        Returns:
            The matching record dict or None if not found.
        """
        state = self._state
        metadata: List[Dict[str, Any]] = state.get("metadata", [])
        section_num = section_num.strip()

        for rec in metadata:
            meta = rec.get("metadata", {})
            if str(meta.get("section", "")).strip() == section_num:
                if act is None:
                    return rec
                act_short = meta.get("act_short", "").upper()
                if act.upper() in act_short or act_short in act.upper():
                    return rec

        # If not found by exact match, try semantic search as fallback
        query = f"Section {section_num}"
        if act:
            query += f" {act}"
        results = self.search(query, top_k=3)
        for res in results:
            meta = res.get("metadata", {})
            if str(meta.get("section", "")).strip() == section_num:
                if act is None or act.upper() in meta.get("act_short", "").upper():
                    return res
        return None

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    def get_sections_by_keywords(
        self,
        keywords: List[str],
        state: Optional[str] = None,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """Return sections whose metadata keywords overlap with the given list."""
        query = " ".join(keywords)
        return self.search(query, state=state, top_k=top_k)

    def get_acts_summary(self) -> List[Dict[str, str]]:
        """Return a list of unique acts present in the index."""
        state = self._state
        seen: set = set()
        acts: List[Dict[str, str]] = []
        for rec in state.get("metadata", []):
            meta = rec.get("metadata", {})
            act_key = meta.get("act", "")
            if act_key and act_key not in seen:
                seen.add(act_key)
                acts.append(
                    {
                        "act": act_key,
                        "act_short": meta.get("act_short", ""),
                        "type": meta.get("type", ""),
                    }
                )
        return acts

    def format_citation_text(self, citation: Dict[str, Any]) -> str:
        """
        Format a single citation dict into a human-readable reference string.

        Example output: "IPC Section 302 (Murder)"
        """
        act_short = citation.get("act_short") or citation.get("act", "")
        section = citation.get("section")
        title = citation.get("title", "")
        state_name = citation.get("state", "")

        if section:
            ref = f"{act_short} Section {section}"
            if title:
                ref += f" ({title})"
        elif state_name:
            ref = f"{state_name}: {title or act_short}"
        else:
            ref = title or act_short

        return ref

    def build_prompt_context(
        self,
        query: str,
        state: Optional[str] = None,
        top_k: int = 5,
    ) -> str:
        """
        Convenience wrapper — returns a ready-to-embed string for LLM prompts.

        Includes section descriptions and a citation line at the end.
        """
        ctx = self.get_context(query, state=state, top_k=top_k)
        return ctx["context_text"]
