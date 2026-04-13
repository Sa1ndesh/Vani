/**
 * legal-query.js – Legal query submission and response handling
 * for Vani-Kanoon Legal Assistant.
 *
 * Manages:
 *  • Text and voice query submission to backend
 *  • Document analysis
 *  • Simplified legal explanations
 *  • Legal term search
 *  • Conversation history (in-memory + localStorage)
 *  • Chat UI rendering (messages, citations, typing indicators)
 *  • Export and clear
 */

'use strict';

class LegalQueryManager {
  /**
   * @param {object} [options]
   * @param {string}  [options.chatContainerId='chat-messages']
   * @param {string}  [options.citationsContainerId='citations-panel']
   * @param {number}  [options.maxHistoryItems=100]
   */
  constructor(options = {}) {
    this.options = Object.assign({
      chatContainerId:      'chat-messages',
      citationsContainerId: 'citations-panel',
      maxHistoryItems:      100,
    }, options);

    /** @type {Array<{id:string, role:'user'|'assistant'|'error', content:string, timestamp:string, language:string, citations?:Array}>} */
    this.conversationHistory = [];

    this.currentState    = null;
    this.currentLanguage = 'hi';
    this.isProcessing    = false;

    this._abortController = null;

    // Restore persisted history
    this._loadHistory();

    // Resolve helpers (may be loaded before or after utils.js)
    this._api      = () => (typeof API      !== 'undefined' ? API      : null);
    this._esc      = () => (typeof escapeHtml !== 'undefined' ? escapeHtml : s => s);
    this._fmt      = () => (typeof Formatter  !== 'undefined' ? Formatter  : null);
    this._uid      = () => (typeof uid        !== 'undefined' ? uid()      : `${Date.now()}`);
  }

  /* ── Language / State setters ───────────────────────────────── */

  /** @param {string} langCode  e.g. 'hi', 'kn', 'en' */
  setLanguage(langCode) {
    this.currentLanguage = langCode;
  }

  /** @param {string} stateName  e.g. 'Maharashtra' */
  setState(stateName) {
    this.currentState = stateName;
  }

  /* ── Query submission ───────────────────────────────────────── */

  /**
   * Submit a plain-text legal query to the /legal/query endpoint.
   * Renders the user message, shows a typing indicator, then renders
   * the assistant response and any citations.
   *
   * @param {string} query
   * @param {object} [opts]
   * @param {boolean} [opts.speak=false]  Whether to play TTS on the response
   * @returns {Promise<object>}  Raw backend response
   */
  async submitQuery(query, opts = {}) {
    if (!query || !query.trim()) return;
    if (this.isProcessing) {
      ErrorHandler.display('Please wait for the current response to complete.', 'warning');
      return;
    }

    const trimmed = query.trim();

    // Show user message
    this.displayMessage(trimmed, 'user');

    // Show typing indicator
    const typingId = this._showTypingIndicator();
    this.isProcessing = true;
    this._abortController = new AbortController();

    const payload = {
      query:    trimmed,
      language: this.currentLanguage,
      state:    this.currentState || undefined,
      history:  this._buildHistoryContext(),
    };

    let response;
    try {
      const api = this._api();
      if (api) {
        response = await api.post('/legal/query', payload, this._abortController.signal);
      } else {
        response = await this._rawPost('/legal/query', payload, this._abortController.signal);
      }
    } catch (err) {
      this._removeTypingIndicator(typingId);
      this.isProcessing = false;

      if (err.name === 'AbortError' || (err.type === 'timeout')) {
        this.displayMessage('The request timed out. Please try again.', 'error');
      } else if (err.type === 'network') {
        this.displayMessage('Cannot reach the server. Please check that the backend is running.', 'error');
      } else {
        this.displayMessage(err.message || 'An unexpected error occurred.', 'error');
      }
      this.handleError(err);
      return null;
    }

    this._removeTypingIndicator(typingId);
    this.isProcessing = false;

    const formatted = this.formatLegalResponse(response);
    this.displayMessage(formatted.answer, 'assistant', formatted.citations);

    this._saveHistory();
    return response;
  }

