"""
Response Generator - Dialect-aware legal response generation using Gemini
"""
import json
import os
import logging
from typing import Dict, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

DATA_DIR = Path(__file__).parent / "data"


def _load_dialect_mapping() -> Dict:
    path = DATA_DIR / "dialect_mapping.json"
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


DIALECT_MAPPING = _load_dialect_mapping()

SIMPLIFICATION_LEVELS = {
    "layperson": "Explain in simple, everyday language without legal jargon. Use relatable analogies.",
    "educated": "Explain clearly with some technical terms but avoid complex legalese.",
    "professional": "Use proper legal terminology and formal language.",
    "child": "Explain as if to a 10-year-old child. Use very simple words and relatable examples.",
}

LANGUAGE_INSTRUCTIONS = {
    "hindi": "Respond in Hindi (Devanagari script). Use respectful 'aap' form.",
    "kannada": "Respond in Kannada (Kannada script). Use polite form.",
    "marathi": "Respond in Marathi (Devanagari script). Use polite form.",
    "tamil": "Respond in Tamil (Tamil script). Use formal Tamil.",
    "telugu": "Respond in Telugu (Telugu script). Use formal Telugu.",
    "english": "Respond in clear, simple English.",
    "gujarati": "Respond in Gujarati (Gujarati script).",
    "bengali": "Respond in Bengali (Bengali script).",
}


class ResponseGenerator:
    def __init__(self):
        self.model = None
        if GEMINI_AVAILABLE:
            try:
                api_key = os.getenv("GEMINI_API_KEY")
                if api_key:
                    genai.configure(api_key=api_key)
                    self.model = genai.GenerativeModel("gemini-2.5-flash")
                    logger.info("Gemini model loaded for response generation")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini: {e}")

    def generate_legal_response(
        self,
        query: str,
        legal_context: str,
        language: str = "english",
        dialect: str = "standard",
        state: Optional[str] = None,
        state_context: str = "",
        simplification_level: str = "layperson",
        conversation_history: Optional[List[Dict]] = None,
    ) -> str:
        """Generate a dialect-aware legal response"""
        if not self.model:
            return self._fallback_response(query, legal_context, language)

        lang_instruction = LANGUAGE_INSTRUCTIONS.get(language, LANGUAGE_INSTRUCTIONS["english"])
        simplification = SIMPLIFICATION_LEVELS.get(
            simplification_level, SIMPLIFICATION_LEVELS["layperson"]
        )

        dialect_terms = ""
        lang_data = DIALECT_MAPPING.get("languages", {}).get(language, {})
        legal_terms = lang_data.get("legal_terms", {})
        if legal_terms:
            terms_text = ", ".join(
                f"{k}: {v}" for k, v in list(legal_terms.items())[:5]
            )
            dialect_terms = f"Use these local legal terms where appropriate: {terms_text}"

        system_prompt = f"""You are Vani-Kanoon, an AI-powered multilingual legal assistant for India.

You help ordinary Indian citizens understand their legal rights in their native language.

Guidelines:
1. {lang_instruction}
2. {simplification}
3. Always cite specific sections (e.g., "IPC Section 302" or "BNS Section 101")
4. Mention state-specific variations when relevant
5. Always recommend consulting a qualified lawyer for serious matters
6. Be empathetic - users may be in distress
7. {dialect_terms}

IMPORTANT: You ONLY answer questions about Indian law and legal rights. For non-legal questions, politely redirect to legal topics."""

        context_parts = []
        if legal_context:
            context_parts.append(f"[RELEVANT LEGAL SECTIONS]\n{legal_context}")
        if state_context:
            context_parts.append(f"[STATE-SPECIFIC CONTEXT for {state}]\n{state_context}")

        full_query = query
        if context_parts:
            full_query = "\n\n".join(context_parts) + f"\n\n[USER QUERY]\n{query}"

        try:
            temp_model = genai.GenerativeModel(
                "gemini-2.5-flash",
                system_instruction=system_prompt,
            )
            if conversation_history:
                history = [
                    {"role": msg["role"], "parts": [msg["content"]]}
                    for msg in conversation_history[-10:]
                ]
                chat = temp_model.start_chat(history=history)
                response = chat.send_message(full_query)
            else:
                response = temp_model.generate_content(full_query)
            return response.text
        except Exception as e:
            logger.error(f"Response generation error: {e}")
            return self._fallback_response(query, legal_context, language)

    def generate_simplified_explanation(
        self, legal_text: str, language: str = "english"
    ) -> str:
        """Generate a simplified explanation of legal text"""
        if not self.model:
            return "Explanation service unavailable. Please configure GEMINI_API_KEY."

        lang_instruction = LANGUAGE_INSTRUCTIONS.get(language, LANGUAGE_INSTRUCTIONS["english"])
        prompt = (
            f"Explain the following legal text to a common person in India as if they are 10 years old.\n"
            f"{lang_instruction}\n"
            f"Use simple words, analogies from daily life, and give practical examples.\n\n"
            f"Legal text:\n{legal_text}"
        )

        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Simplification error: {e}")
            return f"Could not simplify: {str(e)}"

    def _fallback_response(self, query: str, context: str, language: str) -> str:
        """Simple fallback when AI is unavailable"""
        return (
            f"Query received: {query}\n\n"
            f"Relevant legal information:\n{context}\n\n"
            "Note: AI response generation is currently unavailable. "
            "Please configure GEMINI_API_KEY and ensure google-generativeai is installed. "
            "Consult a qualified legal professional for advice."
        )


_generator = None


def get_response_generator() -> ResponseGenerator:
    global _generator
    if _generator is None:
        _generator = ResponseGenerator()
    return _generator
