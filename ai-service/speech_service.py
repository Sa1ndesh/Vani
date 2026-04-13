"""
Speech processing service for Vani-Kanoon.
Handles STT (Whisper), TTS (Google Cloud TTS / gTTS fallback), and audio preprocessing.
"""
import base64
import io
import logging
import os
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

# --- Optional dependency guards ---
try:
    import whisper as openai_whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    logger.warning("openai-whisper not available; STT will return placeholder.")

try:
    from pydub import AudioSegment
    from pydub.silence import detect_nonsilent
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    logger.warning("pydub not available; audio preprocessing skipped.")

try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False
    logger.warning("gTTS not available; TTS will return empty bytes.")

try:
    from google.cloud import texttospeech
    GOOGLE_TTS_AVAILABLE = True
except ImportError:
    GOOGLE_TTS_AVAILABLE = False

# Language code → gTTS language tag
LANGUAGE_CODES = {
    "hi": "hi",
    "kn": "kn",
    "mr": "mr",
    "ta": "ta",
    "te": "te",
    "en": "en",
    "Hindi": "hi",
    "Kannada": "kn",
    "Marathi": "mr",
    "Tamil": "ta",
    "Telugu": "te",
    "English": "en",
}

# Google Cloud TTS voice configs per language
GOOGLE_TTS_VOICES = {
    "hi": {"language_code": "hi-IN", "name": "hi-IN-Standard-A", "ssml_gender": "FEMALE"},
    "kn": {"language_code": "kn-IN", "name": "kn-IN-Standard-A", "ssml_gender": "FEMALE"},
    "mr": {"language_code": "mr-IN", "name": "mr-IN-Standard-A", "ssml_gender": "FEMALE"},
    "ta": {"language_code": "ta-IN", "name": "ta-IN-Standard-A", "ssml_gender": "FEMALE"},
    "te": {"language_code": "te-IN", "name": "te-IN-Standard-A", "ssml_gender": "FEMALE"},
    "en": {"language_code": "en-IN", "name": "en-IN-Standard-A", "ssml_gender": "FEMALE"},
}