  /**
   * Submit a voice recording: first transcribes it, then sends the text.
   * @param {Blob}   audioBlob
   * @param {object} [voiceHandler]  A VoiceHandler instance for transcription
   * @returns {Promise<object|null>}
   */
  async submitVoiceQuery(audioBlob, voiceHandler) {
    if (!audioBlob) return null;

    this.isProcessing = true;
    let transcript;

    try {
      let result;
      if (voiceHandler && typeof voiceHandler.transcribeAudio === 'function') {
        result = await voiceHandler.transcribeAudio(audioBlob, this.currentLanguage);
      } else {
        // Fallback: post directly
        const formData = new FormData();
        formData.append('audio', audioBlob, 'recording.webm');
        formData.append('language', this.currentLanguage);
        const res = await fetch(`${this._baseUrl()}/speech/transcribe`, {
          method: 'POST',
          body: formData,
        });
        result = await res.json();
      }
      transcript = result.transcript || result.text || '';
    } catch (err) {
      this.isProcessing = false;
      this.displayMessage('Could not transcribe audio. Please try typing your question.', 'error');
      this.handleError(err);
      return null;
    }

    if (!transcript.trim()) {
      this.isProcessing = false;
      this.displayMessage('No speech detected. Please speak clearly and try again.', 'error');
      return null;
    }

    this.isProcessing = false;

    // Populate text input with transcript for user visibility
    const textInput = document.getElementById('text-input');
    if (textInput) textInput.value = transcript;

    return this.submitQuery(transcript);
  }

  /**
   * Analyse an uploaded or pasted legal document.
   * @param {string} text  Document text
   * @returns {Promise<object>}
   */
  async analyzeDocument(text) {
    if (!text || !text.trim()) {
      ErrorHandler.display('Please provide document text to analyse.', 'warning');
      return null;
    }

    const typingId = this._showTypingIndicator();
    this.isProcessing = true;

    this.displayMessage(`📄 Analysing document (${text.length} characters)…`, 'user');

    const payload = { text, language: this.currentLanguage, state: this.currentState };

    let response;
    try {
      const api = this._api();
      response = api
        ? await api.post('/legal/analyze', payload)
        : await this._rawPost('/legal/analyze', payload);
    } catch (err) {
      this._removeTypingIndicator(typingId);
      this.isProcessing = false;
      this.displayMessage(err.message || 'Document analysis failed.', 'error');
      this.handleError(err);
      return null;
    }

    this._removeTypingIndicator(typingId);
    this.isProcessing = false;

    const formatted = this.formatLegalResponse(response);
    this.displayMessage(formatted.answer, 'assistant', formatted.citations);
    this._saveHistory();
    return response;
  }

  /**
   * Get a simplified explanation of a law section.
   * @param {string|number} section
   * @param {string} act  e.g. 'IPC', 'CrPC'
   * @returns {Promise<object>}
   */
  async getSimplifiedExplanation(section, act) {
    const citation = `Section ${section}, ${act}`;
    this.displayMessage(`🔍 Explain ${citation} in simple language`, 'user');

    const typingId = this._showTypingIndicator();
    this.isProcessing = true;

    const payload = { section: String(section), act, language: this.currentLanguage };

    let response;
    try {
      const api = this._api();
      response = api
        ? await api.post('/legal/simplified-explain', payload)
        : await this._rawPost('/legal/simplified-explain', payload);
    } catch (err) {
      this._removeTypingIndicator(typingId);
      this.isProcessing = false;
      this.displayMessage(err.message || 'Could not fetch explanation.', 'error');
      this.handleError(err);
      return null;
    }

    this._removeTypingIndicator(typingId);
    this.isProcessing = false;

    const formatted = this.formatLegalResponse(response);
    this.displayMessage(formatted.answer, 'assistant', formatted.citations);
    this._saveHistory();
    return response;
  }

  /**
   * Search for a legal term or topic.
   * @param {string} searchTerm
   * @returns {Promise<object>}
   */
  async searchLegal(searchTerm) {
    if (!searchTerm || !searchTerm.trim()) return null;

    const typingId = this._showTypingIndicator();
    this.isProcessing = true;

    const api = this._api();
    let response;
    try {
      const endpoint = `/legal/search?q=${encodeURIComponent(searchTerm)}&lang=${this.currentLanguage}`;
      response = api
        ? await api.get(endpoint)
        : await this._rawGet(endpoint);
    } catch (err) {
      this._removeTypingIndicator(typingId);
      this.isProcessing = false;
      this.displayMessage(err.message || 'Search failed.', 'error');
      this.handleError(err);
      return null;
    }

    this._removeTypingIndicator(typingId);
    this.isProcessing = false;

    const formatted = this.formatLegalResponse(response);
    this.displayMessage(formatted.answer, 'assistant', formatted.citations);
    return response;
  }

