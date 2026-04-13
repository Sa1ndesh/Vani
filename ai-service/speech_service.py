"""
Speech Service for Vani-Kanoon
Handles Speech-to-Text (STT) and Text-to-Speech (TTS) for multilingual Indian languages.
Uses Whisper for STT (with fallback) and gTTS as primary TTS provider.
Coqui TTS is supported as an optional high-quality TTS backend.
"""

import io
import logging
import tempfile
import os
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependencies — graceful fallbacks
# ---------------------------------------------------------------------------
try:
    import whisper as _whisper  # openai-whisper
    _WHISPER_AVAILABLE = True
    logger.info("openai-whisper is available for STT.")
except ImportError:
    _WHISPER_AVAILABLE = False
    logger.warning("openai-whisper not installed — STT will use placeholder mode.")

try:
    from gtts import gTTS
    _GTTS_AVAILABLE = True
    logger.info("gTTS is available for TTS.")
except ImportError:
    _GTTS_AVAILABLE = False
    logger.warning("gTTS not installed — TTS will be disabled.")

try:
    from TTS.api import TTS as CoquiTTS  # coqui-tts
    _COQUI_AVAILABLE = True
    logger.info("Coqui TTS is available as an enhanced TTS backend.")
except ImportError:
    _COQUI_AVAILABLE = False
    logger.info("Coqui TTS not installed — using gTTS as sole TTS provider.")

try:
    from pydub import AudioSegment
    _PYDUB_AVAILABLE = True
    logger.info("pydub is available for audio preprocessing.")
except ImportError:
    _PYDUB_AVAILABLE = False
    logger.info("pydub not installed — audio preprocessing skipped.")

# ---------------------------------------------------------------------------
# Language configuration
# ---------------------------------------------------------------------------

SUPPORTED_LANGUAGES: Dict[str, Dict[str, str]] = {
    "hi": {
        "name": "Hindi",
        "native": "हिन्दी",
        "gtts_lang": "hi",
        "whisper_lang": "hi",
        "coqui_model": "tts_models/hi/cv/vits",
        "script": "Devanagari",
    },
    "kn": {
        "name": "Kannada",
        "native": "ಕನ್ನಡ",
        "gtts_lang": "kn",
        "whisper_lang": "kn",
        "coqui_model": "tts_models/kn/cv/vits",
        "script": "Kannada",
    },
    "mr": {
        "name": "Marathi",
        "native": "मराठी",
        "gtts_lang": "mr",
        "whisper_lang": "mr",
        "coqui_model": "tts_models/mr/cv/vits",
        "script": "Devanagari",
    },
    "ta": {
        "name": "Tamil",
        "native": "தமிழ்",
        "gtts_lang": "ta",
        "whisper_lang": "ta",
        "coqui_model": "tts_models/ta/cv/vits",
        "script": "Tamil",
    },
    "te": {
        "name": "Telugu",
        "native": "తెలుగు",
        "gtts_lang": "te",
        "whisper_lang": "te",
        "coqui_model": "tts_models/te/cv/vits",
        "script": "Telugu",
    },
    "en": {
        "name": "English",
        "native": "English",
        "gtts_lang": "en",
        "whisper_lang": "en",
        "coqui_model": "tts_models/en/ljspeech/tacotron2-DDC",
        "script": "Latin",
    },
    "bn": {
        "name": "Bengali",
        "native": "বাংলা",
        "gtts_lang": "bn",
        "whisper_lang": "bn",
        "coqui_model": None,
        "script": "Bengali",
    },
    "gu": {
        "name": "Gujarati",
        "native": "ગુજરાતી",
        "gtts_lang": "gu",
        "whisper_lang": "gu",
        "coqui_model": None,
        "script": "Gujarati",
    },
    "pa": {
        "name": "Punjabi",
        "native": "ਪੰਜਾਬੀ",
        "gtts_lang": "pa",
        "whisper_lang": "pa",
        "coqui_model": None,
        "script": "Gurmukhi",
    },
    "ml": {
        "name": "Malayalam",
        "native": "മലയാളം",
        "gtts_lang": "ml",
        "whisper_lang": "ml",
        "coqui_model": None,
        "script": "Malayalam",
    },
}

