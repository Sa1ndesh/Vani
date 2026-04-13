import logging
import os
import base64
from typing import Optional

import google.generativeai as genai
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from dotenv import load_dotenv

from agent import analyze_patient

# Vani-Kanoon legal services (imported lazily so startup never fails)
try:
    from legal_rag_service import LegalRAGService
    _rag_service: Optional[LegalRAGService] = None
except ImportError:
    _rag_service = None

try:
    from speech_service import SpeechService
    _speech_service: Optional[SpeechService] = None
except ImportError:
    _speech_service = None

try:
    from language_detection import LanguageDetector
    _lang_detector: Optional[LanguageDetector] = None
except ImportError:
    _lang_detector = None

try:
    from location_service import LocationService
    _location_service: Optional[LocationService] = None
except ImportError:
    _location_service = None

try:
    from response_generator import ResponseGenerator
    _response_generator: Optional[ResponseGenerator] = None
except ImportError:
    _response_generator = None

try:
    from legal_processor import LegalQueryProcessor
    _legal_processor: Optional[LegalQueryProcessor] = None
except ImportError:
    _legal_processor = None

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

chat_model = genai.GenerativeModel(
    "gemini-2.5-flash",
    system_instruction="""You are ArogyaBot, a specialized medical AI assistant.

You have access to:
1. SPECIFIC PATIENT CONTEXT: When provided, you can analyze a single patient's symptoms and reports in detail.
2. GLOBAL PATIENT DATABASE SUMMARY: When provided, you can analyze trends across all patients (e.g., population age, blood group distribution, counting patients with specific characteristics).

You ONLY respond to:
1. Medical and clinical questions
2. Questions about patient data provided in the context (Specific or Global)
3. Medical research and clinical guidelines

If asked about the patient database, use the [GLOBAL PATIENT DATABASE SUMMARY] provided in the context to give accurate counts or summaries.

You REFUSE to answer anything outside the medical/healthcare domain.

Keep responses concise, professional, and clinically accurate. Always remind doctors to use clinical judgment."""
)

chat_sessions = {}

