"""
Dialect-aware response generator for Vani-Kanoon.
Uses Google Gemini to produce legal responses in the user's language and dialect.
"""
import json
import logging
import os
from typing import Optional

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))

DIALECT_TONE_MAP = {
    "formal_slightly_rough": "Use formal Kannada with a direct, slightly assertive tone typical of North Karnataka.",
    "urban_mixed_english":   "Use conversational urban Kannada, may mix some English words naturally.",
    "formal_coastal":        "Use formal Kannada with clear, measured speech appropriate for Coastal Karnataka.",
    "formal_traditional":    "Use respectful, traditional Kannada with honorifics (ಅವರು, ನೀವು).",
    "informal_rural":        "Use simple, empathetic Hindi with rural Bhojpuri-influenced phrasing where natural.",
    "informal_rustic":       "Use warm, direct Hindi with Rajasthani flavour.",
    "urban_direct":          "Use clear, modern Delhi Hindi, concise and professional.",
    "courtly_formal":        "Use Lucknowi courtly Hindi with respectful address (जनाब, आप).",
    "urban_fast_paced":      "Use conversational Mumbai Marathi, keep it brief and practical.",
    "educated_formal":       "Use educated Pune Marathi with proper grammar.",
    "rural_direct":          "Use straightforward Vidarbha Marathi.",
    "coastal_warm":          "Use warm Konkan Marathi.",
    "formal_urban":          "Use standard Chennai Tamil, polite and clear.",
    "informal_assertive":    "Use confident Madurai Tamil, direct but respectful.",
    "business_practical":    "Use practical Coimbatore Tamil, focused on solutions.",
    "urban_mixed_urdu":      "Use Hyderabadi Telugu with light Urdu influence.",
    "formal_coastal":        "Use formal Coastal Andhra Telugu.",
    "rural_respectful":      "Use respectful Rayalaseema Telugu.",
    "formal_polite":         "Use professional, courteous Indian English.",
}

LANGUAGE_INSTRUCTION = {
    "Kannada":  "Respond primarily in Kannada script (ಕನ್ನಡ). Use simple, clear Kannada.",
    "Hindi":    "Respond primarily in Hindi (हिंदी). Use simple, clear Hindi.",
    "Marathi":  "Respond primarily in Marathi (मराठी). Use simple, clear Marathi.",
    "Tamil":    "Respond primarily in Tamil (தமிழ்). Use simple, clear Tamil.",
    "Telugu":   "Respond primarily in Telugu (తెలుగు). Use simple, clear Telugu.",
    "English":  "Respond in clear, simple English.",
}


