"""
Response Generator for Vani-Kanoon
Generates dialect-aware, simplified legal responses using Google Gemini AI.
Supports multi-language output, citation formatting, and plain-language simplification.
"""

import logging
import os
import re
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gemini AI (required dependency, already in requirements)
# ---------------------------------------------------------------------------
try:
    import google.generativeai as genai
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False
    logger.error("google-generativeai not installed — response generation will be disabled.")

# ---------------------------------------------------------------------------
# Language display names
# ---------------------------------------------------------------------------
_LANGUAGE_NAMES: Dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "kn": "Kannada",
    "mr": "Marathi",
    "ta": "Tamil",
    "te": "Telugu",
    "bn": "Bengali",
    "gu": "Gujarati",
    "pa": "Punjabi",
    "ml": "Malayalam",
    "or": "Odia",
    "ur": "Urdu",
}

# ---------------------------------------------------------------------------
# Dialect-specific prompt instructions
# ---------------------------------------------------------------------------
_DIALECT_INSTRUCTIONS: Dict[str, Dict[str, str]] = {
    "hi": {
        "bhojpuri": (
            "Respond in Bhojpuri Hindi dialect. Use words like 'हम', 'रउरा', 'बाटे', 'हवे'. "
            "Keep sentence structure simple and conversational."
        ),
        "awadhi": (
            "Respond in Awadhi Hindi dialect. Use words like 'हम', 'तोहार', 'हउवे'. "
            "Blend standard Hindi with Awadhi vocabulary."
        ),
        "standard_hindi": "Respond in clear, standard Hindi (मानक हिंदी). Use formal but accessible language.",
    },
    "kn": {
        "bangalore": (
            "Respond in Bangalore Kannada. Mix Kannada with common English words. "
            "Keep it conversational and urban."
        ),
        "hubli": "Respond in Hubli-Dharwad Kannada dialect with North Karnataka vocabulary.",
        "standard_kannada": "Respond in standard literary Kannada (ಶಿಷ್ಟ ಕನ್ನಡ).",
    },
    "mr": {
        "standard_marathi": "Respond in standard Marathi (मराठी). Use clear, formal Marathi.",
        "varhadi": "Respond using Varhadi Marathi dialect vocabulary where natural.",
    },
    "ta": {
        "colloquial_tamil": "Respond in colloquial spoken Tamil. Use everyday vocabulary.",
        "standard_tamil": "Respond in standard written Tamil (தமிழ்).",
    },
    "te": {
        "telangana": "Respond in Telangana Telugu dialect. Use conversational Telangana expressions.",
        "standard_telugu": "Respond in standard Telugu (తెలుగు).",
    },
}

# ---------------------------------------------------------------------------
# System instructions for the legal assistant
# ---------------------------------------------------------------------------
_SYSTEM_INSTRUCTION = """You are Vani-Kanoon, an AI legal assistant specialising in Indian law.

You help ordinary Indian citizens understand their legal rights and options.

Core guidelines:
1. Always cite specific sections, acts, and legal provisions when available in context.
2. Provide practical, actionable advice — not just theory.
3. Remind users to consult a qualified lawyer for their specific situation.
4. Be empathetic, especially for sensitive cases (domestic violence, sexual offences, etc.).
5. Mention free legal aid options (NALSA, DLSA) when relevant.
6. Use accessible language — avoid unnecessary legal jargon.
7. Respect cultural sensitivities and regional contexts.
8. Do NOT provide advice on how to evade the law or help commit crimes.
9. For emergencies, always mention relevant helpline numbers (100, 1091, 181, etc.).
10. Acknowledge the difference between IPC (pre-2024 offences) and BNS (post-July 2024 offences).
"""