app = FastAPI(
    title="Vani – Multilingual AI Platform",
    description="Healthcare (Arogya-Vahini) + Legal (Vani-Kanoon) AI services",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Lazy service getters
# ---------------------------------------------------------------------------

def get_rag_service() -> "LegalRAGService":
    global _rag_service
    if _rag_service is None:
        from legal_rag_service import LegalRAGService
        _rag_service = LegalRAGService()
    return _rag_service


def get_speech_service() -> "SpeechService":
    global _speech_service
    if _speech_service is None:
        from speech_service import SpeechService
        _speech_service = SpeechService()
    return _speech_service


def get_lang_detector() -> "LanguageDetector":
    global _lang_detector
    if _lang_detector is None:
        from language_detection import LanguageDetector
        _lang_detector = LanguageDetector()
    return _lang_detector


def get_location_service() -> "LocationService":
    global _location_service
    if _location_service is None:
        from location_service import LocationService
        _location_service = LocationService()
    return _location_service


def get_response_generator() -> "ResponseGenerator":
    global _response_generator
    if _response_generator is None:
        from response_generator import ResponseGenerator
        _response_generator = ResponseGenerator()
    return _response_generator


def get_legal_processor() -> "LegalQueryProcessor":
    global _legal_processor
    if _legal_processor is None:
        from legal_processor import LegalQueryProcessor
        _legal_processor = LegalQueryProcessor()
    return _legal_processor


# ===========================================================================
# Healthcare endpoints (Arogya-Vahini – unchanged)
# ===========================================================================

@app.post("/analyze")
def analyze(data: dict):
    symptoms = data.get("symptoms")
    reports = data.get("reports")
    result = analyze_patient(symptoms, reports)
    return {"analysis": result}


@app.post("/chat")
def chat(data: dict):
    session_id = data.get("session_id", "default")
    message = data.get("message", "")
    patient_context = data.get("patient_context", "")

    if not message.strip():
        return {"reply": "Please ask a medical question."}

    full_message = message
    if patient_context:
        full_message = f"[Patient Context: {patient_context}]\n\nDoctor's question: {message}"

    if session_id not in chat_sessions:
        chat_sessions[session_id] = chat_model.start_chat(history=[])

    session = chat_sessions[session_id]

    try:
        response = session.send_message(full_message)
        return {"reply": response.text}
    except Exception as e:
        return {"reply": f"Sorry, I encountered an error: {str(e)}"}


@app.delete("/chat/{session_id}")
def clear_session(session_id: str):
    if session_id in chat_sessions:
        del chat_sessions[session_id]
    return {"status": "cleared"}


# ===========================================================================
# Vani-Kanoon – Legal endpoints
# ===========================================================================

@app.post("/legal/query")
async def legal_query(data: dict):
    """Main legal query endpoint – accepts text + optional metadata."""
    query = data.get("query", "").strip()
    language = data.get("language", "en")
    state = data.get("state")
    simplified = data.get("simplified", False)
    session_id = data.get("session_id", "default")

    if not query:
        raise HTTPException(status_code=400, detail="query field is required")

    try:
        processor = get_legal_processor()
        processed = processor.process_query(query, language=language)

        rag = get_rag_service()
        search_query = processed.get("expanded_query", query)
        results = rag.search(search_query, state=state, top_k=5)
        context = rag.get_context(search_query, state=state)

        gen = get_response_generator()
        answer = gen.generate_legal_response(
            query=query,
            context=context,
            language=language,
            simplified=simplified,
        )

        return {
            "answer": answer,
            "citations": results,
            "language": language,
            "intent": processed.get("intent"),
            "keywords": processed.get("keywords", []),
            "entities": processed.get("entities", {}),
            "session_id": session_id,
        }
    except Exception as e:
        logger.exception("Error processing legal query")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/legal/analyze")
async def legal_analyze(data: dict):
    """Analyze a legal document or text passage."""
    text = data.get("text", "").strip()
    language = data.get("language", "en")

    if not text:
        raise HTTPException(status_code=400, detail="text field is required")

    try:
        processor = get_legal_processor()
        entities = processor.extract_entities(text)
        keywords = processor.extract_keywords(text)

        rag = get_rag_service()
        context = rag.get_context(text)

        gen = get_response_generator()
        analysis = gen.generate_legal_response(
            query=f"Analyze this legal document/text: {text}",
            context=context,
            language=language,
        )

        return {
            "analysis": analysis,
            "entities": entities,
            "keywords": keywords,
            "language": language,
        }
    except Exception as e:
        logger.exception("Error analyzing legal document")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/legal/chat")
async def legal_chat(data: dict):
    """Conversational legal assistance with session history."""
    session_id = data.get("session_id", "default")
    message = data.get("message", "").strip()
    language = data.get("language", "en")
    state = data.get("state")

    if not message:
        raise HTTPException(status_code=400, detail="message field is required")

    try:
        processor = get_legal_processor()
        processed = processor.process_query(message, language=language)

        rag = get_rag_service()
        context = rag.get_context(processed.get("expanded_query", message), state=state)

        gen = get_response_generator()
        reply = gen.generate_legal_response(
            query=message,
            context=context,
            language=language,
        )

        return {
            "reply": reply,
            "session_id": session_id,
            "language": language,
        }
    except Exception as e:
        logger.exception("Error in legal chat")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/legal/state/{state}")
async def get_state_laws(state: str):
    """Return laws and court info specific to a state."""
    try:
        loc = get_location_service()
        laws = loc.get_state_laws(state)
        courts = loc.get_local_courts(state)
        return {
            "state": state,
            "laws": laws,
            "courts": courts,
        }
    except Exception as e:
        logger.exception("Error fetching state laws")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/legal/simplified-explain")
async def simplified_explain(data: dict):
    """Return a plain-language (child-friendly) explanation of a legal concept."""
    query = data.get("query", "").strip()
    section = data.get("section")
    act = data.get("act")
    language = data.get("language", "en")

    if not query and not section:
        raise HTTPException(status_code=400, detail="query or section field is required")

    try:
        rag = get_rag_service()

        if section and act:
            result = rag.get_section_by_number(section, act)
            context = str(result) if result else ""
            text = query or f"Explain Section {section} of {act}"
        else:
            context = rag.get_context(query)
            text = query

        gen = get_response_generator()
        simplified = gen.generate_legal_response(
            query=text,
            context=context,
            language=language,
            simplified=True,
        )

        return {
            "explanation": simplified,
            "section": section,
            "act": act,
            "language": language,
        }
    except Exception as e:
        logger.exception("Error generating simplified explanation")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/legal/search")
async def legal_search(
    q: str = Query(..., description="Search term"),
    state: Optional[str] = Query(None),
    top_k: int = Query(10, ge=1, le=50),
):
    """Full-text search over the legal database."""
    try:
        rag = get_rag_service()
        results = rag.search(q, state=state, top_k=top_k)
        return {"results": results, "query": q, "count": len(results)}
    except Exception as e:
        logger.exception("Error during legal search")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# Speech endpoints
# ===========================================================================

@app.post("/speech/transcribe")
async def speech_transcribe(data: dict):
    """Convert audio (base64-encoded) to text."""
    audio_b64 = data.get("audio")
    language = data.get("language")

    if not audio_b64:
        raise HTTPException(status_code=400, detail="audio field (base64) is required")

    try:
        audio_bytes = base64.b64decode(audio_b64)
        svc = get_speech_service()
        result = svc.transcribe(audio_bytes, language=language)
        return result
    except Exception as e:
        logger.exception("Error transcribing audio")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/speech/synthesize")
async def speech_synthesize(data: dict):
    """Convert text to speech, returns base64-encoded MP3."""
    text = data.get("text", "").strip()
    language = data.get("language", "hi")
    slow = data.get("slow", False)

    if not text:
        raise HTTPException(status_code=400, detail="text field is required")

    try:
        svc = get_speech_service()
        audio_bytes = svc.synthesize(text, language=language, slow=slow)
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        return {"audio": audio_b64, "language": language, "format": "mp3"}
    except Exception as e:
        logger.exception("Error synthesizing speech")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# Language detection endpoint
# ===========================================================================

@app.post("/languages/detect")
async def detect_language(data: dict):
    """Detect language and dialect from text."""
    text = data.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text field is required")

    try:
        detector = get_lang_detector()
        lang_result = detector.detect_language(text)
        dialect_result = detector.detect_dialect(text, lang_result.get("language", "en"))
        script = detector.detect_script(text)
        return {
            "language": lang_result.get("language"),
            "confidence": lang_result.get("confidence"),
            "script": script,
            "dialect": dialect_result,
        }
    except Exception as e:
        logger.exception("Error detecting language")
        raise HTTPException(status_code=500, detail=str(e))