_WHISPER_MODEL_NAME = "base"  # tiny | base | small | medium | large


class SpeechService:
    """
    Multilingual Speech-to-Text and Text-to-Speech for Indian languages.

    STT backend priority: openai-whisper → placeholder (returns empty string)
    TTS backend priority: gTTS → Coqui TTS → silent bytes
    """

    def __init__(
        self,
        whisper_model: str = _WHISPER_MODEL_NAME,
        prefer_coqui: bool = False,
    ) -> None:
        """
        Initialise the speech service.

        Args:
            whisper_model: Whisper model size ("tiny", "base", "small", …).
            prefer_coqui:  If True and Coqui TTS is installed, use it for TTS
                           instead of gTTS (higher quality but larger footprint).
        """
        self._whisper_model_name = whisper_model
        self._whisper_model: Optional[Any] = None
        self._prefer_coqui = prefer_coqui and _COQUI_AVAILABLE
        self._coqui_models: Dict[str, Any] = {}  # language → loaded model

        logger.info(
            "SpeechService init — STT=%s, TTS=%s",
            "whisper" if _WHISPER_AVAILABLE else "placeholder",
            "coqui" if self._prefer_coqui else ("gTTS" if _GTTS_AVAILABLE else "disabled"),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_whisper(self) -> Optional[Any]:
        """Lazily load the Whisper model."""
        if self._whisper_model is not None:
            return self._whisper_model
        if not _WHISPER_AVAILABLE:
            return None
        try:
            self._whisper_model = _whisper.load_model(self._whisper_model_name)
            logger.info("Loaded Whisper model: %s", self._whisper_model_name)
            return self._whisper_model
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load Whisper model: %s", exc)
            return None

    def _preprocess_audio(self, audio_bytes: bytes) -> bytes:
        """
        Optionally convert / normalise audio using pydub.
        Converts to 16 kHz mono WAV (Whisper-friendly format).
        Returns original bytes if pydub is not available.
        """
        if not _PYDUB_AVAILABLE:
            return audio_bytes
        try:
            audio = AudioSegment.from_file(io.BytesIO(audio_bytes))
            audio = audio.set_channels(1).set_frame_rate(16_000).set_sample_width(2)
            buf = io.BytesIO()
            audio.export(buf, format="wav")
            return buf.getvalue()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Audio preprocessing failed: %s — using raw audio.", exc)
            return audio_bytes

    def _write_temp_audio(self, audio_bytes: bytes, suffix: str = ".wav") -> str:
        """Write audio bytes to a temp file in the current working directory and return its path."""
        # Use the cache directory (relative to this service) instead of /tmp
        cache_dir = os.path.join(os.path.dirname(__file__), "cache")
        os.makedirs(cache_dir, exist_ok=True)
        import uuid
        tmp_path = os.path.join(cache_dir, f"audio_{uuid.uuid4().hex}{suffix}")
        with open(tmp_path, "wb") as fh:
            fh.write(audio_bytes)
        return tmp_path

    def _cleanup_temp(self, path: str) -> None:
        """Remove a temporary file silently."""
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Speech-to-Text
    # ------------------------------------------------------------------

    def transcribe(
        self,
        audio_data: bytes,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Transcribe audio bytes to text.

        Args:
            audio_data: Raw audio bytes (WAV, MP3, OGG, …).
            language:   BCP-47 language code hint, e.g. "hi", "kn".
                        If None, Whisper auto-detects.

        Returns:
            {
                "text": str,
                "language": str,       # detected or provided language code
                "confidence": float,   # 0–1 estimate (1.0 when forced)
                "backend": str,        # "whisper" | "placeholder"
            }
        """
        if not audio_data:
            return {"text": "", "language": language or "unknown", "confidence": 0.0, "backend": "none"}

        model = self._ensure_whisper()
        if model is None:
            logger.warning("Whisper unavailable — returning empty transcription placeholder.")
            return {
                "text": "",
                "language": language or "unknown",
                "confidence": 0.0,
                "backend": "placeholder",
                "message": "STT backend not available. Please enable Web Speech API on the client side.",
            }

        audio_bytes = self._preprocess_audio(audio_data)
        tmp_path = self._write_temp_audio(audio_bytes, ".wav")
        try:
            whisper_lang = None
            if language and language in SUPPORTED_LANGUAGES:
                whisper_lang = SUPPORTED_LANGUAGES[language]["whisper_lang"]
            elif language:
                whisper_lang = language

            result = model.transcribe(tmp_path, language=whisper_lang, fp16=False)
            detected_lang = result.get("language", language or "unknown")
            # Whisper returns segment-level log-probs; average as a rough confidence
            segments = result.get("segments", [])
            if segments:
                avg_logprob = sum(s.get("avg_logprob", -1.0) for s in segments) / len(segments)
                # Map log-prob (typically -0.2 to -1.5) to 0–1
                confidence = max(0.0, min(1.0, 1.0 + avg_logprob / 2.0))
            else:
                confidence = 0.5

            return {
                "text": result.get("text", "").strip(),
                "language": detected_lang,
                "confidence": round(confidence, 3),
                "backend": "whisper",
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Whisper transcription failed: %s", exc)
            return {
                "text": "",
                "language": language or "unknown",
                "confidence": 0.0,
                "backend": "whisper",
                "error": str(exc),
            }
        finally:
            self._cleanup_temp(tmp_path)

    # ------------------------------------------------------------------
    # Text-to-Speech
    # ------------------------------------------------------------------

    def synthesize(
        self,
        text: str,
        language: str = "hi",
        slow: bool = False,
    ) -> Dict[str, Any]:
        """
        Convert text to speech audio.

        Args:
            text:     Text to synthesise.
            language: BCP-47 language code, e.g. "hi", "kn", "en".
            slow:     If True, speak more slowly (gTTS option).

        Returns:
            {
                "audio_bytes": bytes,  # MP3 audio data (empty if unavailable)
                "format": str,         # "mp3" | "wav" | "none"
                "language": str,
                "backend": str,        # "gtts" | "coqui" | "none"
            }
        """
        if not text or not text.strip():
            return {"audio_bytes": b"", "format": "none", "language": language, "backend": "none"}

        if self._prefer_coqui:
            result = self._synthesize_coqui(text, language)
            if result["audio_bytes"]:
                return result

        return self._synthesize_gtts(text, language, slow)

    def _synthesize_gtts(
        self, text: str, language: str, slow: bool
    ) -> Dict[str, Any]:
        """Synthesise using gTTS (Google Text-to-Speech)."""
        if not _GTTS_AVAILABLE:
            logger.error("gTTS is not installed — cannot synthesise speech.")
            return {"audio_bytes": b"", "format": "none", "language": language, "backend": "none"}

        lang_config = SUPPORTED_LANGUAGES.get(language, SUPPORTED_LANGUAGES["en"])
        gtts_lang = lang_config["gtts_lang"]

        try:
            tts = gTTS(text=text, lang=gtts_lang, slow=slow)
            buf = io.BytesIO()
            tts.write_to_fp(buf)
            buf.seek(0)
            return {
                "audio_bytes": buf.read(),
                "format": "mp3",
                "language": language,
                "backend": "gtts",
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("gTTS synthesis failed (lang=%s): %s", language, exc)
            # Retry with English as fallback
            if language != "en":
                logger.info("Retrying gTTS synthesis in English.")
                return self._synthesize_gtts(text, "en", slow)
            return {"audio_bytes": b"", "format": "none", "language": language, "backend": "gtts", "error": str(exc)}

    def _synthesize_coqui(
        self, text: str, language: str
    ) -> Dict[str, Any]:
        """Synthesise using Coqui TTS (high-quality, offline)."""
        if not _COQUI_AVAILABLE:
            return {"audio_bytes": b"", "format": "none", "language": language, "backend": "coqui"}

        lang_config = SUPPORTED_LANGUAGES.get(language, {})
        model_name = lang_config.get("coqui_model")
        if not model_name:
            logger.warning("No Coqui model for language '%s' — falling back to gTTS.", language)
            return {"audio_bytes": b"", "format": "none", "language": language, "backend": "coqui"}

        if model_name not in self._coqui_models:
            try:
                self._coqui_models[model_name] = CoquiTTS(model_name=model_name, progress_bar=False)
                logger.info("Loaded Coqui model: %s", model_name)
            except Exception as exc:  # noqa: BLE001
                logger.error("Coqui model load failed (%s): %s", model_name, exc)
                return {"audio_bytes": b"", "format": "none", "language": language, "backend": "coqui"}

        tts_model = self._coqui_models[model_name]
        tmp_path = self._write_temp_audio(b"", ".wav")
        try:
            tts_model.tts_to_file(text=text, file_path=tmp_path)
            with open(tmp_path, "rb") as fh:
                wav_bytes = fh.read()
            return {
                "audio_bytes": wav_bytes,
                "format": "wav",
                "language": language,
                "backend": "coqui",
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Coqui synthesis failed: %s", exc)
            return {"audio_bytes": b"", "format": "none", "language": language, "backend": "coqui"}
        finally:
            self._cleanup_temp(tmp_path)

    # ------------------------------------------------------------------
    # Language detection from audio
    # ------------------------------------------------------------------

    def detect_language_from_audio(
        self,
        audio_data: bytes,
    ) -> Dict[str, Any]:
        """
        Detect the spoken language from audio bytes.

        Uses Whisper's built-in language detection when available.
        Returns the most likely language code and probability.

        Returns:
            {
                "language": str,      # BCP-47 code, e.g. "hi"
                "probability": float, # 0–1
                "all_probs": dict,    # language → probability (top candidates)
                "backend": str,
            }
        """
        model = self._ensure_whisper()
        if model is None:
            return {
                "language": "hi",
                "probability": 0.0,
                "all_probs": {},
                "backend": "placeholder",
                "message": "Language detection requires openai-whisper.",
            }

        audio_bytes = self._preprocess_audio(audio_data)
        tmp_path = self._write_temp_audio(audio_bytes, ".wav")
        try:
            audio = _whisper.load_audio(tmp_path)
            audio = _whisper.pad_or_trim(audio)
            mel = _whisper.log_mel_spectrogram(audio).to(model.device)
            _, probs = model.detect_language(mel)
            top_lang = max(probs, key=probs.get)
            top_5 = dict(sorted(probs.items(), key=lambda x: x[1], reverse=True)[:5])
            return {
                "language": top_lang,
                "probability": round(float(probs[top_lang]), 3),
                "all_probs": {k: round(float(v), 3) for k, v in top_5.items()},
                "backend": "whisper",
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Language detection failed: %s", exc)
            return {
                "language": "unknown",
                "probability": 0.0,
                "all_probs": {},
                "backend": "whisper",
                "error": str(exc),
            }
        finally:
            self._cleanup_temp(tmp_path)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_supported_languages(self) -> List[Dict[str, str]]:
        """Return a list of supported languages with metadata."""
        return [
            {
                "code": code,
                "name": cfg["name"],
                "native": cfg["native"],
                "script": cfg["script"],
                "stt_supported": _WHISPER_AVAILABLE,
                "tts_supported": _GTTS_AVAILABLE or _COQUI_AVAILABLE,
            }
            for code, cfg in SUPPORTED_LANGUAGES.items()
        ]

    def is_language_supported(self, language_code: str) -> bool:
        """Return True if the language code is in the supported list."""
        return language_code in SUPPORTED_LANGUAGES

    def get_tts_backends(self) -> Dict[str, bool]:
        """Return availability status of each TTS backend."""
        return {"gtts": _GTTS_AVAILABLE, "coqui": _COQUI_AVAILABLE}

    def get_stt_backends(self) -> Dict[str, bool]:
        """Return availability status of each STT backend."""
        return {"whisper": _WHISPER_AVAILABLE}
