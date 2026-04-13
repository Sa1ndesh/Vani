/**
 * legal-query.js
 * Manages the legal query lifecycle, response rendering, and session handling.
 */

const API_BASE = window.VANI_API_BASE || 'http://localhost:8000';

export class LegalQueryHandler {
  constructor() {
    this._selectedLanguage = 'English';
    this._selectedState = '';
    this._sessionId = this._generateSessionId();
    this._voiceHandler = null;

    // DOM refs
    this._chatMessages = null;
    this._textInput = null;
    this._sendBtn = null;
    this._loadingOverlay = null;
    this._dialectDisplay = null;
    this._dialectValue = null;
    this._aiStatus = null;
    this._docCount = null;
    this._stateSelect = null;
    this._newChatBtn = null;
    this._citationModal = null;
    this._modalTitle = null;
    this._modalBody = null;
    this._modalClose = null;
  }

  /** Wire up all DOM event listeners. */
  init() {
    this._chatMessages   = document.getElementById('chatMessages');
    this._textInput      = document.getElementById('textInput');
    this._sendBtn        = document.getElementById('sendBtn');
    this._loadingOverlay = document.getElementById('loadingOverlay');
    this._dialectDisplay = document.getElementById('dialectDisplay');
    this._dialectValue   = document.getElementById('dialectValue');
    this._aiStatus       = document.getElementById('aiStatus');
    this._docCount       = document.getElementById('docCount');
    this._stateSelect    = document.getElementById('stateSelect');
    this._newChatBtn     = document.getElementById('newChatBtn');
    this._citationModal  = document.getElementById('citationModal');
    this._modalTitle     = document.getElementById('modalTitle');
    this._modalBody      = document.getElementById('modalBody');
    this._modalClose     = document.getElementById('modalClose');

    // Language pills
    document.getElementById('languagePills')?.addEventListener('click', (e) => {
      const btn = e.target.closest('.lang-pill');
      if (!btn) return;
      document.querySelectorAll('.lang-pill').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      this._selectedLanguage = btn.dataset.lang;
    });

    // State select
    this._stateSelect?.addEventListener('change', () => {
      this._selectedState = this._stateSelect.value;
    });

    // Send button
    this._sendBtn?.addEventListener('click', () => this._handleTextSubmit());

    // Enter key (Shift+Enter for newline)
    this._textInput?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this._handleTextSubmit();
      }
    });

    // Auto-grow textarea
    this._textInput?.addEventListener('input', () => {
      this._textInput.style.height = 'auto';
      this._textInput.style.height = Math.min(this._textInput.scrollHeight, 160) + 'px';
    });

    // New chat
    this._newChatBtn?.addEventListener('click', () => this.startNewChat());

    // Quick queries
    document.getElementById('quickQueries')?.addEventListener('click', (e) => {
      const btn = e.target.closest('.quick-btn');
      if (!btn) return;
      const q = btn.dataset.query;
      if (q && this._textInput) {
        this._textInput.value = q;
        this._handleTextSubmit();
      }
    });

    // Citation modal close
    this._modalClose?.addEventListener('click', () => this._closeCitationModal());
    this._citationModal?.addEventListener('click', (e) => {
      if (e.target === this._citationModal) this._closeCitationModal();
    });

    // Load initial info
    this._loadDocCount();
    this.loadQuickQueries();
  }

  // ---------------------------------------------------------------------------
  // Session management
  // ---------------------------------------------------------------------------

  startNewChat(sessionId) {
    this._sessionId = sessionId || this._generateSessionId();
    if (this._chatMessages) {
      // Remove all bubbles except the welcome message
      const bubbles = this._chatMessages.querySelectorAll('.chat-bubble');
      bubbles.forEach((b, i) => { if (i > 0) b.remove(); });
    }
    this._showToast('New conversation started.');
  }

  _generateSessionId() {
    return 'sess_' + Math.random().toString(36).slice(2, 11) + Date.now();
  }

  getSelectedLanguage() { return this._selectedLanguage; }

  // ---------------------------------------------------------------------------
  // Submit
  // ---------------------------------------------------------------------------

  _handleTextSubmit() {
    const text = this._textInput?.value.trim();
    if (!text) return;
    if (this._textInput) this._textInput.value = '';
    this.submitQuery(text, null, this._selectedLanguage, this._selectedState);
  }

  async submitQuery(queryText, audioBlob, language, state) {
    if (!queryText?.trim()) return;

    // Render user bubble
    this._appendUserBubble(queryText);
    this._showLoading(true);

    // Prepare payload
    let audioBase64 = null;
    if (audioBlob) {
      audioBase64 = await this._blobToBase64(audioBlob).catch(() => null);
    }

    const payload = {
      query: queryText,
      language: language || this._selectedLanguage,
      state: state || this._selectedState,
      session_id: this._sessionId,
    };
    if (audioBase64) payload.audio = audioBase64;

    try {
      const resp = await fetch(`${API_BASE}/legal/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!resp.ok) throw new Error(`Server error ${resp.status}: ${await resp.text()}`);

      const data = await resp.json();
      this._showLoading(false);
      this.displayResponse(data);

      // Update dialect display
      if (data.dialect_detected || data.language_detected) {
        this.handleLanguageDetection(data.language_detected, data.dialect_detected);
      }

      // Auto-play audio if present
      if (data.audio_response && this._voiceHandler) {
        this._voiceHandler.playAudio(data.audio_response);
      }
    } catch (err) {
      this._showLoading(false);
      this._appendAssistantBubble(
        `❌ Could not reach the server. Please ensure the backend is running at <code>${API_BASE}</code>.`,
        [], '', ''
      );
      console.error('Query failed:', err);
    }
  }

  // ---------------------------------------------------------------------------
  // Response display
  // ---------------------------------------------------------------------------

  displayResponse(data) {
    const responseText   = data.response || data.response_text || '';
    const citations      = data.citations || [];
    const simplified     = data.simplified_explanation || '';
    const queryType      = data.query_type || '';
    const audioBase64    = data.audio_response || '';

    this._appendAssistantBubble(responseText, citations, simplified, queryType, audioBase64);
  }

  _appendAssistantBubble(text, citations = [], simplified = '', queryType = '', audioBase64 = '') {
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble assistant-bubble';
    bubble.innerHTML = `
      <div class="bubble-avatar">⚖️</div>
      <div class="bubble-content">
        ${queryType ? `<span class="query-type-badge">${this._queryTypeLabel(queryType)}</span>` : ''}
        <div class="bubble-text">${this._markdownToHtml(text)}</div>
        ${citations.length ? `<div class="citations-area">${this.formatCitations(citations)}</div>` : ''}
        ${simplified ? `
          <details class="simplified-details">
            <summary>💡 Simplified Explanation</summary>
            <p class="simplified-text">${this._escapeHtml(simplified)}</p>
          </details>` : ''}
        ${audioBase64 ? `
          <button class="play-audio-btn" data-audio="${audioBase64}" title="Play audio response">
            🔊 Play Response
          </button>` : ''}
      </div>`;

    // Play audio button handler
    bubble.querySelector('.play-audio-btn')?.addEventListener('click', (e) => {
      const b64 = e.currentTarget.dataset.audio;
      if (b64 && this._voiceHandler) this._voiceHandler.playAudio(b64);
    });

    this._chatMessages?.appendChild(bubble);
    this._scrollToBottom();
  }

  _appendUserBubble(text) {
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble user-bubble';
    bubble.innerHTML = `
      <div class="bubble-content">
        <div class="bubble-text">${this._escapeHtml(text)}</div>
      </div>
      <div class="bubble-avatar user-avatar">👤</div>`;
    this._chatMessages?.appendChild(bubble);
    this._scrollToBottom();
  }

  // ---------------------------------------------------------------------------
  // Citations
  // ---------------------------------------------------------------------------

  formatCitations(citations) {
    if (!citations || citations.length === 0) return '';
    const items = citations.map((c) => {
      const ref = this._escapeHtml(c.reference || '');
      const ctx = this._escapeHtml(c.context || '');
      return `
        <button class="citation-tag" data-ref="${ref}" data-ctx="${ctx}">
          📖 ${ref}
        </button>`;
    }).join('');
    const wrapper = document.createElement('div');
    wrapper.className = 'citations-list';
    wrapper.innerHTML = `<span class="citations-label">Citations:</span> ${items}`;

    // We return a string; attach listeners after insertion
    setTimeout(() => {
      document.querySelectorAll('.citation-tag').forEach((btn) => {
        if (!btn.dataset.listenerAdded) {
          btn.dataset.listenerAdded = 'true';
          btn.addEventListener('click', () => this._openCitationModal(btn.dataset.ref, btn.dataset.ctx));
        }
      });
    }, 50);

    return wrapper.outerHTML;
  }

  _openCitationModal(reference, context) {
    if (!this._citationModal) return;
    if (this._modalTitle) this._modalTitle.textContent = reference;
    if (this._modalBody) {
      this._modalBody.innerHTML = context
        ? `<p>${this._escapeHtml(context)}</p>`
        : `<p>Refer to the relevant provisions of <strong>${this._escapeHtml(reference)}</strong> for details.</p>
           <p>For the full text of Indian laws, visit <a href="https://indiacode.nic.in" target="_blank" rel="noopener">India Code</a>.</p>`;
    }
    this._citationModal.style.display = 'flex';
    this._modalClose?.focus();
  }

  _closeCitationModal() {
    if (this._citationModal) this._citationModal.style.display = 'none';
  }

  // ---------------------------------------------------------------------------
  // Language / dialect display
  // ---------------------------------------------------------------------------

  handleLanguageDetection(language, dialect) {
    if (!language) return;
    if (dialect && this._dialectDisplay && this._dialectValue) {
      this._dialectDisplay.style.display = 'flex';
      this._dialectValue.textContent = `${dialect} (${language})`;
    }

    // Sync language pill
    document.querySelectorAll('.lang-pill').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.lang === language);
    });
    this._selectedLanguage = language;
  }

  // ---------------------------------------------------------------------------
  // Quick queries
  // ---------------------------------------------------------------------------

  loadQuickQueries() {
    // Buttons already in HTML; this could fetch from an API in future
  }

  // ---------------------------------------------------------------------------
  // Misc UI
  // ---------------------------------------------------------------------------

  toggleSimplifiedExplanation(detailsEl) {
    if (detailsEl) detailsEl.open = !detailsEl.open;
  }

  _showLoading(show) {
    if (this._loadingOverlay) this._loadingOverlay.style.display = show ? 'flex' : 'none';
  }

  _scrollToBottom() {
    if (this._chatMessages) {
      this._chatMessages.scrollTop = this._chatMessages.scrollHeight;
    }
  }

  _showToast(message) {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => { toast.classList.remove('show'); setTimeout(() => toast.remove(), 300); }, 2500);
  }

  async _loadDocCount() {
    try {
      const resp = await fetch(`${API_BASE}/health`);
      if (resp.ok) {
        const data = await resp.json();
        if (this._docCount) this._docCount.textContent = 'Online ✓';
        if (this._aiStatus) this._aiStatus.style.color = '#4ade80';
      }
    } catch {
      if (this._docCount) this._docCount.textContent = 'Offline – check backend';
    }
  }

  _queryTypeLabel(type) {
    const labels = {
      criminal: '⚖️ Criminal Law',
      civil: '📄 Civil Law',
      property: '🏠 Property Law',
      family: '👨‍👩‍👧 Family Law',
      general: '📋 General',
    };
    return labels[type] || type;
  }

  // ---------------------------------------------------------------------------
  // Text helpers
  // ---------------------------------------------------------------------------

  _markdownToHtml(text) {
    return text
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`(.+?)`/g, '<code>$1</code>')
      .replace(/\n\n/g, '</p><p>')
      .replace(/\n/g, '<br />')
      .replace(/^/, '<p>').replace(/$/, '</p>');
  }

  _escapeHtml(text) {
    return (text || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  _blobToBase64(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result.split(',')[1]);
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }

  setVoiceHandler(vh) { this._voiceHandler = vh; }
}
