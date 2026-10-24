/**
 * Talking Copilot — In-Page Content Script
 * =======================================
 * Integrates WhatsApp Web and Instagram Direct with the local Talking autopilot.
 */

(function () {
  'use strict';

  const BACKEND_BASE = 'http://localhost:8000';
  let activeContactId = null;
  let activeOriginalDraft = null;
  let activeVariants = [];
  let currentVariantLabel = 'direct';
  let isProMode = localStorage.getItem('talking_copilot_pro') === 'true';

  // ── Platform Detection ──────────────────────────────────────────────
  const isWhatsApp = () => window.location.hostname.includes('web.whatsapp.com');
  const isInstagram = () => window.location.hostname.includes('instagram.com');

  // ── DOM Extraction Helpers ──────────────────────────────────────────

  function getActiveContactName() {
    if (isWhatsApp()) {
      // WhatsApp header title
      const titleEl =
        document.querySelector('header span[dir="auto"]') ||
        document.querySelector('header [data-testid="conversation-info-header-chat-title"]') ||
        document.querySelector('header div[role="button"] span[title]');
      return titleEl ? (titleEl.getAttribute('title') || titleEl.textContent || '').trim() : 'Friend';
    }

    if (isInstagram()) {
      // Instagram Direct conversation header
      const headerEl =
        document.querySelector('main header h2') ||
        document.querySelector('main header span[dir="auto"]') ||
        document.querySelector('main header a span') ||
        document.querySelector('header span');
      return headerEl ? headerEl.textContent.trim() : 'Friend';
    }

    return 'Friend';
  }

  function getLastIncomingMessage() {
    if (isWhatsApp()) {
      const incomingNodes = document.querySelectorAll('div.message-in');
      if (incomingNodes.length === 0) return '';
      const last = incomingNodes[incomingNodes.length - 1];
      const textEl = last.querySelector('.selectable-text') || last.querySelector('.copyable-text');
      return textEl ? textEl.textContent.trim() : '';
    }

    if (isInstagram()) {
      // Look for message bubbles in main direct thread
      const bubbles = document.querySelectorAll('div[role="main"] div[dir="auto"]');
      if (bubbles.length === 0) return '';
      // Scan from bottom to top for incoming message
      for (let i = bubbles.length - 1; i >= 0; i--) {
        const text = bubbles[i].textContent.trim();
        if (text && text.length > 0 && !text.includes('Seen') && !text.includes('Delivered')) {
          return text;
        }
      }
    }

    return '';
  }

  function getChatInputElement() {
    if (isWhatsApp()) {
      return (
        document.querySelector('footer div[contenteditable="true"]') ||
        document.querySelector('footer [role="textbox"]')
      );
    }

    if (isInstagram()) {
      return (
        document.querySelector('div[role="main"] div[contenteditable="true"][role="textbox"]') ||
        document.querySelector('div[role="main"] textarea[placeholder*="Message"]') ||
        document.querySelector('div[contenteditable="true"]')
      );
    }

    return null;
  }

  function insertTextIntoChat(text) {
    const inputEl = getChatInputElement();
    if (!inputEl) {
      navigator.clipboard.writeText(text);
      alert('Copied draft to clipboard! (Please click in the chat input and paste)');
      return;
    }

    inputEl.focus();
    try {
      // Select existing content and replace using execCommand
      document.execCommand('selectAll', false, null);
      const inserted = document.execCommand('insertText', false, text);
      if (!inserted) {
        inputEl.textContent = text;
        inputEl.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
      }
    } catch {
      inputEl.textContent = text;
      inputEl.dispatchEvent(new Event('input', { bubbles: true }));
    }
  }

  // ── Floating UI Creation ────────────────────────────────────────────

  function ensureFloatingPill() {
    if (document.getElementById('talking-copilot-pill')) return;

    const pill = document.createElement('div');
    pill.id = 'talking-copilot-pill';
    pill.innerHTML = `
      <span class="tk-icon">⚡</span>
      <span>Draft</span>
      <span class="tk-kbd">Alt+D</span>
    `;

    pill.addEventListener('click', () => {
      triggerDraftGeneration();
    });

    document.body.appendChild(pill);
  }

  function closeCopilotModal() {
    const existing = document.getElementById('talking-copilot-modal');
    if (existing) existing.remove();
  }

  function openCopilotModal(contactName, incomingText, isLoading = true, draftData = null) {
    closeCopilotModal();

    const modal = document.createElement('div');
    modal.id = 'talking-copilot-modal';

    const safeContact = contactName || 'Friend';
    const safeSnippet = incomingText ? `"${incomingText.slice(0, 140)}${incomingText.length > 140 ? '...' : ''}"` : 'No incoming text detected';

    modal.innerHTML = `
      <div class="tk-header">
        <div class="tk-title-wrap">
          <span style="font-size:16px;">⚡</span>
          <span class="tk-brand">Talking Copilot</span>
          <span class="tk-contact-tag">${escapeHtml(safeContact)}</span>
        </div>
        <button class="tk-close-btn" id="tk-close-modal">✕</button>
      </div>

      <div class="tk-body">
        <div class="tk-incoming-snippet">
          <strong>They said:</strong> ${escapeHtml(safeSnippet)}
        </div>

        ${
          isLoading
            ? `
          <div class="tk-loading-indicator">
            <div class="tk-spinner"></div>
            <span>Crafting personalized draft...</span>
          </div>`
            : `
          <div class="tk-variants-bar" id="tk-variants-bar">
            <!-- Variant chips rendered dynamically -->
          </div>

          <textarea class="tk-draft-textarea" id="tk-draft-text" placeholder="Draft reply..."></textarea>
          `
        }
      </div>

      ${
        isLoading
          ? ''
          : `
      <div class="tk-footer">
        <div class="tk-left-actions">
          <label class="tk-pro-toggle">
            <input type="checkbox" id="tk-pro-toggle-cb" ${isProMode ? 'checked' : ''} />
            <span>⚡ Pro</span>
          </label>
          <button class="tk-btn tk-btn-secondary" id="tk-regen-btn" title="Regenerate">🔄</button>
        </div>
        <div class="tk-right-actions">
          <button class="tk-btn tk-btn-secondary" id="tk-copy-btn">Copy</button>
          <button class="tk-btn tk-btn-primary" id="tk-insert-btn">Insert ↵</button>
        </div>
      </div>
      `
      }
    `;

    document.body.appendChild(modal);

    modal.querySelector('#tk-close-modal')?.addEventListener('click', closeCopilotModal);

    if (!isLoading && draftData) {
      bindModalActions(modal, draftData);
    }
  }

  function bindModalActions(modal, data) {
    const draftTextarea = modal.querySelector('#tk-draft-text');
    const variantsBar = modal.querySelector('#tk-variants-bar');
    const proToggle = modal.querySelector('#tk-pro-toggle-cb');
    const regenBtn = modal.querySelector('#tk-regen-btn');
    const copyBtn = modal.querySelector('#tk-copy-btn');
    const insertBtn = modal.querySelector('#tk-insert-btn');

    activeContactId = data.contact_id;
    activeOriginalDraft = data.draft;
    activeVariants = data.variants || [];

    // Render variant buttons
    if (variantsBar && activeVariants.length > 0) {
      const icons = { chill: '🧊', direct: '🎯', banter: '🔥' };
      variantsBar.innerHTML = '';
      activeVariants.forEach((v) => {
        const btn = document.createElement('button');
        btn.className = `tk-variant-btn ${v.label === currentVariantLabel ? 'tk-active' : ''}`;
        btn.innerHTML = `<span>${icons[v.label] || '⚡'}</span> ${v.label.charAt(0).toUpperCase() + v.label.slice(1)}`;
        btn.addEventListener('click', () => {
          variantsBar.querySelectorAll('.tk-variant-btn').forEach((b) => b.classList.remove('tk-active'));
          btn.classList.add('tk-active');
          currentVariantLabel = v.label;
          draftTextarea.value = v.text;
        });
        variantsBar.appendChild(btn);
      });
    }

    draftTextarea.value = data.draft || '';

    // Pro mode toggle
    proToggle?.addEventListener('change', (e) => {
      isProMode = e.target.checked;
      localStorage.setItem('talking_copilot_pro', isProMode ? 'true' : 'false');
    });

    // Regenerate
    regenBtn?.addEventListener('click', () => {
      triggerDraftGeneration();
    });

    // Copy
    copyBtn?.addEventListener('click', () => {
      navigator.clipboard.writeText(draftTextarea.value);
      copyBtn.textContent = 'Copied!';
      setTimeout(() => (copyBtn.textContent = 'Copy'), 1500);
    });

    // Insert into chat
    const doInsert = () => {
      const finalMsg = draftTextarea.value.trim();
      if (!finalMsg) return;

      insertTextIntoChat(finalMsg);

      // Report approval to backend
      if (activeContactId) {
        fetch(`${BACKEND_BASE}/api/approve`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            contact_id: activeContactId,
            original_draft: activeOriginalDraft || finalMsg,
            final_message: finalMsg,
          }),
        }).catch((e) => console.warn('[Talking Copilot] Approve notify failed:', e));
      }

      closeCopilotModal();
    };

    insertBtn?.addEventListener('click', doInsert);

    // Enter key submits draft inside textarea
    draftTextarea?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        doInsert();
      }
    });

    draftTextarea?.focus();
  }

  // ── Draft Generation Controller ─────────────────────────────────────

  async function triggerDraftGeneration() {
    const contactName = getActiveContactName();
    const incomingText = getLastIncomingMessage();

    openCopilotModal(contactName, incomingText, true);

    try {
      const res = await fetch(`${BACKEND_BASE}/api/copilot/draft`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contact_name: contactName,
          incoming_message: incomingText || 'Hey!',
          mood: 'default',
          pro_mode: isProMode,
        }),
      });

      if (!res.ok) {
        const errText = await res.text();
        throw new Error(`API ${res.status}: ${errText}`);
      }

      const data = await res.json();
      openCopilotModal(contactName, incomingText, false, data);
    } catch (err) {
      console.error('[Talking Copilot] Error:', err);
      openCopilotModal(contactName, incomingText, false, {
        draft: `Could not connect to Talking at ${BACKEND_BASE}. Make sure the backend is running (python -m backend.main).`,
        variants: [],
      });
    }
  }

  // ── Utility ─────────────────────────────────────────────────────────

  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // ── Global Keyboard Shortcuts ───────────────────────────────────────

  window.addEventListener('keydown', (e) => {
    // Alt+D triggers draft
    if (e.altKey && (e.key === 'd' || e.key === 'D')) {
      e.preventDefault();
      triggerDraftGeneration();
      return;
    }

    // Escape closes modal
    if (e.key === 'Escape') {
      closeCopilotModal();
    }
  });

  // ── Initialization & Observer ───────────────────────────────────────

  function init() {
    ensureFloatingPill();

    // Re-check floating pill on SPA route change
    const observer = new MutationObserver(() => {
      ensureFloatingPill();
    });
    observer.observe(document.body, { childList: true, subtree: true });
    console.log('[Talking Copilot] Active on', window.location.hostname);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
