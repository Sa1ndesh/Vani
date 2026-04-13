/**
 * voice-handler.js – WebRTC audio recording and voice handling
 * for Vani-Kanoon Legal Assistant.
 *
 * Handles:
 *  • Microphone permission
 *  • MediaRecorder-based audio capture
 *  • STT via backend  (/speech/transcribe)
 *  • TTS via backend  (/speech/synthesize)
 *  • Browser Web Speech API fallback (when backend is unavailable)
 *  • Real-time audio-level callbacks
 *  • Integration with AudioVisualizer
 */

'use strict';

class VoiceHandler {
  /**
   * @param {AudioVisualizer|null} [visualizer=null]
   *   An AudioVisualizer instance to drive with the live mic stream.
   */
  constructor(visualizer = null) {
    // MediaRecorder state
    this._mediaRecorder = null;
    this._audioChunks   = [];
    this._stream        = null;

    // Public flags
    this.isRecording    = false;
    this.isPlaying      = false;

    // References
    this.visualizer     = visualizer;

    // Settings
    this.selectedLanguage = 'hi';
    this.selectedMimeType = this._pickMimeType();

    // Audio-level monitoring
    this._levelContext   = null;
    this._levelAnalyser  = null;
    this._levelSource    = null;
    this._levelTimerId   = null;
    this._levelCallbacks = [];

    // TTS audio element (re-used)
    this._audioEl = new Audio();
    this._audioEl.preload = 'auto';

    // Browser STT (Web Speech API)
    this._speechRecognition = null;

    // Event callbacks map
    this._eventListeners = {
      start:        [],
      stop:         [],
      result:       [],
      error:        [],
      audiolevel:   [],
      playstart:    [],
      playend:      [],
    };

    // Bind
    this._handleDataAvailable = this._handleDataAvailable.bind(this);
    this._handleRecordStop    = this._handleRecordStop.bind(this);
  }

  /* ── Permission ─────────────────────────────────────────────── */