  /* ── UI: messages ───────────────────────────────────────────── */

  /**
   * Render a message bubble in the chat container.
   * @param {string} message   Plain text (will be HTML-escaped)
   * @param {'user'|'assistant'|'error'} type
   * @param {Array}  [citations=[]]
   * @param {string} [language]
   */
  displayMessage(message, type, citations = [], language) {
    const container = document.getElementById(this.options.chatContainerId);
    if (!container) return;

    // Remove empty state if present
    const emptyState = container.querySelector('.chat-empty');
    if (emptyState) emptyState.remove();

    const id        = this._uid();
    const lang      = language || this.currentLanguage;
    const timestamp = new Date().toISOString();
    const timeLabel = this._fmt() ? this._fmt().timeLabel(timestamp) : '';
    const esc       = this._esc();

    // Persist to history
    if (type === 'user' || type === 'assistant') {
      this.conversationHistory.push({
        id, role: type, content: message, timestamp, language: lang,
        citations: citations || [],
      });

      // Trim history
      if (this.conversationHistory.length > this.options.maxHistoryItems) {
        this.conversationHistory.splice(0, this.conversationHistory.length - this.options.maxHistoryItems);
      }
    }

    const isUser      = type === 'user';
    const isError     = type === 'error';
    const avatarLabel = isUser ? '👤' : isError ? '⚠️' : '⚖️';
    const langLabel   = lang.toUpperCase();

    // Format message: convert newlines to <br> and handle basic markdown-ish bold
    const formattedContent = this._formatMessageContent(message, esc);

    const citationsHtml = (citations && citations.length)
      ? this._buildCitationsHtml(citations)
      : '';

    const rowEl = document.createElement('div');
    rowEl.className = `message-row message-row--${isUser ? 'user' : isError ? 'error' : 'assistant'}`;
    rowEl.dataset.messageId = id;
    rowEl.setAttribute('role', 'listitem');

    rowEl.innerHTML = `
      <div class="message-avatar" aria-hidden="true">${avatarLabel}</div>
      <div class="message-bubble ${isError ? 'message-bubble--error' : ''}">
        <span class="message-bubble__lang-tag">${esc(langLabel)}</span>
        <div class="message-bubble__content">${formattedContent}</div>
        ${citationsHtml}
        <span class="message-bubble__timestamp" aria-label="Sent at ${timeLabel}">${esc(timeLabel)}</span>
      </div>
    `;

    container.appendChild(rowEl);
    this._scrollToBottom(container);
  }

  /**
   * Render a standalone citations panel (e.g. in a sidebar).
   * @param {Array} citations
   */
  displayCitations(citations) {
    const panel = document.getElementById(this.options.citationsContainerId);
    if (!panel || !citations || citations.length === 0) return;

    panel.innerHTML = `
      <div class="citations-title">
        <span>📚</span> Related Laws (${citations.length})
      </div>
      ${citations.map(c => this._buildCitationCard(c)).join('')}
    `;
  }

  /* ── History management ─────────────────────────────────────── */

  /** Clear conversation history from memory and DOM. */
  clearHistory() {
    this.conversationHistory = [];
    this._saveHistory();

    const container = document.getElementById(this.options.chatContainerId);
    if (container) {
      container.innerHTML = '';
      this._renderEmptyState(container);
    }

    const citationsPanel = document.getElementById(this.options.citationsContainerId);
    if (citationsPanel) citationsPanel.innerHTML = '';
  }

