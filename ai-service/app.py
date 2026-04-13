"""
Vani-Kanoon AI Service
Voice-based multilingual legal assistant for India.

Backwards-compatible: original /analyze, /chat, /chat/{session_id} endpoints retained.
"""
import base64
import logging
import os
import uuid

import google.generativeai as genai
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Legacy import (kept for backwards compatibility)
# ---------------------------------------------------------------------------
try:
    from agent import analyze_patient
except ImportError:
    def analyze_patient(symptoms, reports):
        return "Analysis service unavailable."

# ---------------------------------------------------------------------------
# Legal service imports (graceful degradation)
# ---------------------------------------------------------------------------
try:
    from legal_rag_service import LegalRAGService
    rag_service = LegalRAGService()
except Exception as e:
    logging.warning("LegalRAGService unavailable: %s", e)
    rag_service = None

try:
    from speech_service import SpeechService
    speech_service = SpeechService()
except Exception as e:
    logging.warning("SpeechService unavailable: %s", e)
    speech_service = None

try:
    from language_detection import LanguageDetector
    lang_detector = LanguageDetector()
except Exception as e:
    logging.warning("LanguageDetector unavailable: %s", e)
    lang_detector = None

try:
    from legal_processor import LegalProcessor
    legal_processor = LegalProcessor()
except Exception as e:
    logging.warning("LegalProcessor unavailable: %s", e)
    legal_processor = None

try:
    from location_service import LocationService
    location_service = LocationService()
except Exception as e:
    logging.warning("LocationService unavailable: %s", e)
    location_service = None

try:
    from response_generator import ResponseGenerator
    response_generator = ResponseGenerator()
except Exception as e:
    logging.warning("ResponseGenerator unavailable: %s", e)
    response_generator = None

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))

# ---------------------------------------------------------------------------
# Legacy healthcare chat model (backwards compat)
# ---------------------------------------------------------------------------
_legacy_chat_model = genai.GenerativeModel(
    "gemini-2.5-flash",
    system_instruction=(
        "You are ArogyaBot, a specialized medical AI assistant. "
        "You ONLY respond to medical and clinical questions. "
        "Keep responses concise, professional, and clinically accurate. "
        "Always remind doctors to use clinical judgment."
    ),
)

# Legal chat model
_legal_chat_model = genai.GenerativeModel(
    "gemini-2.5-flash",
    system_instruction=(
        "You are VaniBot, an expert legal assistant for India. "
        "You help users understand Indian laws, their rights, and legal procedures. "
        "Cite relevant IPC/BNS sections and applicable acts. "
        "Always add: 'This is legal information, not legal advice. Consult a qualified lawyer.' "
        "Respond in the language specified by the user."
    ),
)

chat_sessions: dict = {}      # legacy sessions
legal_chat_sessions: dict = {}  # legal chat sessions

