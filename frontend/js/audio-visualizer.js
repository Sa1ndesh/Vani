/**
 * audio-visualizer.js – Real-time canvas-based audio visualisation
 * for Vani-Kanoon Legal Assistant.
 *
 * Supports two modes:
 *   • "bars"     – frequency-domain bar chart (default while recording)
 *   • "waveform" – time-domain waveform
 *   • "idle"     – gentle animated idle pulse when no audio is active
 */

'use strict';

class AudioVisualizer {
  /**
   * @param {string} canvasId  ID of the <canvas> element to draw on
   * @param {object} [options]
   * @param {string}  [options.mode='bars']          Initial render mode
   * @param {string}  [options.barColor='#4f46e5']   Primary bar / wave colour
   * @param {string}  [options.barColorAlt='#06b6d4'] Secondary / gradient colour
   * @param {string}  [options.backgroundColor='transparent']
   * @param {number}  [options.barCount=64]          Number of FFT bars
   * @param {number}  [options.barGap=2]             Pixel gap between bars
   * @param {number}  [options.minBarHeight=3]       Minimum bar height in px
   * @param {boolean} [options.mirror=true]          Mirror bars from centre
   * @param {number}  [options.smoothing=0.8]        AnalyserNode smoothing
   */
  constructor(canvasId, options = {}) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) {
      console.warn(`[AudioVisualizer] Canvas element with id "${canvasId}" not found.`);
      this.canvas = document.createElement('canvas');
    }

    this.ctx = this.canvas.getContext('2d');

    this.options = Object.assign({
      mode:            'idle',
      barColor:        '#4f46e5',
      barColorAlt:     '#06b6d4',
      backgroundColor: 'transparent',
      barCount:        64,
      barGap:          2,
      minBarHeight:    3,
      mirror:          true,
      smoothing:       0.8,
    }, options);

    // Web Audio nodes
    this._audioContext = null;
    this._analyser     = null;
    this._source       = null;
    this._dataArray    = null;

    // Animation state
    this._animationId  = null;
    this._isRunning    = false;

    // Idle animation state
    this._idlePhase    = 0;
    this._idleTime     = 0;

    // Current mode ('bars' | 'waveform' | 'idle')
    this._mode         = this.options.mode;

    // Bind handlers
    this._onResize = this._onResize.bind(this);

    // Observe size changes
    if (typeof ResizeObserver !== 'undefined') {
      this._resizeObserver = new ResizeObserver(this._onResize);
      this._resizeObserver.observe(this.canvas.parentElement || this.canvas);
    } else {
      window.addEventListener('resize', this._onResize);
    }

    this.resize();
  }

  /* ── Public API ─────────────────────────────────────────────── */

  /**
   * Connect this visualiser to a live MediaStream (e.g. from getUserMedia).
   * Creates an AudioContext → source node → AnalyserNode pipeline.
   * @param {MediaStream} audioStream
   */
  connect(audioStream) {
    this._teardownAudio();

    try {
      this._audioContext = new (window.AudioContext || window.webkitAudioContext)();
      this._analyser = this._audioContext.createAnalyser();
      this._analyser.fftSize = this.options.barCount * 4;
      this._analyser.smoothingTimeConstant = this.options.smoothing;

      this._source = this._audioContext.createMediaStreamSource(audioStream);
      this._source.connect(this._analyser);

      const bufferLen = this._analyser.frequencyBinCount;
      this._dataArray = new Uint8Array(bufferLen);

      this._mode = this.options.mode === 'idle' ? 'bars' : this.options.mode;
    } catch (err) {
      console.error('[AudioVisualizer] Could not connect audio stream:', err);
    }
  }

  /**
   * Connect directly to an AnalyserNode (e.g. from a more complex audio graph).
   * @param {AnalyserNode} analyserNode
   */
  connectAnalyser(analyserNode) {
    this._analyser = analyserNode;
    this._analyser.fftSize = this.options.barCount * 4;
    this._analyser.smoothingTimeConstant = this.options.smoothing;

    const bufferLen = this._analyser.frequencyBinCount;
    this._dataArray = new Uint8Array(bufferLen);
    this._mode = 'bars';
  }

  /**
   * Start the render loop. Safe to call multiple times.
   */
  start() {
    if (this._isRunning) return;
    this._isRunning = true;
    this._loop();
  }

  /**
   * Stop the render loop and clear the canvas.
   */
  stop() {
    this._isRunning = false;
    if (this._animationId) {
      cancelAnimationFrame(this._animationId);
      this._animationId = null;
    }
    this._clearCanvas();
    this._mode = 'idle';
  }

  /**
   * Switch to idle animation (no audio input).
   */
  setIdle() {
    this._mode = 'idle';
    this._teardownAudio();
  }

  /**
   * Switch render mode.
   * @param {'bars'|'waveform'|'idle'} mode
   */
  setMode(mode) {
    if (['bars', 'waveform', 'idle'].includes(mode)) {
      this._mode = mode;
    }
  }

  /**
   * Apply a colour theme preset.
   * @param {'dark'|'light'} theme
   */
  setTheme(theme) {
    if (theme === 'dark') {
      this.options.barColor    = '#06b6d4'; // cyan – pops on dark bg
      this.options.barColorAlt = '#7c3aed'; // violet
    } else {
      this.options.barColor    = '#4f46e5'; // indigo
      this.options.barColorAlt = '#06b6d4'; // cyan
    }
  }

  /**
   * Handle canvas / container resize.
   */
  resize() {
    const container = this.canvas.parentElement || this.canvas;
    const w = container.clientWidth  || this.canvas.clientWidth  || 300;
    const h = container.clientHeight || this.canvas.clientHeight || 64;
    const dpr = window.devicePixelRatio || 1;

    this.canvas.width  = w * dpr;
    this.canvas.height = h * dpr;
    this.canvas.style.width  = `${w}px`;
    this.canvas.style.height = `${h}px`;

    this.ctx.scale(dpr, dpr);
    this._logicalWidth  = w;
    this._logicalHeight = h;
  }

  /** Release all Web Audio resources and cancel animation. */
  destroy() {
    this.stop();
    this._teardownAudio();
    if (this._resizeObserver) {
      this._resizeObserver.disconnect();
    } else {
      window.removeEventListener('resize', this._onResize);
    }
  }

  /* ── Private rendering ──────────────────────────────────────── */

  _loop(ts = 0) {
    if (!this._isRunning) return;
    this._animationId = requestAnimationFrame((t) => this._loop(t));

    this._clearCanvas();

    if (this._mode === 'idle' || !this._analyser) {
      this._drawIdle(ts);
    } else if (this._mode === 'waveform') {
      this._analyser.getByteTimeDomainData(this._dataArray);
      this._drawWaveform(this._dataArray);
    } else {
      this._analyser.getByteFrequencyData(this._dataArray);
      this._drawBars(this._dataArray);
    }
  }

  _clearCanvas() {
    const { ctx } = this;
    const w = this._logicalWidth  || this.canvas.width;
    const h = this._logicalHeight || this.canvas.height;

    ctx.clearRect(0, 0, w, h);

    if (this.options.backgroundColor !== 'transparent') {
      ctx.fillStyle = this.options.backgroundColor;
      ctx.fillRect(0, 0, w, h);
    }
  }

  /**
   * Draw frequency bars.
   * @param {Uint8Array} dataArray
   */
  _drawBars(dataArray) {
    const { ctx, options } = this;
    const w  = this._logicalWidth;
    const h  = this._logicalHeight;

    const count   = Math.min(options.barCount, dataArray.length);
    const barW    = (w / count) - options.barGap;
    const gradient = ctx.createLinearGradient(0, h, 0, 0);
    gradient.addColorStop(0, options.barColor);
    gradient.addColorStop(1, options.barColorAlt);

    ctx.fillStyle = gradient;

    for (let i = 0; i < count; i++) {
      const normalized = dataArray[i] / 255;
      const barH = Math.max(options.minBarHeight, normalized * h * 0.9);
      const x    = i * (barW + options.barGap);
      const y    = h - barH;

      const radius = Math.min(barW / 2, 3);
      this._roundRect(x, y, barW, barH, radius);
    }
  }

  /**
   * Draw a time-domain waveform.
   * @param {Uint8Array} dataArray
   */
  _drawWaveform(dataArray) {
    const { ctx, options } = this;
    const w = this._logicalWidth;
    const h = this._logicalHeight;

    ctx.lineWidth   = 2;
    ctx.strokeStyle = options.barColor;
    ctx.shadowColor = options.barColorAlt;
    ctx.shadowBlur  = 4;

    ctx.beginPath();

    const sliceWidth = w / dataArray.length;
    let x = 0;

    for (let i = 0; i < dataArray.length; i++) {
      const v = dataArray[i] / 128;
      const y = (v * h) / 2;

      if (i === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
      x += sliceWidth;
    }

    ctx.lineTo(w, h / 2);
    ctx.stroke();
    ctx.shadowBlur = 0;
  }

  /**
   * Gentle idle pulse – sine-wave animation on a row of soft bars.
   * @param {number} timestamp  rAF timestamp (ms)
   */
  _drawIdle(timestamp) {
    const { ctx, options } = this;
    const w       = this._logicalWidth;
    const h       = this._logicalHeight;
    const count   = Math.min(options.barCount, 32);
    const barW    = (w / count) - options.barGap;
    const speed   = 0.0012; // radians per ms
    const t       = timestamp * speed;

    const gradient = ctx.createLinearGradient(0, 0, w, 0);
    gradient.addColorStop(0,   options.barColor + '66');
    gradient.addColorStop(0.5, options.barColorAlt + '99');
    gradient.addColorStop(1,   options.barColor + '66');

    ctx.fillStyle = gradient;

    for (let i = 0; i < count; i++) {
      const phase   = (i / count) * Math.PI * 2;
      const amp     = (Math.sin(t + phase) + 1) / 2; // 0..1
      const barH    = Math.max(options.minBarHeight, amp * h * 0.45 + h * 0.05);
      const x       = i * (barW + options.barGap);
      const y       = (h - barH) / 2; // centre vertically

      const radius  = Math.min(barW / 2, 3);
      this._roundRect(x, y, barW, barH, radius);
    }
  }

  /** Helper – fill a rounded rectangle. */
  _roundRect(x, y, w, h, r) {
    const { ctx } = this;
    if (w < 2 * r) r = w / 2;
    if (h < 2 * r) r = h / 2;

    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y,     x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x,     y + h, r);
    ctx.arcTo(x,     y + h, x,     y,     r);
    ctx.arcTo(x,     y,     x + w, y,     r);
    ctx.closePath();
    ctx.fill();
  }

  /** Disconnect and close Web Audio nodes. */
  _teardownAudio() {
    if (this._source) {
      try { this._source.disconnect(); } catch { /* ignore */ }
      this._source = null;
    }
    if (this._audioContext) {
      try { this._audioContext.close(); } catch { /* ignore */ }
      this._audioContext = null;
    }
    this._analyser  = null;
    this._dataArray = null;
  }

  _onResize() {
    this.resize();
  }
}

/* ── Expose globally ─────────────────────────────────────────── */
if (typeof window !== 'undefined') {
  window.AudioVisualizer = AudioVisualizer;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = AudioVisualizer;
}