class ResponseGenerator:
    def __init__(self):
        self._model = None
        self._init_model()

    def _init_model(self) -> None:
        try:
            self._model = genai.GenerativeModel(
                "gemini-2.5-flash",
                system_instruction=self._system_instruction(),
            )
            logger.info("Gemini model initialized for ResponseGenerator.")
        except Exception as e:
            logger.error("Failed to initialize Gemini model: %s", e)

    @staticmethod
    def _system_instruction() -> str:
        return """You are VaniBot, an expert legal assistant for India.

You have deep knowledge of:
1. Indian Penal Code (IPC) and Bharatiya Nyaya Sanhita (BNS) 2023
2. Civil law, property law, tenancy laws
3. Family law (Hindu, Muslim, Christian, Special Marriage Act)
4. State-specific laws across Karnataka, Maharashtra, Tamil Nadu, Delhi, Telangana, etc.
5. Constitutional rights of Indian citizens
6. Court hierarchy and procedure (FIR filing, bail, appeals)

Guidelines:
- Always respond in the language specified by the user
- Cite specific sections of law (e.g., "IPC Section 302" or "BNS Section 103")
- Be empathetic and non-judgmental
- Provide practical next steps (file FIR, approach district court, etc.)
- Add a disclaimer: "This is legal information, not legal advice. Consult a qualified lawyer for your specific case."
- Keep explanations simple and accessible
- If the question is outside legal domain, politely redirect to legal matters"""

    # ------------------------------------------------------------------
    # Main response generation
    # ------------------------------------------------------------------

    def generate_response(
        self,
        legal_context: str,
        query: str,
        language: str,
        dialect: Optional[str] = None,
        state: Optional[str] = None,
    ) -> dict:
        """
        Generate a legal response using Gemini.
        Returns {
            "response_text": str,
            "audio_url": None,
            "citations": [...],
            "simplified_explanation": str,
        }
        """
        if self._model is None:
            return self._fallback_response(query)

        try:
            prompt = self.build_prompt(query, legal_context, language, dialect, state)
            response = self._model.generate_content(prompt)
            raw_text = response.text.strip() if response.text else ""

            formatted = self.format_legal_response(raw_text, language)
            citations = self._extract_citations(raw_text)
            simplified = self.generate_simplified_explanation(raw_text, language)

            return {
                "response_text": formatted,
                "audio_url": None,
                "citations": citations,
                "simplified_explanation": simplified,
            }
        except Exception as e:
            logger.error("Response generation failed: %s", e)
            return self._fallback_response(query, error=str(e))

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def build_prompt(
        self,
        query: str,
        context: str,
        language: str,
        dialect: Optional[str],
        state: Optional[str],
    ) -> str:
        lang_instr = LANGUAGE_INSTRUCTION.get(language, LANGUAGE_INSTRUCTION["English"])
        dialect_instr = self.get_dialect_instructions(language, dialect)
        state_clause = f"The user is from {state}. Apply relevant {state} state laws where applicable." if state else ""

        prompt = f"""
{lang_instr}
{dialect_instr}
{state_clause}

{context}

USER QUESTION: {query}

Please answer the above legal question:
1. Briefly explain the relevant law(s) with section numbers
2. State the user's rights and options
3. Suggest practical steps (FIR filing, court approach, lawyer consultation)
4. Include a brief disclaimer about consulting a lawyer

Keep the response clear, organized, and under 400 words.
""".strip()
        return prompt

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_dialect_instructions(
        self, language: str, dialect: Optional[str]
    ) -> str:
        """Build a tone instruction string based on language and dialect."""
        if not dialect:
            return ""
        # Try to find tone for this dialect
        try:
            path = os.path.join(os.path.dirname(__file__), "data", "dialect_mapping.json")
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            lang_data = data.get("languages", {}).get(language, {})
            for d in lang_data.get("dialects", []):
                if d["name"].lower() == dialect.lower() or dialect.lower() in d["name"].lower():
                    tone = d.get("tone", "")
                    return DIALECT_TONE_MAP.get(tone, f"Use {dialect} tone.")
        except Exception:
            pass
        return f"Use a tone appropriate for {dialect} dialect."

    def format_legal_response(self, response: str, language: str) -> str:
        """Light post-processing: ensure disclaimer is present."""
        disclaimer_map = {
            "Hindi":   "\n\n⚠️ यह कानूनी जानकारी है, कानूनी सलाह नहीं। अपने मामले के लिए एक योग्य वकील से परामर्श करें।",
            "Kannada": "\n\n⚠️ ಇದು ಕಾನೂನು ಮಾಹಿತಿ ಮಾತ್ರ, ಕಾನೂನು ಸಲಹೆ ಅಲ್ಲ। ನಿಮ್ಮ ಪ್ರಕರಣಕ್ಕೆ ಅರ್ಹ ವಕೀಲರನ್ನು ಸಂಪರ್ಕಿಸಿ।",
            "Marathi":  "\n\n⚠️ ही कायदेशीर माहिती आहे, कायदेशीर सल्ला नाही। आपल्या प्रकरणासाठी पात्र वकिलाचा सल्ला घ्या।",
            "Tamil":    "\n\n⚠️ இது சட்ட தகவல் மட்டுமே, சட்ட ஆலோசனை அல்ல. உங்கள் வழக்கிற்கு தகுதியான வழக்கறிஞரை அணுகுங்கள்.",
            "Telugu":   "\n\n⚠️ ఇది చట్ట సమాచారం మాత్రమే, చట్ట సలహా కాదు. మీ కేసు కోసం అర్హత కలిగిన న్యాయవాదిని సంప్రదించండి.",
            "English":  "\n\n⚠️ This is legal information, not legal advice. Please consult a qualified lawyer for your specific case.",
        }
        disclaimer = disclaimer_map.get(language, disclaimer_map["English"])
        if "⚠️" not in response and "disclaimer" not in response.lower():
            response += disclaimer
        return response

    def generate_simplified_explanation(self, legal_text: str, language: str) -> str:
        """Generate a plain-language version using Gemini."""
        if self._model is None or not legal_text.strip():
            return ""
        try:
            lang_instr = LANGUAGE_INSTRUCTION.get(language, LANGUAGE_INSTRUCTION["English"])
            prompt = f"""{lang_instr}

Summarize the following legal text in 2-3 simple sentences that a non-lawyer can understand. Use the simplest possible language.

Legal text:
{legal_text[:1500]}
"""
            resp = self._model.generate_content(prompt)
            return resp.text.strip() if resp.text else ""
        except Exception as e:
            logger.error("Simplified explanation generation failed: %s", e)
            return ""

    @staticmethod
    def _extract_citations(text: str) -> list[dict]:
        """Extract legal section references from the response text."""
        import re
        patterns = [
            r"(?:IPC|BNS|Section|Sec\.?)\s+\d+[A-Z]?(?:\s*\([a-z]\))?",
            r"(?:Hindu Marriage Act|Transfer of Property Act|RERA|Special Marriage Act|Domestic Violence Act|CrPC|CPC)\s*(?:Section|Sec\.?)?\s*\d*",
        ]
        citations = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for m in matches:
                m = m.strip()
                if m and m not in [c["reference"] for c in citations]:
                    citations.append({"reference": m, "context": ""})
        return citations[:10]  # cap at 10

    @staticmethod
    def _fallback_response(query: str, error: str = "") -> dict:
        return {
            "response_text": (
                "I'm sorry, I'm unable to process your query at the moment. "
                "Please try again or consult a qualified lawyer.\n\n"
                f"{'Error: ' + error if error else ''}"
            ).strip(),
            "audio_url": None,
            "citations": [],
            "simplified_explanation": "",
        }