class SpeechService:
    def __init__(self):
        self._whisper_model = None
        self._google_tts_client = None
        self._init_services()

    def _init_services(self) -> None:
        if WHISPER_AVAILABLE:
            try:
                # Use 'base' for a good speed/accuracy balance
                self._whisper_model = openai_whisper.load_model("base")
                logger.info("Whisper 'base' model loaded.")
            except Exception as e:
                logger.error("Whisper load failed: %s", e)

        if GOOGLE_TTS_AVAILABLE and os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            try:
                self._google_tts_client = texttospeech.TextToSpeechClient()
                logger.info("Google Cloud TTS client initialized.")
            except Exception as e:
                logger.warning("Google Cloud TTS init failed: %s", e)

    # ------------------------------------------------------------------
    # STT
    # ------------------------------------------------------------------

    def transcribe_audio(
        self, audio_data: bytes, language: Optional[str] = None
    ) -> dict:
        """
        Transcribe audio bytes (or base64-encoded bytes) to text.
        Returns {"text": ..., "detected_language": ..., "confidence": ...}
        """
        # Accept base64 input
        if isinstance(audio_data, str):
            try:
                audio_data = base64.b64decode(audio_data)
            except Exception:
                pass

        if not WHISPER_AVAILABLE or self._whisper_model is None:
            return {
                "text": "",
                "detected_language": language or "en",
                "confidence": 0.0,
            }

        try:
            preprocessed = self._preprocess_audio(audio_data)
            audio_file = io.BytesIO(preprocessed)

            # Whisper requires a file path or numpy array; use a temp file
            suffix = ".wav"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(preprocessed)
                tmp_path = tmp.name

            try:
                options = {}
                if language and language in LANGUAGE_CODES:
                    options["language"] = LANGUAGE_CODES[language]
                result = self._whisper_model.transcribe(tmp_path, **options)
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

            detected_lang = result.get("language", language or "en")
            # Map whisper lang code to friendly name
            lang_map = {v: k for k, v in LANGUAGE_CODES.items() if len(k) == 2}
            detected_friendly = lang_map.get(detected_lang, detected_lang)

            return {
                "text": result.get("text", "").strip(),
                "detected_language": detected_friendly,
                "confidence": 0.9,
            }
        except Exception as e:
            logger.error("Transcription failed: %s", e)
            return {
                "text": "",
                "detected_language": language or "en",
                "confidence": 0.0,
            }

    # ------------------------------------------------------------------
    # TTS
    # ------------------------------------------------------------------

    def synthesize_speech(
        self, text: str, language: str, dialect: Optional[str] = None
    ) -> bytes:
        """
        Synthesize *text* in *language*. Returns MP3 bytes.
        Tries Google Cloud TTS first, falls back to gTTS.
        """
        lang_code = LANGUAGE_CODES.get(language, "en")

        if self._google_tts_client is not None:
            result = self._google_cloud_tts(text, lang_code)
            if result:
                return result

        if GTTS_AVAILABLE:
            return self._gtts_synthesize(text, lang_code)

        logger.warning("No TTS backend available.")
        return b""

    def _google_cloud_tts(self, text: str, lang_code: str) -> Optional[bytes]:
        try:
            voice_cfg = GOOGLE_TTS_VOICES.get(lang_code, GOOGLE_TTS_VOICES["en"])
            synthesis_input = texttospeech.SynthesisInput(text=text)
            voice = texttospeech.VoiceSelectionParams(
                language_code=voice_cfg["language_code"],
                name=voice_cfg["name"],
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3
            )
            response = self._google_tts_client.synthesize_speech(
                input=synthesis_input, voice=voice, audio_config=audio_config
            )
            return response.audio_content
        except Exception as e:
            logger.error("Google Cloud TTS failed: %s", e)
            return None

    def _gtts_synthesize(self, text: str, lang_code: str) -> bytes:
        try:
            tts = gTTS(text=text, lang=lang_code, slow=False)
            buf = io.BytesIO()
            tts.write_to_fp(buf)
            buf.seek(0)
            return buf.read()
        except Exception as e:
            logger.error("gTTS failed: %s", e)
            return b""

    # ------------------------------------------------------------------
    # Language detection from audio
    # ------------------------------------------------------------------

    def detect_language_from_audio(self, audio_data: bytes) -> str:
        """
        Detect the spoken language in *audio_data*.
        Uses Whisper's language detection pass.
        """
        if isinstance(audio_data, str):
            try:
                audio_data = base64.b64decode(audio_data)
            except Exception:
                pass

        if not WHISPER_AVAILABLE or self._whisper_model is None:
            return "en"

        try:
            preprocessed = self._preprocess_audio(audio_data)
            suffix = ".wav"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(preprocessed)
                tmp_path = tmp.name
            try:
                audio = openai_whisper.load_audio(tmp_path)
                audio = openai_whisper.pad_or_trim(audio)
                mel = openai_whisper.log_mel_spectrogram(audio).to(
                    self._whisper_model.device
                )
                _, probs = self._whisper_model.detect_language(mel)
                detected = max(probs, key=probs.get)
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

            lang_map = {v: k for k, v in LANGUAGE_CODES.items() if len(k) == 2}
            return lang_map.get(detected, detected)
        except Exception as e:
            logger.error("Language detection from audio failed: %s", e)
            return "en"

    # ------------------------------------------------------------------
    # Audio preprocessing
    # ------------------------------------------------------------------

    def _preprocess_audio(self, audio_data: bytes) -> bytes:
        """
        Normalize volume and strip leading/trailing silence.
        Returns WAV bytes. Falls back to original bytes if pydub unavailable.
        """
        if not PYDUB_AVAILABLE:
            return audio_data
        try:
            audio = AudioSegment.from_file(io.BytesIO(audio_data))
            # Normalize to -20 dBFS
            change_dBFS = -20.0 - audio.dBFS
            audio = audio.apply_gain(change_dBFS)

            # Strip silence from edges
            nonsilent = detect_nonsilent(audio, min_silence_len=300, silence_thresh=-40)
            if nonsilent:
                start_ms, end_ms = nonsilent[0][0], nonsilent[-1][1]
                audio = audio[max(0, start_ms - 100): end_ms + 100]

            buf = io.BytesIO()
            audio.export(buf, format="wav")
            buf.seek(0)
            return buf.read()
        except Exception as e:
            logger.warning("Audio preprocessing failed: %s", e)
            return audio_data