  /**
   * Export conversation history as a formatted plain-text string and
   * trigger a browser download.
   */
  exportHistory() {
    if (!this.conversationHistory.length) {
      ErrorHandler.display('No conversation history to export.', 'info');
      return;
    }

    const fmt = this._fmt();
    const lines = [
      'Vani-Kanoon Legal Assistant – Conversation Export',
      `Exported: ${new Date().toLocaleString('en-IN')}`,
      `Language: ${this.currentLanguage}`,
      this.currentState ? `State: ${this.currentState}` : '',
      '='.repeat(60),
      '',
    ];

    this.conversationHistory.forEach(msg => {
      const ts   = fmt ? fmt.date(msg.timestamp) : msg.timestamp;
      const role = msg.role === 'user' ? 'YOU' : 'ASSISTANT';
      lines.push(`[${ts}] ${role}:`);
      lines.push(msg.content);
      if (msg.citations && msg.citations.length) {
        lines.push('  Cited laws:');
        msg.citations.forEach(c => {
          lines.push(`    • ${c.section || ''} ${c.act || c.title || ''}`.trim());
        });
      }
      lines.push('');
    });

    lines.push('─'.repeat(60));
    lines.push('DISCLAIMER: This is not a substitute for professional legal advice.');

    const content = lines.filter(l => l !== null && l !== undefined).join('\n');
    this._downloadText(content, `vani-kanoon-export-${Date.now()}.txt`);
  }

  /* ── Response formatting ────────────────────────────────────── */

  /**
   * Parse a raw backend response into a normalised {answer, citations} object.
   * Handles multiple possible response shapes.
   * @param {object|string} response
   * @returns {{answer: string, citations: Array}}
   */
  formatLegalResponse(response) {
    if (!response) {
      return { answer: 'No response received from the server.', citations: [] };
    }

    if (typeof response === 'string') {
      return { answer: response, citations: [] };
    }

    // Normalise possible response shapes from the backend
    const answer =
      response.answer     ||
      response.response   ||
      response.message    ||
      response.result     ||
      response.text       ||
      'I could not generate a response for that query.';

    const rawCitations =
      response.citations  ||
      response.references ||
      response.laws       ||
      response.results    ||
      [];

    const citations = Array.isArray(rawCitations)
      ? rawCitations.map(c => this._normaliseCitation(c))
      : [];

    return { answer, citations };
  }

  /** Central error handler – delegates to global ErrorHandler if available. */
  handleError(error) {
    if (typeof ErrorHandler !== 'undefined') {
      ErrorHandler.handle(error, 'LegalQueryManager');
    } else {
      console.error('[LegalQueryManager]', error);
    }
  }

  /* ── Private helpers ────────────────────────────────────────── */

  _buildHistoryContext(maxItems = 6) {
    return this.conversationHistory
      .slice(-maxItems)
      .map(({ role, content }) => ({ role, content }));
  }

  _normaliseCitation(c) {
    if (typeof c === 'string') {
      return { act: '', section: '', title: c, description: '', relevance: 0, tags: [] };
    }
    return {
      act:         c.act         || c.statute    || '',
      section:     c.section     || c.provision  || '',
      title:       c.title       || c.heading    || `${c.act || ''} ${c.section || ''}`.trim(),
      description: c.description || c.summary    || c.text || '',
      relevance:   typeof c.relevance === 'number' ? c.relevance : (c.score || 0),
      tags:        Array.isArray(c.tags) ? c.tags : (c.category ? [c.category] : []),
      url:         c.url         || c.source_url || '',
    };
  }

  _buildCitationsHtml(citations) {
    if (!citations.length) return '';
    const esc = this._esc();
    const cards = citations.map(c => this._buildCitationCard(c, true)).join('');
    return `
      <div class="citations-container">
        <div class="citations-title"><span>📚</span> Referenced Laws</div>
        ${cards}
      </div>
    `;
  }

