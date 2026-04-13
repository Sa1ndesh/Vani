/**
 * utils.js – Shared utilities for Vani-Kanoon Legal Assistant
 * Provides language data, storage, formatting, error handling,
 * API helpers, and common text-manipulation functions.
 */

'use strict';

/* ================================================================
   LANGUAGE & REGION DATA
   ================================================================ */

const SUPPORTED_LANGUAGES = {
  hi: { name: 'Hindi',    native: 'हिन्दी',    bcp47: 'hi-IN', rtl: false },
  kn: { name: 'Kannada',  native: 'ಕನ್ನಡ',    bcp47: 'kn-IN', rtl: false },
  mr: { name: 'Marathi',  native: 'मराठी',     bcp47: 'mr-IN', rtl: false },
  ta: { name: 'Tamil',    native: 'தமிழ்',     bcp47: 'ta-IN', rtl: false },
  te: { name: 'Telugu',   native: 'తెలుగు',   bcp47: 'te-IN', rtl: false },
  en: { name: 'English',  native: 'English',   bcp47: 'en-IN', rtl: false },
};

const INDIAN_STATES = [
  'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar',
  'Chhattisgarh', 'Goa', 'Gujarat', 'Haryana', 'Himachal Pradesh',
  'Jharkhand', 'Karnataka', 'Kerala', 'Madhya Pradesh', 'Maharashtra',
  'Manipur', 'Meghalaya', 'Mizoram', 'Nagaland', 'Odisha', 'Punjab',
  'Rajasthan', 'Sikkim', 'Tamil Nadu', 'Telangana', 'Tripura',
  'Uttar Pradesh', 'Uttarakhand', 'West Bengal',
  // Union Territories
  'Andaman and Nicobar Islands', 'Chandigarh',
  'Dadra and Nagar Haveli and Daman and Diu', 'Delhi (NCT)',
  'Jammu and Kashmir', 'Ladakh', 'Lakshadweep', 'Puducherry',
];

/**
 * Returns a language's BCP-47 tag for use with Web Speech API / TTS.
 * @param {string} langCode  e.g. 'hi'
 * @returns {string}
 */
function getBCP47(langCode) {
  const lang = SUPPORTED_LANGUAGES[langCode];
  return lang ? lang.bcp47 : 'en-IN';
}

/* ================================================================
   STORAGE MANAGEMENT
   ================================================================ */

const Storage = {
  /**
   * Retrieve a value from localStorage, returning defaultVal if absent or
   * if JSON parsing fails.
   * @param {string} key
   * @param {*} [defaultVal=null]
   * @returns {*}
   */
  get(key, defaultVal = null) {
    try {
      const raw = localStorage.getItem(key);
      return raw === null ? defaultVal : JSON.parse(raw);
    } catch {
      return defaultVal;
    }
  },

  /**
   * Store a value in localStorage (serialised with JSON.stringify).
   * @param {string} key
   * @param {*} value
   */
  set(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (err) {
      console.warn('[Storage.set] Could not write to localStorage:', err.message);
    }
  },

  /** Remove a specific key. */
  remove(key) {
    try {
      localStorage.removeItem(key);
    } catch { /* ignore */ }
  },

  /** Remove all Vani-Kanoon keys (prefixed with "vk_"). */
  clear() {
    try {
      const toRemove = Object.keys(localStorage).filter(k => k.startsWith('vk_'));
      toRemove.forEach(k => localStorage.removeItem(k));
    } catch { /* ignore */ }
  },
};

/* Storage key constants */
const STORAGE_KEYS = {
  THEME:       'vk_theme',
  LANGUAGE:    'vk_language',
  STATE:       'vk_state',
  HISTORY:     'vk_conversation_history',
  SETTINGS:    'vk_settings',
  DISCLAIMER:  'vk_disclaimer_ack',
};

/* ================================================================
   FORMATTER UTILITIES
   ================================================================ */