app = FastAPI(
    title="Vani-Kanoon AI Service",
    description="Voice-based multilingual legal assistant for India",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===========================================================================
# LEGACY ENDPOINTS (backwards compatibility)
# ===========================================================================

@app.post("/analyze")
def analyze(data: dict):
    """Legacy healthcare analysis endpoint."""
    symptoms = data.get("symptoms")
    reports = data.get("reports")
    result = analyze_patient(symptoms, reports)
    return {"analysis": result}


@app.post("/chat")
def chat(data: dict):
    """Legacy healthcare chat endpoint."""
    session_id = data.get("session_id", "default")
    message = data.get("message", "")
    patient_context = data.get("patient_context", "")

    if not message.strip():
        return {"reply": "Please ask a medical question."}

    full_message = message
    if patient_context:
        full_message = f"[Patient Context: {patient_context}]\n\nDoctor's question: {message}"

    if session_id not in chat_sessions:
        chat_sessions[session_id] = _legacy_chat_model.start_chat(history=[])

    session = chat_sessions[session_id]
    try:
        response = session.send_message(full_message)
        return {"reply": response.text}
    except Exception as e:
        return {"reply": f"Sorry, I encountered an error: {str(e)}"}


@app.delete("/chat/{session_id}")
def clear_session(session_id: str):
    """Legacy: clear a healthcare chat session."""
    if session_id in chat_sessions:
        del chat_sessions[session_id]
    return {"status": "cleared"}


# ===========================================================================
# LEGAL ENDPOINTS
# ===========================================================================

@app.post("/legal/query")
def legal_query(data: dict):
    """
    Main legal voice/text query endpoint.
    Input: {query, audio (base64, optional), language, dialect, state, session_id}
    Output: {response, audio_response (base64), citations, language_detected, dialect_detected, query_type}
    """
    query_text: str = data.get("query", "")
    audio_b64: str = data.get("audio", "")
    language: str = data.get("language", "English")
    dialect: str = data.get("dialect", "")
    state: str = data.get("state", "")
    session_id: str = data.get("session_id", str(uuid.uuid4()))

    # --- 1. STT if audio provided ---
    if audio_b64 and speech_service:
        try:
            transcription = speech_service.transcribe_audio(audio_b64, language)
            if transcription.get("text"):
                query_text = transcription["text"]
                if not language or language == "English":
                    language = transcription.get("detected_language", language)
        except Exception as e:
            logger.error("STT failed: %s", e)

    if not query_text.strip():
        raise HTTPException(status_code=400, detail="No query text or audio provided.")

    # --- 2. Language & dialect detection ---
    language_detected = language
    dialect_detected = dialect
    if lang_detector:
        try:
            lang_result = lang_detector.detect_language(query_text)
            if lang_result.get("confidence", 0) > 0.6:
                language_detected = lang_result.get("language", language)
            dialect_result = lang_detector.detect_dialect(query_text, language_detected)
            if not dialect_detected:
                dialect_detected = dialect_result.get("dialect", "")
        except Exception as e:
            logger.error("Language detection failed: %s", e)

    # --- 3. Legal query processing ---
    query_type = "general"
    if legal_processor:
        try:
            proc_result = legal_processor.process_query(query_text, language_detected, state or None)
            query_type = proc_result.get("query_type", "general")
        except Exception as e:
            logger.error("Legal processing failed: %s", e)

    # --- 4. RAG retrieval ---
    legal_context = ""
    if rag_service:
        try:
            sections = rag_service.retrieve_relevant_sections(query_text, language_detected, top_k=5)
            legal_context = rag_service.format_context_for_llm(sections)
        except Exception as e:
            logger.error("RAG retrieval failed: %s", e)

    # --- 5. Response generation ---
    result = {"response_text": "", "audio_url": None, "citations": [], "simplified_explanation": ""}
    if response_generator:
        try:
            result = response_generator.generate_response(
                legal_context, query_text, language_detected, dialect_detected or None, state or None
            )
        except Exception as e:
            logger.error("Response generation failed: %s", e)
            result["response_text"] = f"Error generating response: {str(e)}"

    # --- 6. TTS ---
    audio_response_b64 = ""
    if result.get("response_text") and speech_service:
        try:
            audio_bytes = speech_service.synthesize_speech(
                result["response_text"], language_detected, dialect_detected or None
            )
            if audio_bytes:
                audio_response_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        except Exception as e:
            logger.error("TTS failed: %s", e)

    return {
        "response": result.get("response_text", ""),
        "audio_response": audio_response_b64,
        "citations": result.get("citations", []),
        "simplified_explanation": result.get("simplified_explanation", ""),
        "language_detected": language_detected,
        "dialect_detected": dialect_detected,
        "query_type": query_type,
        "session_id": session_id,
    }


@app.post("/legal/analyze")
def legal_analyze(data: dict):
    """
    Analyze a legal document.
    Input: {document_text, language}
    Output: {summary, key_sections, risks, recommendations}
    """
    document_text: str = data.get("document_text", "")
    language: str = data.get("language", "English")

    if not document_text.strip():
        raise HTTPException(status_code=400, detail="document_text is required.")

    prompt = f"""Analyze the following Indian legal document and provide:
1. A brief summary (2-3 sentences)
2. Key legal sections or clauses identified
3. Potential risks or issues for the party
4. Practical recommendations

Document:
{document_text[:3000]}

Respond in {language}. Structure your response with clear headings."""

    try:
        resp = _legal_chat_model.generate_content(prompt)
        text = resp.text.strip()
        return {
            "summary": text,
            "key_sections": [],
            "risks": [],
            "recommendations": [],
            "full_analysis": text,
        }
    except Exception as e:
        logger.error("Document analysis failed: %s", e)
        raise HTTPException(status_code=500, detail="Document analysis failed. Please try again.")


@app.post("/legal/chat")
def legal_chat(data: dict):
    """
    Conversational legal assistance with session memory.
    Input: {message, language, state, session_id}
    """
    session_id: str = data.get("session_id", "default")
    message: str = data.get("message", "")
    language: str = data.get("language", "English")
    state: str = data.get("state", "")

    if not message.strip():
        return {"reply": "Please ask a legal question."}

    context_prefix = f"[Language: {language}]"
    if state:
        context_prefix += f" [State: {state}]"
    full_message = f"{context_prefix}\nUser: {message}"

    if session_id not in legal_chat_sessions:
        legal_chat_sessions[session_id] = _legal_chat_model.start_chat(history=[])

    session = legal_chat_sessions[session_id]
    try:
        response = session.send_message(full_message)
        return {"reply": response.text, "session_id": session_id}
    except Exception as e:
        logger.error("Legal chat error: %s", e)
        return {"reply": "Sorry, I encountered an error. Please try again.", "session_id": session_id}


@app.get("/legal/state/{state}")
def get_state_laws(state: str):
    """Return state-specific laws and court information."""
    if location_service:
        try:
            laws = location_service.get_state_laws(state)
            courts = location_service.get_local_courts(state)
            return {"state": state, "laws": laws, "courts": courts}
        except Exception as e:
            logger.error("State laws retrieval failed for %s: %s", state, e)
            raise HTTPException(status_code=500, detail="Failed to retrieve state laws.")
    raise HTTPException(status_code=503, detail="Location service unavailable.")


# ===========================================================================
# SPEECH ENDPOINTS
# ===========================================================================

@app.post("/speech/transcribe")
def speech_transcribe(data: dict):
    """
    Speech-to-text.
    Input: {audio: base64_str, language: str}
    Output: {text: str, detected_language: str}
    """
    audio_b64 = data.get("audio", "")
    language = data.get("language", None)

    if not audio_b64:
        raise HTTPException(status_code=400, detail="audio field is required.")

    if speech_service:
        result = speech_service.transcribe_audio(audio_b64, language)
        return {"text": result.get("text", ""), "detected_language": result.get("detected_language", "")}

    raise HTTPException(status_code=503, detail="Speech service unavailable.")


@app.post("/speech/synthesize")
def speech_synthesize(data: dict):
    """
    Text-to-speech.
    Input: {text: str, language: str, dialect: str}
    Output: {audio: base64_str, format: "mp3"}
    """
    text = data.get("text", "")
    language = data.get("language", "English")
    dialect = data.get("dialect", None)

    if not text.strip():
        raise HTTPException(status_code=400, detail="text field is required.")

    if speech_service:
        audio_bytes = speech_service.synthesize_speech(text, language, dialect)
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8") if audio_bytes else ""
        return {"audio": audio_b64, "format": "mp3"}

    raise HTTPException(status_code=503, detail="Speech service unavailable.")


# ===========================================================================
# LANGUAGE ENDPOINT
# ===========================================================================

@app.get("/languages/detect")
def detect_language(text: str = Query(..., description="Text to detect language for")):
    """
    Detect language and dialect from text.
    Output: {language, dialect, script, confidence}
    """
    if not lang_detector:
        raise HTTPException(status_code=503, detail="Language detection service unavailable.")

    try:
        lang_result = lang_detector.detect_language(text)
        dialect_result = lang_detector.detect_dialect(text, lang_result.get("language", "English"))
        return {
            "language": lang_result.get("language", "English"),
            "dialect": dialect_result.get("dialect", ""),
            "region": dialect_result.get("region", ""),
            "script": lang_result.get("script", "Latin"),
            "confidence": lang_result.get("confidence", 0.5),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# HEALTH CHECK
# ===========================================================================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "Vani-Kanoon AI Service",
        "services": {
            "rag": rag_service is not None,
            "speech": speech_service is not None,
            "language_detector": lang_detector is not None,
            "legal_processor": legal_processor is not None,
            "location_service": location_service is not None,
            "response_generator": response_generator is not None,
        },
    }