class ResponseGenerator:
    """
    Generates legally accurate, dialect-aware responses using Google Gemini AI.
    """

    def __init__(
        self,
        model_name: str = "gemini-2.5-flash",
        api_key: Optional[str] = None,
    ) -> None:
        """
        Initialise the response generator.

        Args:
            model_name: Gemini model identifier.
            api_key:    Gemini API key. Defaults to GEMINI_API_KEY env variable.
        """
        self._model_name = model_name
        self._model: Optional[Any] = None

        resolved_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if _GENAI_AVAILABLE and resolved_key:
            try:
                genai.configure(api_key=resolved_key)
                self._model = genai.GenerativeModel(
                    model_name,
                    system_instruction=_SYSTEM_INSTRUCTION,
                )
                logger.info("ResponseGenerator initialised with model: %s", model_name)
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to initialise Gemini model: %s", exc)
        elif not resolved_key:
            logger.warning("GEMINI_API_KEY not set — response generation disabled.")
        else:
            logger.warning("google-generativeai not available — response generation disabled.")

    # ------------------------------------------------------------------
    # Core response generation
    # ------------------------------------------------------------------

    def generate_legal_response(
        self,
        query: str,
        context: str,
        language: str = "en",
        dialect: Optional[str] = None,
        simplified: bool = False,
        state: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a legal response for the user query with retrieved context.

        Args:
            query:      User's original question.
            context:    Retrieved legal context from RAG service.
            language:   Target response language (BCP-47 code).
            dialect:    Optional dialect for more localised response.
            simplified: If True, use plain language suitable for a layperson.
            state:      Indian state context for jurisdiction-specific info.

        Returns:
            {
                "response": str,      # generated text
                "language": str,
                "dialect": str | None,
                "simplified": bool,
                "model": str,
                "success": bool,
            }
        """
        if self._model is None:
            return {
                "response": self._fallback_message(language),
                "language": language,
                "dialect": dialect,
                "simplified": simplified,
                "model": "none",
                "success": False,
            }

        prompt = self._build_prompt(
            query=query,
            context=context,
            language=language,
            dialect=dialect,
            simplified=simplified,
            state=state,
        )

        try:
            gemini_response = self._model.generate_content(prompt)
            response_text = gemini_response.text.strip()
            return {
                "response": response_text,
                "language": language,
                "dialect": dialect,
                "simplified": simplified,
                "model": self._model_name,
                "success": True,
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Gemini response generation failed: %s", exc)
            return {
                "response": self._fallback_message(language),
                "language": language,
                "dialect": dialect,
                "simplified": simplified,
                "model": self._model_name,
                "success": False,
                "error": str(exc),
            }

    def _build_prompt(
        self,
        query: str,
        context: str,
        language: str,
        dialect: Optional[str],
        simplified: bool,
        state: Optional[str],
    ) -> str:
        """Construct the full prompt string for Gemini."""
        lang_name = _LANGUAGE_NAMES.get(language, language)

        # Language/dialect instruction
        if dialect:
            dialect_map = _DIALECT_INSTRUCTIONS.get(language, {})
            lang_instruction = dialect_map.get(
                dialect,
                f"Respond in {lang_name}.",
            )
        else:
            lang_instruction = f"Respond in {lang_name}."

        # Simplification instruction
        if simplified:
            simplification_instruction = (
                "Explain as if talking to a person with no legal background. "
                "Use very simple words, short sentences, and relatable examples. "
                "Avoid legal jargon; if you must use a legal term, explain it immediately."
            )
        else:
            simplification_instruction = (
                "Use clear, professional language. You may use legal terms but briefly explain them."
            )

        # State context
        state_instruction = ""
        if state:
            state_instruction = (
                f"\nThe user is located in {state}. "
                "Prioritise state-specific laws and local court information from the context."
            )

        prompt = f"""{lang_instruction}
{simplification_instruction}{state_instruction}

--- LEGAL CONTEXT (retrieved from Indian law database) ---
{context}
--- END OF LEGAL CONTEXT ---

User's Question: {query}

Instructions:
- Use the legal context above to answer accurately.
- Cite relevant sections and acts (e.g., "Section 302 IPC" or "Section 103 BNS").
- If the answer requires consulting a lawyer, say so clearly.
- Mention free legal aid if applicable (NALSA helpline: 15100).
- If this is an emergency situation, mention 100 (police), 1091 (women), 181 (domestic violence).
- Structure your answer clearly with numbered steps or bullet points where helpful.
"""
        return prompt.strip()

    # ------------------------------------------------------------------
    # Simplification
    # ------------------------------------------------------------------

    def simplify_legal_language(
        self,
        text: str,
        language: str = "en",
    ) -> Dict[str, Any]:
        """
        Rewrite complex legal text in plain, accessible language.

        Args:
            text:     Legal text to simplify.
            language: Target language for the simplified output.

        Returns:
            {"simplified_text": str, "language": str, "success": bool}
        """
        if self._model is None:
            return {"simplified_text": text, "language": language, "success": False}

        lang_name = _LANGUAGE_NAMES.get(language, language)
        prompt = (
            f"Rewrite the following Indian legal text in very simple {lang_name} "
            "that a 10-year-old child could understand. "
            "Replace legal jargon with everyday words. Keep the core meaning intact.\n\n"
            f"Legal text:\n{text}\n\nSimplified version:"
        )

        try:
            result = self._model.generate_content(prompt)
            return {
                "simplified_text": result.text.strip(),
                "language": language,
                "success": True,
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Simplification failed: %s", exc)
            return {"simplified_text": text, "language": language, "success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Citation formatting
    # ------------------------------------------------------------------

    def format_citations(
        self,
        legal_sections: List[Dict[str, Any]],
    ) -> str:
        """
        Format a list of legal section dicts into a readable citation block.

        Each dict should have keys: act_short, section, title, description, punishment.

        Returns a formatted multi-line citation string.
        """
        if not legal_sections:
            return "No specific legal provisions cited."

        lines: List[str] = []
        for i, sec in enumerate(legal_sections, start=1):
            act = sec.get("act_short") or sec.get("act", "")
            section = sec.get("section")
            title = sec.get("title", "")
            punishment = sec.get("punishment", "")
            state = sec.get("state", "")

            if section:
                ref = f"{act} Section {section}"
                if title:
                    ref += f" — {title}"
            elif state:
                ref = f"{state}: {title or act}"
            else:
                ref = title or act

            citation_line = f"{i}. **{ref}**"
            if punishment:
                citation_line += f"\n   Punishment: {punishment}"
            lines.append(citation_line)

        return "\n".join(lines)

    def format_citation_inline(self, section: Dict[str, Any]) -> str:
        """
        Format a single section dict as a short inline citation.
        Example: "IPC §302 (Murder)" or "BNS §103 (Murder)"
        """
        act = section.get("act_short") or section.get("act", "")
        sec_num = section.get("section", "")
        title = section.get("title", "")
        if sec_num:
            return f"{act} §{sec_num} ({title})" if title else f"{act} §{sec_num}"
        return title or act

    # ------------------------------------------------------------------
    # Translation
    # ------------------------------------------------------------------

    def translate_response(
        self,
        text: str,
        target_language: str,
        source_language: str = "en",
    ) -> Dict[str, Any]:
        """
        Translate a response from source_language to target_language.

        Uses Gemini for translation — maintains legal accuracy and register.

        Returns:
            {"translated": str, "target_language": str, "success": bool}
        """
        if self._model is None:
            return {"translated": text, "target_language": target_language, "success": False}

        if source_language == target_language:
            return {"translated": text, "target_language": target_language, "success": True}

        src_name = _LANGUAGE_NAMES.get(source_language, source_language)
        tgt_name = _LANGUAGE_NAMES.get(target_language, target_language)

        prompt = (
            f"Translate the following legal text from {src_name} to {tgt_name}. "
            "Preserve the legal meaning, section references, and any numbers exactly. "
            "Do NOT add or remove any legal citations.\n\n"
            f"Text to translate:\n{text}\n\nTranslation:"
        )

        try:
            result = self._model.generate_content(prompt)
            return {
                "translated": result.text.strip(),
                "target_language": target_language,
                "source_language": source_language,
                "success": True,
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Translation failed (%s→%s): %s", source_language, target_language, exc)
            return {
                "translated": text,
                "target_language": target_language,
                "success": False,
                "error": str(exc),
            }

    # ------------------------------------------------------------------
    # Structured summaries
    # ------------------------------------------------------------------

    def generate_legal_summary(
        self,
        full_text: str,
        language: str = "en",
        max_sentences: int = 5,
    ) -> Dict[str, Any]:
        """
        Generate a concise bullet-point summary of a legal document or response.

        Args:
            full_text:      Long legal text to summarise.
            language:       Target language.
            max_sentences:  Maximum number of bullet points.

        Returns:
            {"summary": str, "language": str, "success": bool}
        """
        if self._model is None:
            return {"summary": "", "language": language, "success": False}

        lang_name = _LANGUAGE_NAMES.get(language, language)
        prompt = (
            f"Summarise the following Indian legal text in {lang_name}. "
            f"Use at most {max_sentences} bullet points. "
            "Each bullet should be a complete, actionable insight. "
            "Preserve all section and act references.\n\n"
            f"Text:\n{full_text}\n\nSummary (bullet points):"
        )

        try:
            result = self._model.generate_content(prompt)
            return {"summary": result.text.strip(), "language": language, "success": True}
        except Exception as exc:  # noqa: BLE001
            logger.error("Summary generation failed: %s", exc)
            return {"summary": "", "language": language, "success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Next steps
    # ------------------------------------------------------------------

    def generate_next_steps(
        self,
        query: str,
        context: str,
        language: str = "en",
        state: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate practical next steps a user should take based on their query.

        Returns:
            {"steps": List[str], "language": str, "success": bool}
        """
        if self._model is None:
            return {"steps": [], "language": language, "success": False}

        lang_name = _LANGUAGE_NAMES.get(language, language)
        state_clause = f" in {state}" if state else ""
        prompt = (
            f"Based on the user's legal situation below, list exactly 5 clear, numbered next steps "
            f"they should take{state_clause}. Respond in {lang_name}. "
            "Be practical and specific. Mention relevant authorities, helplines, or documents needed.\n\n"
            f"Context:\n{context}\n\nUser query: {query}\n\nNext steps:"
        )

        try:
            result = self._model.generate_content(prompt)
            raw = result.text.strip()
            # Parse numbered list into array
            steps = re.findall(r"\d+[.)]\s*(.+?)(?=\n\d+[.)]|\Z)", raw, re.DOTALL)
            if not steps:
                steps = [line.strip() for line in raw.split("\n") if line.strip()]
            return {"steps": steps, "language": language, "success": True}
        except Exception as exc:  # noqa: BLE001
            logger.error("Next steps generation failed: %s", exc)
            return {"steps": [], "language": language, "success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fallback_message(self, language: str) -> str:
        """Return a safe fallback message when Gemini is unavailable."""
        messages: Dict[str, str] = {
            "en": (
                "I'm unable to generate a response at the moment due to a technical issue. "
                "Please contact NALSA legal aid helpline: 15100 for immediate assistance."
            ),
            "hi": (
                "तकनीकी समस्या के कारण मैं अभी उत्तर नहीं दे सकता। "
                "कृपया NALSA कानूनी सहायता हेल्पलाइन: 15100 पर संपर्क करें।"
            ),
            "kn": (
                "ತಾಂತ್ರಿಕ ಸಮಸ್ಯೆಯಿಂದಾಗಿ ಪ್ರತಿಕ್ರಿಯೆ ನೀಡಲು ಸಾಧ್ಯವಾಗುತ್ತಿಲ್ಲ. "
                "NALSA ಕಾನೂನು ಸಹಾಯ ಸಹಾಯವಾಣಿ: 15100 ಗೆ ಕರೆ ಮಾಡಿ."
            ),
            "mr": (
                "तांत्रिक अडचणीमुळे मी आत्ता उत्तर देऊ शकत नाही. "
                "NALSA कायदेशीर सहाय्य हेल्पलाइन: 15100 वर संपर्क करा."
            ),
            "ta": (
                "தொழில்நுட்ப சிக்கல் காரணமாக பதில் அளிக்க இயலவில்லை. "
                "NALSA சட்ட உதவி ஹெல்ப்லைன்: 15100 அழைக்கவும்."
            ),
            "te": (
                "సాంకేతిక సమస్య కారణంగా ప్రతిస్పందించడం సాధ్యపడటం లేదు. "
                "NALSA చట్టపరమైన సహాయ హెల్ప్‌లైన్: 15100 కి కాల్ చేయండి."
            ),
        }
        return messages.get(language, messages["en"])

    def is_available(self) -> bool:
        """Return True if the Gemini model is initialised and ready."""
        return self._model is not None
