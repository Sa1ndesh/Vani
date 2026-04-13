"""
Speech Service - STT and TTS for multilingual Indian languages
Uses OpenAI Whisper for STT and gTTS for TTS
"""
import os
import io
import base64
import logging
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    logger.warning("Whisper not available")

try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False
    logger.warning("gTTS not available")

LANGUAGE_CODES = {
    "hindi": "hi",
    "kannada": "kn",
    "marathi": "mr",
    "tamil": "ta",
    "telugu": "te",
    "english": "en",
    "gujarati": "gu",
    "bengali": "bn",
    "punjabi": "pa",
    "malayalam": "ml",
    "odia": "or",
    "assamese": "as",
}


class SpeechService:
    def __init__(self):
        self.whisper_model = None
        if WHISPER_AVAILABLE:
            try:
                model_size = os.getenv("WHISPER_MODEL", "base")
                self.whisper_model = whisper.load_model(model_size)
                logger.info(f"Whisper model '{model_size}' loaded")
            except Exception as e:
                logger.error(f"Failed to load Whisper: {e}")

    def transcribe(self, audio_data: bytes, language: Optional[str] = None) -> dict:
        """Transcribe audio to text"""
        if not WHISPER_AVAILABLE or self.whisper_model is None:
            return {
                "text": "",
                "language": language or "unknown",
                "error": "Whisper STT not available. Please install openai-whisper."
            }

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False,
                                              dir=os.path.dirname(os.path.abspath(__file__))) as f:
                f.write(audio_data)
                tmp_path = f.name

            whisper_lang = None
            if language and language in LANGUAGE_CODES:
                whisper_lang = LANGUAGE_CODES[language]

            result = self.whisper_model.transcribe(
                tmp_path,
                language=whisper_lang,
                fp16=False
            )

            return {
                "text": result.get("text", "").strip(),
                "language": result.get("language", language or "unknown"),
                "segments": result.get("segments", [])
            }
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return {"text": "", "language": language or "unknown", "error": str(e)}
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def synthesize(self, text: str, language: str = "english") -> dict:
        """Convert text to speech, return base64 audio"""
        lang_code = LANGUAGE_CODES.get(language.lower(), "en")

        if GTTS_AVAILABLE:
            return self._gtts_synthesize(text, lang_code)

        return {"audio_base64": "", "format": "mp3", "error": "No TTS engine available. Install gtts."}

    def _gtts_synthesize(self, text: str, lang_code: str) -> dict:
        """Synthesize using gTTS"""
        try:
            tts = gTTS(text=text, lang=lang_code, slow=False)
            buf = io.BytesIO()
            tts.write_to_fp(buf)
            buf.seek(0)
            audio_b64 = base64.b64encode(buf.read()).decode("utf-8")
            return {"audio_base64": audio_b64, "format": "mp3", "language": lang_code}
        except Exception as e:
            logger.error(f"gTTS error: {e}")
            return {"audio_base64": "", "format": "mp3", "error": str(e)}


_speech_service = None


def get_speech_service() -> SpeechService:
    global _speech_service
    if _speech_service is None:
        _speech_service = SpeechService()
    return _speech_service
