/**
 * voice-handler.js
 * Handles microphone recording, STT, and TTS playback for Vani-Kanoon.
 */

const API_BASE = window.VANI_API_BASE || 'http://localhost:8000';

export class VoiceHandler {
  constructor() {
    this._mediaRecorder = null;
    this._audioChunks = [];
    this._isRecording = false;
    this._stream = null;
    this._legalHandler = null;

    // DOM refs – populated in init()
    this._micBtn = null;
    this._transcriptionBar = null;
    this._transcriptionText = null;
  }

  /** Bind to a LegalQueryHandler and wire up DOM events. */
  init(legalHandler) {
    this._legalHandler = legalHandler;
    this._micBtn = document.getElementById('micBtn');
    this._transcriptionBar = document.getElementById('transcriptionBar');
    this._transcriptionText = document.getElementById('transcriptionText');

    if (this._micBtn) {
      this._micBtn.addEventListener('mousedown', () => this.startRecording());
      this._micBtn.addEventListener('mouseup', () => this.stopRecordingAndProcess());
      this._micBtn.addEventListener('touchstart', (e) => { e.preventDefault(); this.startRecording(); });
      this._micBtn.addEventListener('touchend', (e) => { e.preventDefault(); this.stopRecordingAndProcess(); });
    }
  }

  // ---------------------------------------------------------------------------
  // Recording
  // ---------------------------------------------------------------------------

  async startRecording() {
    if (this._isRecording) return;
    try {
      this._stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this._audioChunks = [];

      // Prefer webm; fall back to browser default if not supported
      let mimeType = 'audio/webm';
      if (!MediaRecorder.isTypeSupported(mimeType)) {
        mimeType = MediaRecorder.isTypeSupported('audio/ogg') ? 'audio/ogg' : '';
      }
      const options = mimeType ? { mimeType } : {};
      this._mediaRecorder = new MediaRecorder(this._stream, options);

      this._mediaRecorder.addEventListener('dataavailable', (e) => {
        if (e.data.size > 0) this._audioChunks.push(e.data);
      });

      this._mediaRecorder.start(100);
      this._isRecording = true;
      this._setRecordingState(true);
      this.displayTranscription('🎙️ Recording… Release to send.');
    } catch (err) {
      console.error('Microphone access denied:', err);
      this.displayTranscription('❌ Microphone access denied. Please type your question.');
      setTimeout(() => this._hideTranscriptionBar(), 3000);
    }
  }

  async stopRecording() {
    if (!this._isRecording || !this._mediaRecorder) return null;
    return new Promise((resolve) => {
      this._mediaRecorder.addEventListener('stop', () => {
        const blob = new Blob(this._audioChunks, { type: 'audio/webm' });
        this._cleanupStream();
        resolve(blob);
      });
      this._mediaRecorder.stop();
      this._isRecording = false;
      this._setRecordingState(false);
    });
  }

  async stopRecordingAndProcess() {
    const blob = await this.stopRecording();
    if (blob && blob.size > 0) {
      this.displayTranscription('⏳ Processing speech…');
      await this.handleVoiceInput(blob);
    }
  }

  _cleanupStream() {
    if (this._stream) {
      this._stream.getTracks().forEach((t) => t.stop());
      this._stream = null;
    }
  }

  // ---------------------------------------------------------------------------
  // STT
  // ---------------------------------------------------------------------------

  async transcribeAudio(audioBlob) {
    try {
      const base64 = await this._blobToBase64(audioBlob);
      const language = this._legalHandler ? this._legalHandler.getSelectedLanguage() : 'English';

      const resp = await fetch(`${API_BASE}/speech/transcribe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ audio: base64, language }),
      });

      if (!resp.ok) throw new Error(`STT API error: ${resp.status}`);
      return await resp.json();
    } catch (err) {
      console.error('Transcription failed:', err);
      return { text: '', detected_language: 'English' };
    }
  }

  // ---------------------------------------------------------------------------
  // TTS playback
  // ---------------------------------------------------------------------------

  playAudio(base64Audio) {
    if (!base64Audio) return;
    try {
      const byteChars = atob(base64Audio);
      const byteNums = new Uint8Array(byteChars.length);
      for (let i = 0; i < byteChars.length; i++) byteNums[i] = byteChars.charCodeAt(i);
      const blob = new Blob([byteNums], { type: 'audio/mp3' });
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.play().catch((e) => console.warn('Audio playback error:', e));
      audio.addEventListener('ended', () => URL.revokeObjectURL(url));
    } catch (err) {
      console.error('Audio playback failed:', err);
    }
  }

  // ---------------------------------------------------------------------------
  // Complete voice flow
  // ---------------------------------------------------------------------------

  async handleVoiceInput(audioBlob) {
    if (!this._legalHandler) return;

    const result = await this.transcribeAudio(audioBlob);
    const text = result.text || '';
    const detectedLang = result.detected_language || 'English';

    if (text.trim()) {
      this.displayTranscription(`✅ "${text}"`);
      this._legalHandler.handleLanguageDetection(detectedLang, null);
      await this._legalHandler.submitQuery(text, audioBlob, detectedLang, null);
    } else {
      this.displayTranscription('❌ Could not understand speech. Please try again or type.');
    }
    setTimeout(() => this._hideTranscriptionBar(), 4000);
  }

  // ---------------------------------------------------------------------------
  // UI helpers
  // ---------------------------------------------------------------------------

  displayTranscription(text) {
    if (this._transcriptionBar) this._transcriptionBar.style.display = 'flex';
    if (this._transcriptionText) this._transcriptionText.textContent = text;
  }

  _hideTranscriptionBar() {
    if (this._transcriptionBar) this._transcriptionBar.style.display = 'none';
  }

  _setRecordingState(recording) {
    if (!this._micBtn) return;
    if (recording) {
      this._micBtn.classList.add('recording');
      this._micBtn.setAttribute('aria-pressed', 'true');
    } else {
      this._micBtn.classList.remove('recording');
      this._micBtn.setAttribute('aria-pressed', 'false');
    }
  }

  // ---------------------------------------------------------------------------
  // Utility
  // ---------------------------------------------------------------------------

  _blobToBase64(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const dataUrl = reader.result;
        // Strip the data:audio/xxx;base64, prefix
        const b64 = dataUrl.split(',')[1];
        resolve(b64);
      };
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }

  get isRecording() { return this._isRecording; }
}