  /**
   * Request microphone access from the browser.
   * Returns the MediaStream on success, throws on denial/error.
   * @returns {Promise<MediaStream>}
   */
  async requestMicrophonePermission() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error('Microphone access is not supported in this browser.');
    }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    return stream;
  }

  /* ── Recording ──────────────────────────────────────────────── */

  /**
   * Start recording audio from the microphone.
   * Resolves immediately once recording begins.
   * @returns {Promise<void>}
   */
  async startRecording() {
    if (this.isRecording) {
      console.warn('[VoiceHandler] Already recording.');
      return;
    }

    try {
      this._stream = await this.requestMicrophonePermission();
    } catch (err) {
      this._emit('error', { message: err.message, type: 'permission' });
      throw err;
    }

    this._audioChunks = [];

    // Connect visualizer
    if (this.visualizer) {
      this.visualizer.connect(this._stream);
      this.visualizer.setMode('bars');
      this.visualizer.start();
    }

    // Start audio-level monitoring
    this._startLevelMonitor(this._stream);

    // Create MediaRecorder
    const opts = this.selectedMimeType ? { mimeType: this.selectedMimeType } : {};
    this._mediaRecorder = new MediaRecorder(this._stream, opts);
    this._mediaRecorder.addEventListener('dataavailable', this._handleDataAvailable);
    this._mediaRecorder.addEventListener('stop', this._handleRecordStop);
    this._mediaRecorder.start(250); // collect chunks every 250 ms

    this.isRecording = true;
    this._emit('start', {});
  }

  /**
   * Stop recording and return the captured audio as a Blob.
   * @returns {Promise<Blob>}
   */
  stopRecording() {
    return new Promise((resolve, reject) => {
      if (!this._mediaRecorder || !this.isRecording) {
        return reject(new Error('Not currently recording.'));
      }

      // Listen for the stop event (fired after MediaRecorder.stop())
      this._pendingStopResolve = resolve;
      this._pendingStopReject  = reject;

      this._mediaRecorder.stop();
      this.isRecording = false;

      // Stop all mic tracks
      if (this._stream) {
        this._stream.getTracks().forEach(t => t.stop());
        this._stream = null;
      }

      this._stopLevelMonitor();

      if (this.visualizer) {
        this.visualizer.setIdle();
      }

      this._emit('stop', {});
    });
  }

  /* ── STT – send audio to backend ───────────────────────────── */

  /**
   * Send an audio Blob to the backend Speech-to-Text endpoint.
   * @param {Blob}   audioBlob   The recorded audio.
   * @param {string} [language]  Override language code (defaults to this.selectedLanguage).
   * @returns {Promise<{transcript: string, confidence: number}>}
   */
  async transcribeAudio(audioBlob, language) {
    const lang = language || this.selectedLanguage;
    const bcp47 = typeof getBCP47 === 'function' ? getBCP47(lang) : `${lang}-IN`;

    const formData = new FormData();
    formData.append('audio', audioBlob, `recording.${this._mimeToExt()}`);
    formData.append('language', lang);
    formData.append('language_bcp47', bcp47);

    const apiHelper = typeof API !== 'undefined' ? API : null;
    if (apiHelper) {
      return await apiHelper.postForm('/speech/transcribe', formData);
    }

    // Fallback: raw fetch
    const res = await fetch('http://localhost:8000/speech/transcribe', {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.text();
      throw new Error(`STT failed (${res.status}): ${err}`);
    }
    return res.json();
  }

  /* ── TTS – request synthesis from backend ───────────────────── */

  /**
   * Request TTS synthesis from the backend.
   * Returns an object with an audio_base64 or audio_url field.
   * @param {string} text
   * @param {string} [language]
   * @returns {Promise<{audio_base64?: string, audio_url?: string, duration?: number}>}
   */
  async synthesizeSpeech(text, language) {
    const lang  = language || this.selectedLanguage;
    const bcp47 = typeof getBCP47 === 'function' ? getBCP47(lang) : `${lang}-IN`;

    const apiHelper = typeof API !== 'undefined' ? API : null;
    const payload = { text, language: lang, language_bcp47: bcp47 };

    if (apiHelper) {
      return await apiHelper.post('/speech/synthesize', payload);
    }

    const res = await fetch('http://localhost:8000/speech/synthesize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.text();
      throw new Error(`TTS failed (${res.status}): ${err}`);
    }
    return res.json();
  }

  /**
   * Play back TTS audio returned by synthesizeSpeech().
   * Accepts either a base64 string or a URL.
   * @param {{audio_base64?: string, audio_url?: string}|string} audioData
   * @returns {Promise<void>}  Resolves when playback finishes.
   */
  playAudio(audioData) {
    return new Promise((resolve, reject) => {
      let src;

      if (typeof audioData === 'string') {
        src = audioData;
      } else if (audioData.audio_url) {
        src = audioData.audio_url;
      } else if (audioData.audio_base64) {
        src = `data:audio/mpeg;base64,${audioData.audio_base64}`;
      } else {
        return reject(new Error('No playable audio data provided.'));
      }

      this._audioEl.pause();
      this._audioEl.currentTime = 0;
      this._audioEl.src = src;

      this._audioEl.onended = () => {
        this.isPlaying = false;
        this._emit('playend', {});
        resolve();
      };
      this._audioEl.onerror = (e) => {
        this.isPlaying = false;
        reject(new Error(`Audio playback error: ${e.message || 'unknown'}`));
      };

      this.isPlaying = true;
      this._emit('playstart', {});
      this._audioEl.play().catch(reject);
    });
  }

  /** Stop any in-progress TTS playback. */
  stopPlayback() {
    this._audioEl.pause();
    this._audioEl.currentTime = 0;
    this.isPlaying = false;
  }

  /* ── Language ───────────────────────────────────────────────── */

  /**
   * @param {string} langCode  One of: hi, kn, mr, ta, te, en
   */
  setLanguage(langCode) {
    this.selectedLanguage = langCode;
  }

  /* ── Audio level callbacks ──────────────────────────────────── */

  /**
   * Register a callback that receives a normalised audio level (0–1)
   * while recording is active. Useful for custom level meters.
   * @param {function(number): void} callback
   */
  onAudioLevel(callback) {
    if (typeof callback === 'function') {
      this._levelCallbacks.push(callback);
    }
  }

  /* ── Browser Web Speech API (fallback) ──────────────────────── */

  /**
   * Start browser-native STT using Web Speech API.
   * @param {string}   language   BCP-47 tag, e.g. 'hi-IN'
   * @param {function({transcript: string, isFinal: boolean}): void} onResult
   * @param {function(Error): void} onError
   */
  startBrowserSTT(language, onResult, onError) {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      onError(new Error('Web Speech API not supported in this browser.'));
      return;
    }

    this.stopBrowserSTT();

    const recognition = new SpeechRecognition();
    recognition.lang              = language || getBCP47(this.selectedLanguage);
    recognition.interimResults    = true;
    recognition.continuous        = false;
    recognition.maxAlternatives   = 1;

    recognition.onresult = (event) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        onResult({
          transcript: result[0].transcript,
          confidence: result[0].confidence,
          isFinal:    result.isFinal,
        });
      }
    };

    recognition.onerror = (event) => {
      const messages = {
        'no-speech':          'No speech was detected. Please try again.',
        'audio-capture':      'Microphone is unavailable.',
        'not-allowed':        'Microphone permission denied.',
        'network':            'Network error during speech recognition.',
        'aborted':            'Speech recognition was stopped.',
        'language-not-supported': `Language "${language}" is not supported by the browser.`,
      };
      onError(new Error(messages[event.error] || `Speech error: ${event.error}`));
    };

    recognition.onend = () => {
      this._speechRecognition = null;
    };

    this._speechRecognition = recognition;
    recognition.start();
  }

  /** Stop browser STT if currently active. */
  stopBrowserSTT() {
    if (this._speechRecognition) {
      try { this._speechRecognition.stop(); } catch { /* ignore */ }
      this._speechRecognition = null;
    }
  }

  /* ── Event emitter ──────────────────────────────────────────── */

  /**
   * Register an event listener.
   * @param {'start'|'stop'|'result'|'error'|'audiolevel'|'playstart'|'playend'} event
   * @param {Function} handler
   */
  on(event, handler) {
    if (this._eventListeners[event]) {
      this._eventListeners[event].push(handler);
    }
    return this;
  }

  /** Remove an event listener. */
  off(event, handler) {
    if (this._eventListeners[event]) {
      this._eventListeners[event] = this._eventListeners[event].filter(h => h !== handler);
    }
    return this;
  }

  /* ── Cleanup ────────────────────────────────────────────────── */

  /** Release all resources. */
  destroy() {
    if (this.isRecording) {
      try { this._mediaRecorder.stop(); } catch { /* ignore */ }
    }
    if (this._stream) {
      this._stream.getTracks().forEach(t => t.stop());
    }
    this._stopLevelMonitor();
    this.stopBrowserSTT();
    this.stopPlayback();
  }

  /* ── Private helpers ────────────────────────────────────────── */

  _handleDataAvailable(event) {
    if (event.data && event.data.size > 0) {
      this._audioChunks.push(event.data);
    }
  }

  _handleRecordStop() {
    const mimeType = this.selectedMimeType || 'audio/webm';
    const blob = new Blob(this._audioChunks, { type: mimeType });
    this._audioChunks = [];

    if (this._pendingStopResolve) {
      this._pendingStopResolve(blob);
      this._pendingStopResolve = null;
      this._pendingStopReject  = null;
    }

    this._emit('result', { blob });
  }

  _startLevelMonitor(stream) {
    try {
      this._levelContext  = new (window.AudioContext || window.webkitAudioContext)();
      this._levelAnalyser = this._levelContext.createAnalyser();
      this._levelAnalyser.fftSize = 256;
      this._levelSource  = this._levelContext.createMediaStreamSource(stream);
      this._levelSource.connect(this._levelAnalyser);

      const data = new Uint8Array(this._levelAnalyser.frequencyBinCount);

      const tick = () => {
        if (!this._levelAnalyser) return;
        this._levelTimerId = requestAnimationFrame(tick);
        this._levelAnalyser.getByteFrequencyData(data);
        // RMS of frequency data as a proxy for loudness
        const sum = data.reduce((acc, v) => acc + v * v, 0);
        const rms = Math.sqrt(sum / data.length) / 255;
        this._levelCallbacks.forEach(cb => cb(rms));
        this._emit('audiolevel', { level: rms });
      };
      tick();
    } catch (err) {
      console.warn('[VoiceHandler] Level monitor unavailable:', err.message);
    }
  }

  _stopLevelMonitor() {
    if (this._levelTimerId) {
      cancelAnimationFrame(this._levelTimerId);
      this._levelTimerId = null;
    }
    if (this._levelSource)  { try { this._levelSource.disconnect();  } catch { /* ignore */ } this._levelSource  = null; }
    if (this._levelContext) { try { this._levelContext.close();       } catch { /* ignore */ } this._levelContext = null; }
    this._levelAnalyser = null;
  }

  _emit(event, data) {
    (this._eventListeners[event] || []).forEach(h => {
      try { h(data); } catch (err) { console.error(`[VoiceHandler] Handler error for "${event}":`, err); }
    });
  }

  /** Return a supported MediaRecorder MIME type, or empty string for default. */
  _pickMimeType() {
    const candidates = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
      'audio/mp4',
    ];
    if (typeof MediaRecorder === 'undefined' || !MediaRecorder.isTypeSupported) return '';
    return candidates.find(t => MediaRecorder.isTypeSupported(t)) || '';
  }

  /** Map MIME type to file extension for uploads. */
  _mimeToExt() {
    const mime = this.selectedMimeType;
    if (!mime) return 'webm';
    if (mime.includes('ogg')) return 'ogg';
    if (mime.includes('mp4')) return 'mp4';
    return 'webm';
  }
}

/* ── Expose globally ─────────────────────────────────────────── */
if (typeof window !== 'undefined') {
  window.VoiceHandler = VoiceHandler;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = VoiceHandler;
}
