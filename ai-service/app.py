import base64
import logging
import os

import google.generativeai as genai
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from agent import analyze_patient
from language_detection import get_language_detector
from legal_data_loader import get_summary as get_data_summary
from legal_processor import get_legal_processor
from legal_rag_service import get_rag_service
from location_service import get_location_service
from response_generator import get_response_generator
from speech_service import get_speech_service

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))

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
legal_chat_sessions = {}

app = FastAPI(
    title="Vani AI Service",
    description="AI service for Vani-Kanoon legal assistant and Arogya-Vahini healthcare system",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# EXISTING HEALTHCARE ENDPOINTS (unchanged)
# ============================================================


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

    # Include patient context if provided
    full_message = message
    if patient_context:
        full_message = f"[Patient Context: {patient_context}]\n\nDoctor's question: {message}"

    # Get or create chat session
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


# ============================================================
# VANI-KANOON LEGAL ASSISTANT ENDPOINTS
# ============================================================


@app.get("/legal/health")
def legal_health():
    """Health check for legal assistant service"""
    summary = get_data_summary()
    return {
        "status": "ok",
        "service": "Vani-Kanoon Legal Assistant",
        "data_loaded": summary["all_ok"],
        "total_legal_sections": summary["total_sections"],
        "features": [
            "RAG legal search",
            "Multi-language support",
            "Dialect detection",
            "State-specific laws",
            "Simplified explanations",
            "Voice STT/TTS",
        ],
    }


@app.post("/legal/query")
def legal_query(data: dict):
    """Main legal query endpoint - processes voice or text queries"""
    query = data.get("query", "").strip()
    language = data.get("language", "english").lower()
    dialect = data.get("dialect", "standard").lower()
    state = data.get("state", "")
    simplification = data.get("simplification_level", "layperson")
    session_id = data.get("session_id", "default")
    audio_base64_input = data.get("audio_base64", "")

    if not query and not audio_base64_input:
        raise HTTPException(
            status_code=400, detail="Either 'query' text or 'audio_base64' is required"
        )

    # If audio provided, transcribe first
    if audio_base64_input and not query:
        try:
            audio_bytes = base64.b64decode(audio_base64_input)
            stt_result = get_speech_service().transcribe(audio_bytes, language)
            query = stt_result.get("text", "")
            if not query:
                raise HTTPException(status_code=422, detail="Could not transcribe audio")
            if stt_result.get("language"):
                language = stt_result["language"]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Audio transcription failed: {str(e)}")

    # Detect language if set to auto
    if language == "auto" or not language:
        detection = get_language_detector().detect(query)
        language = detection["language"]
        dialect = detection.get("dialect", "standard")

    # Infer state from language if not provided
    if not state:
        state = get_location_service().get_state_from_language(language) or ""

    # Process query
    processed = get_legal_processor().process(query, language, state)

    # Get relevant legal context via RAG
    legal_context = get_rag_service().get_context_for_query(query, state=state or None)

    # Get state-specific context
    state_context = ""
    if state:
        state_context = get_location_service().get_legal_context(state, processed["categories"])

    # Get conversation history
    history = legal_chat_sessions.get(session_id, [])

    # Generate response
    response_text = get_response_generator().generate_legal_response(
        query=query,
        legal_context=legal_context,
        language=language,
        dialect=dialect,
        state=state or None,
        state_context=state_context,
        simplification_level=simplification,
        conversation_history=history,
    )

    # Update conversation history (keep last 20 messages)
    if session_id not in legal_chat_sessions:
        legal_chat_sessions[session_id] = []
    legal_chat_sessions[session_id].append({"role": "user", "content": query})
    legal_chat_sessions[session_id].append({"role": "model", "content": response_text})
    legal_chat_sessions[session_id] = legal_chat_sessions[session_id][-20:]

    return {
        "query": query,
        "response": response_text,
        "language": language,
        "dialect": dialect,
        "state": state,
        "categories": processed["categories"],
        "section_references": processed["section_references"],
        "legal_sections_used": len(processed["specific_sections"]),
        "session_id": session_id,
    }


@app.post("/legal/analyze")
def analyze_legal_document(data: dict):
    """Analyze a legal document and extract key information"""
    document_text = data.get("text", "").strip()
    language = data.get("language", "english")
    state = data.get("state", "")

    if not document_text:
        raise HTTPException(status_code=400, detail="'text' field is required")

    query = (
        f"Analyze this legal document and explain its key points, "
        f"rights, and obligations: {document_text[:2000]}"
    )
    legal_context = get_rag_service().get_context_for_query(document_text[:500])
    processed = get_legal_processor().process(document_text, language, state)

    response_text = get_response_generator().generate_legal_response(
        query=query,
        legal_context=legal_context,
        language=language,
        state=state or None,
        simplification_level="educated",
    )

    return {
        "analysis": response_text,
        "categories": processed["categories"],
        "section_references": processed["section_references"],
        "language": language,
    }


@app.post("/legal/chat")
def legal_chat(data: dict):
    """Conversational legal assistance with session history"""
    return legal_query(data)


@app.get("/legal/state/{state}")
def get_state_laws(state: str):
    """Get state-specific legal information"""
    state_laws = get_location_service().get_state_laws(state)
    tenancy_laws = get_location_service().get_tenancy_laws(state)

    if not state_laws and not tenancy_laws.get("state_specific"):
        raise HTTPException(status_code=404, detail=f"State '{state}' not found in database")

    return {"state": state, "laws": state_laws, "tenancy": tenancy_laws}


@app.post("/speech/transcribe")
async def transcribe_speech(
    file: UploadFile = File(...), language: str = Query("auto")
):
    """Convert speech audio to text (STT)"""
    audio_bytes = await file.read()
    lang = None if language == "auto" else language
    result = get_speech_service().transcribe(audio_bytes, lang)
    return {
        "text": result.get("text", ""),
        "language": result.get("language", "unknown"),
        "error": result.get("error"),
    }


@app.post("/speech/synthesize")
def synthesize_speech(data: dict):
    """Convert text to speech (TTS)"""
    text = data.get("text", "").strip()
    language = data.get("language", "english")

    if not text:
        raise HTTPException(status_code=400, detail="'text' field is required")

    result = get_speech_service().synthesize(text, language)
    return {
        "audio_base64": result.get("audio_base64", ""),
        "format": result.get("format", "mp3"),
        "language": language,
        "error": result.get("error"),
    }


@app.get("/languages/detect")
def detect_language(text: str = Query(..., description="Text to detect language for")):
    """Detect language and dialect from text"""
    if not text.strip():
        raise HTTPException(status_code=400, detail="'text' query parameter is required")
    return get_language_detector().detect(text)


@app.get("/legal/search")
def search_legal_database(
    q: str = Query(..., description="Search query"),
    state: str = Query(None, description="Filter by state"),
    top_k: int = Query(5, description="Number of results", ge=1, le=20),
):
    """Search the legal database"""
    if not q.strip():
        raise HTTPException(status_code=400, detail="'q' query parameter is required")

    results = get_rag_service().search(q, top_k=top_k, state=state)
    return {"query": q, "results": results, "count": len(results)}


@app.post("/legal/simplified-explain")
def simplified_explanation(data: dict):
    """Generate a simplified explanation of legal text"""
    text = data.get("text", "").strip()
    language = data.get("language", "english")

    if not text:
        raise HTTPException(status_code=400, detail="'text' field is required")

    explanation = get_response_generator().generate_simplified_explanation(text, language)
    return {"original": text, "simplified": explanation, "language": language}


@app.delete("/legal/chat/{session_id}")
def clear_legal_session(session_id: str):
    """Clear a legal chat session"""
    if session_id in legal_chat_sessions:
        del legal_chat_sessions[session_id]
    return {"status": "cleared", "session_id": session_id}


@app.get("/legal/data/status")
def legal_data_status():
    """Get status of loaded legal data"""
    return get_data_summary()