const Formatter = {
  /**
   * Format a legal citation from section number and act name.
   * e.g. legalCitation('302', 'IPC') → "Section 302, IPC"
   * @param {string|number} section
   * @param {string} act
   * @returns {string}
   */
  legalCitation(section, act) {
    if (!section && !act) return 'Unknown Provision';
    if (!section) return act;
    if (!act) return `Section ${section}`;
    return `Section ${section}, ${act}`;
  },

  /**
   * Format an ISO date string to a locale-friendly string.
   * @param {string} dateStr
   * @param {string} [locale='en-IN']
   * @returns {string}
   */
  date(dateStr, locale = 'en-IN') {
    if (!dateStr) return '';
    try {
      return new Date(dateStr).toLocaleDateString(locale, {
        year: 'numeric', month: 'short', day: 'numeric',
      });
    } catch {
      return dateStr;
    }
  },

  /**
   * Format a duration in seconds to MM:SS or HH:MM:SS.
   * @param {number} seconds
   * @returns {string}
   */
  duration(seconds) {
    if (typeof seconds !== 'number' || isNaN(seconds)) return '0:00';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    const pad = n => String(n).padStart(2, '0');
    return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
  },

  /**
   * Format a file size in bytes to a human-readable string.
   * @param {number} bytes
   * @returns {string}
   */
  fileSize(bytes) {
    if (typeof bytes !== 'number' || bytes < 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    let size = bytes;
    while (size >= 1024 && i < units.length - 1) {
      size /= 1024;
      i++;
    }
    return `${size.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
  },

  /**
   * Format a timestamp for chat messages.
   * @param {Date|string} [date=new Date()]
   * @returns {string}  e.g. "10:34 AM"
   */
  timeLabel(date = new Date()) {
    try {
      return new Date(date).toLocaleTimeString('en-IN', {
        hour: '2-digit', minute: '2-digit', hour12: true,
      });
    } catch {
      return '';
    }
  },
};

/* ================================================================
   ERROR HANDLER
   ================================================================ */

const ErrorHandler = {
  /**
   * Central error handler – logs to console and optionally shows a toast.
   * @param {Error|string} error
   * @param {string} [context='']
   */
  handle(error, context = '') {
    const msg = error instanceof Error ? error.message : String(error);
    console.error(`[Vani-Kanoon]${context ? ` [${context}]` : ''} ${msg}`);
    if (error instanceof Error && error.stack) {
      console.debug(error.stack);
    }
    this.display(msg, 'error');
  },

  /**
   * Display a toast notification.
   * @param {string} message
   * @param {'error'|'warning'|'success'|'info'} [type='info']
   * @param {number} [duration=5000]  ms
   */
  display(message, type = 'info', duration = 5000) {
    const ICONS = {
      error:   '❌',
      warning: '⚠️',
      success: '✅',
      info:    'ℹ️',
    };

    const TITLES = {
      error:   'Error',
      warning: 'Warning',
      success: 'Success',
      info:    'Info',
    };

    // Build toast element
    const toast = document.createElement('div');
    toast.className = `toast toast--${type}`;
    toast.setAttribute('role', type === 'error' ? 'alert' : 'status');
    toast.setAttribute('aria-live', type === 'error' ? 'assertive' : 'polite');
    toast.innerHTML = `
      <span class="toast__icon" aria-hidden="true">${ICONS[type] || 'ℹ️'}</span>
      <div class="toast__body">
        <div class="toast__title">${escapeHtml(TITLES[type])}</div>
        <div class="toast__msg">${escapeHtml(message)}</div>
      </div>
    `;

    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'toast-container';
      container.setAttribute('aria-label', 'Notifications');
      document.body.appendChild(container);
    }

    container.appendChild(toast);

    // Auto-dismiss
    const dismiss = () => {
      toast.classList.add('removing');
      toast.addEventListener('transitionend', () => toast.remove(), { once: true });
    };

    const timer = setTimeout(dismiss, duration);

    // Allow manual dismiss on click
    toast.addEventListener('click', () => {
      clearTimeout(timer);
      dismiss();
    });
  },
};

/* ================================================================
   API UTILITIES
   ================================================================ */

const API = {
  BASE_URL: (() => {
    // Respect environment override; fall back to localhost
    if (typeof window !== 'undefined' && window.VANI_API_URL) {
      return window.VANI_API_URL;
    }
    return 'http://localhost:8000';
  })(),

  /** Default request timeout in ms */
  TIMEOUT_MS: 30000,

  /**
   * Send a POST request to an API endpoint.
   * @param {string} endpoint  Path relative to BASE_URL, e.g. '/legal/query'
   * @param {object} data      Request body (will be JSON-serialised)
   * @param {AbortSignal} [signal]
   * @returns {Promise<any>}   Parsed JSON response
   */
  async post(endpoint, data, signal) {
    return this._request('POST', endpoint, data, signal);
  },

  /**
   * Send a GET request.
   * @param {string} endpoint
   * @param {AbortSignal} [signal]
   * @returns {Promise<any>}
   */
  async get(endpoint, signal) {
    return this._request('GET', endpoint, null, signal);
  },

  /**
   * Post FormData (for file/audio uploads – no Content-Type header so the
   * browser sets multipart/form-data with boundary automatically).
   * @param {string} endpoint
   * @param {FormData} formData
   * @param {AbortSignal} [signal]
   * @returns {Promise<any>}
   */
  async postForm(endpoint, formData, signal) {
    const url = `${this.BASE_URL}${endpoint}`;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.TIMEOUT_MS);

    const mergedSignal = signal
      ? _mergeSignals(signal, controller.signal)
      : controller.signal;

    try {
      const res = await fetch(url, {
        method: 'POST',
        body: formData,
        signal: mergedSignal,
      });
      clearTimeout(timeoutId);
      return await this._parseResponse(res);
    } catch (err) {
      clearTimeout(timeoutId);
      throw this._normalizeError(err);
    }
  },

  /** Internal fetch wrapper. */
  async _request(method, endpoint, data, signal) {
    const url = `${this.BASE_URL}${endpoint}`;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.TIMEOUT_MS);

    const mergedSignal = signal
      ? _mergeSignals(signal, controller.signal)
      : controller.signal;

    const opts = {
      method,
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      signal: mergedSignal,
    };
    if (data !== null && data !== undefined) {
      opts.body = JSON.stringify(data);
    }

    try {
      const res = await fetch(url, opts);
      clearTimeout(timeoutId);
      return await this._parseResponse(res);
    } catch (err) {
      clearTimeout(timeoutId);
      throw this._normalizeError(err);
    }
  },

  async _parseResponse(res) {
    let body;
    const contentType = res.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      body = await res.json();
    } else {
      body = await res.text();
    }
    if (!res.ok) {
      const message = (typeof body === 'object' && body.detail)
        ? body.detail
        : (typeof body === 'string' ? body : `HTTP ${res.status}`);
      const err = new Error(message);
      err.status = res.status;
      err.body = body;
      throw err;
    }
    return body;
  },

  _normalizeError(err) {
    if (err.name === 'AbortError') {
      return Object.assign(new Error('Request timed out or was cancelled.'), { type: 'timeout' });
    }
    if (err.message && err.message.includes('Failed to fetch')) {
      return Object.assign(new Error('Cannot reach the server. Please check your connection.'), { type: 'network' });
    }
    return err;
  },
};

/** Merge two AbortSignals – aborts when either fires. */
function _mergeSignals(a, b) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  a.addEventListener('abort', abort, { once: true });
  b.addEventListener('abort', abort, { once: true });
  return controller.signal;
}

/* ================================================================
   DEBOUNCE & THROTTLE
   ================================================================ */

/**
 * Debounce – returns a function that delays invoking `fn` until `delay` ms
 * have elapsed since the last invocation.
 * @param {Function} fn
 * @param {number} delay  ms
 * @returns {Function}
 */
function debounce(fn, delay) {
  let timer;
  function debounced(...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  }
  debounced.cancel = () => clearTimeout(timer);
  return debounced;
}

/**
 * Throttle – returns a function that invokes `fn` at most once per `limit` ms.
 * @param {Function} fn
 * @param {number} limit  ms
 * @returns {Function}
 */
function throttle(fn, limit) {
  let lastCall = 0;
  let timer;
  return function throttled(...args) {
    const now = Date.now();
    const remaining = limit - (now - lastCall);
    if (remaining <= 0) {
      clearTimeout(timer);
      lastCall = now;
      fn.apply(this, args);
    } else {
      clearTimeout(timer);
      timer = setTimeout(() => {
        lastCall = Date.now();
        fn.apply(this, args);
      }, remaining);
    }
  };
}

/* ================================================================
   TEXT UTILITIES
   ================================================================ */

/**
 * Truncate text to `maxLength` characters, appending an ellipsis if cut.
 * @param {string} text
 * @param {number} maxLength
 * @param {string} [ellipsis='…']
 * @returns {string}
 */
function truncateText(text, maxLength, ellipsis = '…') {
  if (typeof text !== 'string') return '';
  if (text.length <= maxLength) return text;
  // Avoid cutting mid-word where possible
  const cut = text.lastIndexOf(' ', maxLength - ellipsis.length);
  const end = cut > maxLength * 0.6 ? cut : maxLength - ellipsis.length;
  return text.slice(0, end) + ellipsis;
}

/**
 * Wrap occurrences of each keyword in `text` with a <mark> element.
 * Case-insensitive. Returns an HTML string.
 * @param {string} text
 * @param {string[]} keywords
 * @returns {string}  HTML string (safe – text is escaped first)
 */
function highlightKeywords(text, keywords) {
  if (!text) return '';
  let escaped = escapeHtml(text);
  if (!keywords || keywords.length === 0) return escaped;

  keywords
    .filter(k => k && k.trim())
    .sort((a, b) => b.length - a.length) // longest first to avoid partial-match issues
    .forEach(kw => {
      const safe = escapeHtml(kw).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const re = new RegExp(`(${safe})`, 'gi');
      escaped = escaped.replace(re, '<mark class="highlight">$1</mark>');
    });

  return escaped;
}

/**
 * Escape HTML special characters to prevent XSS.
 * @param {string} text
 * @returns {string}
 */
function escapeHtml(text) {
  if (typeof text !== 'string') return String(text ?? '');
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;');
}

/**
 * Strip HTML tags from a string, returning plain text.
 * @param {string} html
 * @returns {string}
 */
function stripHtml(html) {
  if (typeof html !== 'string') return '';
  return html.replace(/<[^>]*>/g, '');
}

/**
 * Generate a simple unique ID (non-cryptographic).
 * @param {string} [prefix='id']
 * @returns {string}
 */
function uid(prefix = 'id') {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

/**
 * Detect whether text contains Devanagari (Hindi/Marathi) characters.
 * @param {string} text
 * @returns {boolean}
 */
function isDevanagari(text) {
  return /[\u0900-\u097F]/.test(text);
}

/**
 * Auto-detect the probable language code of a short text snippet.
 * Returns 'en' by default when detection is uncertain.
 * @param {string} text
 * @returns {string}  Language code
 */
function detectLanguage(text) {
  if (!text || text.trim().length < 3) return 'en';
  if (/[\u0900-\u097F]/.test(text)) {
    // Both Hindi and Marathi use Devanagari – default to Hindi
    return 'hi';
  }
  if (/[\u0C80-\u0CFF]/.test(text)) return 'kn'; // Kannada
  if (/[\u0B80-\u0BFF]/.test(text)) return 'ta'; // Tamil
  if (/[\u0C00-\u0C7F]/.test(text)) return 'te'; // Telugu
  return 'en';
}

/* ================================================================
   DOM UTILITIES
   ================================================================ */

/**
 * Safely query a selector; logs a warning instead of throwing.
 * @param {string} selector
 * @param {Element|Document} [root=document]
 * @returns {Element|null}
 */
function qs(selector, root = document) {
  try {
    return root.querySelector(selector);
  } catch (err) {
    console.warn(`[qs] Invalid selector "${selector}":`, err.message);
    return null;
  }
}

/**
 * Safely query all matching elements.
 * @param {string} selector
 * @param {Element|Document} [root=document]
 * @returns {Element[]}
 */
function qsAll(selector, root = document) {
  try {
    return Array.from(root.querySelectorAll(selector));
  } catch {
    return [];
  }
}

/**
 * Add a delegated event listener to a parent element.
 * @param {Element} parent
 * @param {string} eventType
 * @param {string} childSelector
 * @param {Function} handler
 */
function delegate(parent, eventType, childSelector, handler) {
  parent.addEventListener(eventType, (e) => {
    const target = e.target.closest(childSelector);
    if (target && parent.contains(target)) {
      handler.call(target, e, target);
    }
  });
}

/* ================================================================
   MISC HELPERS
   ================================================================ */

/**
 * Deep-clone a plain object/array (uses JSON round-trip).
 * @param {*} obj
 * @returns {*}
 */
function deepClone(obj) {
  return JSON.parse(JSON.stringify(obj));
}

/**
 * Clamp a number between min and max.
 * @param {number} val
 * @param {number} min
 * @param {number} max
 * @returns {number}
 */
function clamp(val, min, max) {
  return Math.min(Math.max(val, min), max);
}

/**
 * Convert an ArrayBuffer to a Base64-encoded string.
 * @param {ArrayBuffer} buffer
 * @returns {string}
 */
function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

/**
 * Convert a Base64 string back to an ArrayBuffer.
 * @param {string} base64
 * @returns {ArrayBuffer}
 */
function base64ToArrayBuffer(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

/* ================================================================
   EXPORTS (browser global + ESM-compatible)
   ================================================================ */

// Make everything available on the global `window` object for inline
// script usage, while also supporting ES module environments.
const VaniUtils = {
  SUPPORTED_LANGUAGES,
  INDIAN_STATES,
  STORAGE_KEYS,
  getBCP47,
  Storage,
  Formatter,
  ErrorHandler,
  API,
  debounce,
  throttle,
  truncateText,
  highlightKeywords,
  escapeHtml,
  stripHtml,
  uid,
  isDevanagari,
  detectLanguage,
  qs,
  qsAll,
  delegate,
  deepClone,
  clamp,
  arrayBufferToBase64,
  base64ToArrayBuffer,
};

if (typeof window !== 'undefined') {
  window.VaniUtils = VaniUtils;
  // Also expose common helpers at top-level for convenience in HTML scripts
  Object.assign(window, {
    SUPPORTED_LANGUAGES,
    INDIAN_STATES,
    STORAGE_KEYS,
    getBCP47,
    Storage,
    Formatter,
    ErrorHandler,
    API,
    debounce,
    throttle,
    truncateText,
    highlightKeywords,
    escapeHtml,
    stripHtml,
    uid,
    detectLanguage,
    qs,
    qsAll,
    delegate,
  });
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = VaniUtils;
}