  _buildCitationCard(c, compact = false) {
    const esc = this._esc();
    const relevancePct = Math.round(Math.min(100, Math.max(0, (c.relevance || 0) * 100)));
    const tagsHtml = (c.tags || []).map(t => `<span class="citation-tag">${esc(t)}</span>`).join('');
    const desc = compact
      ? (c.description ? `<div class="citation-card__description">${esc(c.description)}</div>` : '')
      : `<div class="citation-card__description">${esc(c.description || 'No description available.')}</div>`;

    return `
      <div class="citation-card" 
           tabindex="0" 
           role="article"
           aria-label="${esc(c.title || [c.act, c.section].filter(Boolean).join(' '))}"
           data-act="${esc(c.act || '')}"
           data-section="${esc(c.section || '')}"
           data-url="${esc(c.url || '')}">
        ${c.act ? `<div class="citation-card__act">${esc(c.act)}</div>` : ''}
        <div class="citation-card__section">${esc(c.title || c.section || 'Legal Provision')}</div>
        ${desc}
        <div class="citation-card__footer">
          <div>${tagsHtml}</div>
          ${relevancePct > 0 ? `
            <div class="citation-relevance" aria-label="Relevance ${relevancePct}%">
              <div class="relevance-bar">
                <div class="relevance-bar__fill" style="width:${relevancePct}%"></div>
              </div>
              ${relevancePct}%
            </div>` : ''}
        </div>
      </div>
    `;
  }

  _formatMessageContent(text, esc) {
    let html = esc(text);
    // Bold: **text** → <strong>
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Italic: *text* → <em>
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    // Newlines → <br>
    html = html.replace(/\n/g, '<br>');
    return html;
  }

  _showTypingIndicator() {
    const container = document.getElementById(this.options.chatContainerId);
    if (!container) return null;

    const id = `typing_${Date.now()}`;
    const row = document.createElement('div');
    row.className = 'message-row message-row--assistant';
    row.id = id;
    row.setAttribute('aria-label', 'Assistant is typing');
    row.innerHTML = `
      <div class="message-avatar" aria-hidden="true">⚖️</div>
      <div class="message-bubble">
        <div class="typing-indicator" role="status" aria-live="polite">
          <div class="typing-indicator__dot"></div>
          <div class="typing-indicator__dot"></div>
          <div class="typing-indicator__dot"></div>
        </div>
      </div>
    `;
    container.appendChild(row);
    this._scrollToBottom(container);
    return id;
  }

  _removeTypingIndicator(id) {
    if (!id) return;
    const el = document.getElementById(id);
    if (el) el.remove();
  }

  _renderEmptyState(container) {
    container.innerHTML = `
      <div class="chat-empty" role="status" aria-label="No messages yet">
        <div class="chat-empty__icon" aria-hidden="true">⚖️</div>
        <div class="chat-empty__title">Vani-Kanoon Legal Assistant</div>
        <div class="chat-empty__desc">
          Ask any legal question in your language. You can type or use
          the microphone button below.
        </div>
        <div class="quick-actions" id="quick-actions" role="list" aria-label="Quick action suggestions"></div>
      </div>
    `;
  }

  _scrollToBottom(container) {
    requestAnimationFrame(() => {
      container.scrollTop = container.scrollHeight;
    });
  }

  _saveHistory() {
    try {
      const key = typeof STORAGE_KEYS !== 'undefined' ? STORAGE_KEYS.HISTORY : 'vk_conversation_history';
      const toSave = this.conversationHistory.slice(-50); // save last 50 only
      localStorage.setItem(key, JSON.stringify(toSave));
    } catch { /* quota exceeded – ignore */ }
  }

  _loadHistory() {
    try {
      const key = typeof STORAGE_KEYS !== 'undefined' ? STORAGE_KEYS.HISTORY : 'vk_conversation_history';
      const raw = localStorage.getItem(key);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          this.conversationHistory = parsed;
        }
      }
    } catch { /* corrupt data – ignore */ }
  }

  _baseUrl() {
    if (typeof API !== 'undefined' && API.BASE_URL) return API.BASE_URL;
    if (typeof window !== 'undefined' && window.VANI_API_URL) return window.VANI_API_URL;
    return 'http://localhost:8000';
  }

  async _rawPost(endpoint, data, signal) {
    const res = await fetch(`${this._baseUrl()}${endpoint}`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(data),
      signal,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  async _rawGet(endpoint, signal) {
    const res = await fetch(`${this._baseUrl()}${endpoint}`, { signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  _downloadText(content, filename) {
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = filename;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 2000);
  }

  _uid() {
    return typeof uid === 'function' ? uid('msg') : `msg_${Date.now()}_${Math.random().toString(36).slice(2,6)}`;
  }
}

/* ── Expose globally ─────────────────────────────────────────── */
if (typeof window !== 'undefined') {
  window.LegalQueryManager = LegalQueryManager;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = LegalQueryManager;
}
