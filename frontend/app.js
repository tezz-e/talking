/* ============================================================
   TALKING — AI Texting Autopilot Dashboard
   Frontend Application Logic
   ============================================================ */

'use strict';

// ─────────────────────────────────────────────────────────────
// State
// ─────────────────────────────────────────────────────────────

const state = {
  currentContact: null,
  contacts: [],
  messages: [],
  currentDraft: null,
  currentDraftRaw: null,      // original draft before edits
  currentConfidence: null,
  currentVariants: [],
  currentMood: 'default',
  facts: [],
  proMode: false,
  isGenerating: false,
  isEditing: false,
  ingestSource: 'instagram',
  lastIncomingMessage: null
};

// ─────────────────────────────────────────────────────────────
// API Layer
// ─────────────────────────────────────────────────────────────

const api = {
  /** Helper: make a fetch request and return parsed JSON. */
  async _fetch(url, options = {}) {
    const defaultHeaders = { 'Content-Type': 'application/json' };
    const res = await fetch(url, {
      ...options,
      headers: { ...defaultHeaders, ...options.headers }
    });
    if (!res.ok) {
      const body = await res.text().catch(() => '');
      throw new Error(`API ${res.status}: ${body || res.statusText}`);
    }
    // Some endpoints may return 204 No Content
    if (res.status === 204) return null;
    return res.json();
  },

  // ── Contacts ──
  getContacts() {
    return this._fetch('/api/contacts');
  },

  createContact(data) {
    return this._fetch('/api/contacts', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  },

  updateContact(id, data) {
    return this._fetch(`/api/contacts/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    });
  },

  deleteContact(id) {
    return this._fetch(`/api/contacts/${id}`, {
      method: 'DELETE'
    });
  },

  // ── Facts ──
  getFacts(contactId) {
    return this._fetch(`/api/contacts/${contactId}/facts`);
  },

  addFact(contactId, data) {
    return this._fetch(`/api/contacts/${contactId}/facts`, {
      method: 'POST',
      body: JSON.stringify(data)
    });
  },

  deleteFact(factId) {
    return this._fetch(`/api/facts/${factId}`, {
      method: 'DELETE'
    });
  },

  // ── History ──
  getHistory(contactId, limit = 50) {
    return this._fetch(`/api/history/${contactId}?limit=${limit}`);
  },

  // ── Messaging ──
  sendMessage(contactId, message, mood, proMode = false, steeringDirective = null) {
    return this._fetch('/api/message', {
      method: 'POST',
      body: JSON.stringify({
        contact_id: contactId,
        incoming_message: message,
        mood: mood,
        pro_mode: proMode,
        steering_directive: steeringDirective || undefined
      })
    });
  },

  regenerate(contactId, message, mood, proMode = false, steeringDirective = null) {
    return this._fetch('/api/regenerate', {
      method: 'POST',
      body: JSON.stringify({
        contact_id: contactId,
        incoming_message: message,
        mood: mood,
        pro_mode: proMode,
        steering_directive: steeringDirective || undefined
      })
    });
  },

  steerContact(contactId, instruction) {
    return this._fetch(`/api/contacts/${contactId}/steer`, {
      method: 'POST',
      body: JSON.stringify({ instruction })
    });
  },

  approve(contactId, originalDraft, finalMessage) {
    return this._fetch('/api/approve', {
      method: 'POST',
      body: JSON.stringify({
        contact_id: contactId,
        original_draft: originalDraft,
        final_message: finalMessage
      })
    });
  },

  // ── Ingestion ──
  ingest(source, userName, path) {
    return this._fetch('/api/ingest', {
      method: 'POST',
      body: JSON.stringify({ source, contact_name: userName, path })
    });
  },

  // ── Soul / Style ──
  getSoul() {
    return this._fetch('/api/soul');
  },

  saveSoul(content) {
    return this._fetch('/api/soul', {
      method: 'PUT',
      body: JSON.stringify({ content })
    });
  },

  getStyle() {
    return this._fetch('/api/style');
  },

  // ── Stats ──
  getStats() {
    return this._fetch('/api/stats');
  }
};

// ─────────────────────────────────────────────────────────────
// DOM References
// ─────────────────────────────────────────────────────────────

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const dom = {
  // Header
  contactSelector:  $('#contactSelector'),
  statusDot:        $('#statusDot'),
  statusText:       $('#statusText'),
  memoryCount:      $('#memoryCount'),

  // Chat & Steering
  proModeBtn:          $('#proModeBtn'),
  steeringInput:       $('#steeringInput'),
  clearSteerBtn:       $('#clearSteerBtn'),
  messageHistory:   $('#messageHistory'),
  emptyState:       $('#emptyState'),
  messageInput:     $('#messageInput'),
  sendBtn:          $('#sendBtn'),
  uploadImgBtn:     $('#uploadImgBtn'),
  imageUpload:      $('#imageUpload'),

  // Draft
  draftPanel:       $('#draftPanel'),
  draftVariants:    $('#draftVariants'),
  draftContent:     $('#draftContent'),
  draftActions:     $('#draftActions'),
  confidenceBadge:  $('#confidenceBadge'),
  editDraftBtn:     $('#editDraftBtn'),
  regenBtn:         $('#regenBtn'),
  approveBtn:       $('#approveBtn'),
  draftShortcutHint:$('#draftShortcutHint'),

  // Contact Profile
  contactName:         $('#contactName'),
  contactStage:        $('#contactStage'),
  contactGoal:         $('#contactGoal'),
  contactImpression:   $('#contactImpression'),
  contactStrategyNote: $('#contactStrategyNote'),
  contactHow:          $('#contactHow'),
  contactInterests:    $('#contactInterests'),
  contactJokes:        $('#contactJokes'),
  contactNotes:        $('#contactNotes'),
  contactFactCount:    $('#contactFactCount'),
  contactFactList:     $('#contactFactList'),
  addFactToggleBtn:    $('#addFactToggleBtn'),
  newFactRow:          $('#newFactRow'),
  newFactCategory:     $('#newFactCategory'),
  newFactInput:        $('#newFactInput'),
  saveNewFactBtn:      $('#saveNewFactBtn'),
  saveContactBtn:      $('#saveContactBtn'),

  // Mood
  moodSelector:     $('#moodSelector'),

  // AI stats
  aiStatusText:     $('#aiStatusText'),
  aiMemoryCount:    $('#aiMemoryCount'),

  // Data management buttons
  ingestBtn:        $('#ingestBtn'),
  editSoulBtn:      $('#editSoulBtn'),
  viewStyleBtn:     $('#viewStyleBtn'),

  // Modals
  soulEditor:       $('#soulEditor'),
  saveSoulBtn:      $('#saveSoulBtn'),
  styleContent:     $('#styleContent'),
  ingestUserName:   $('#ingestUserName'),
  ingestPath:       $('#ingestPath'),
  startIngestBtn:   $('#startIngestBtn'),
  ingestProgressContainer: $('#ingestProgressContainer'),
  ingestProgressBar:       $('#ingestProgressBar'),
  ingestProgressText:      $('#ingestProgressText'),
  ingestProgressPercent:   $('#ingestProgressPercent'),

  // Toast
  toastContainer:   $('#toastContainer')
};

// ─────────────────────────────────────────────────────────────
// Utility Helpers
// ─────────────────────────────────────────────────────────────

/**
 * Format a timestamp string into a human-readable relative time.
 */
function relativeTime(dateStr) {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now - date;
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHr  = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);

  if (diffSec < 10) return 'just now';
  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffMin < 60) return `${diffMin} min ago`;
  if (diffHr < 24)  return `${diffHr}h ago`;
  if (diffDay === 1) return 'yesterday';
  if (diffDay < 7)  return `${diffDay}d ago`;

  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/**
 * Auto-resize a textarea based on content.
 */
function autoResize(textarea) {
  textarea.style.height = 'auto';
  textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
}

/**
 * Copy text to clipboard.
 */
async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Fallback
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    return ok;
  }
}

// ─────────────────────────────────────────────────────────────
// Toast Notifications
// ─────────────────────────────────────────────────────────────

const TOAST_ICONS = {
  success: '✅',
  error: '❌',
  info: 'ℹ️',
  warning: '⚠️'
};

function showToast(message, type = 'info', duration = 3500) {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span class="toast-icon">${TOAST_ICONS[type] || ''}</span><span>${message}</span>`;
  dom.toastContainer.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('removing');
    toast.addEventListener('animationend', () => toast.remove());
  }, duration);
}

// ─────────────────────────────────────────────────────────────
// Modal Management
// ─────────────────────────────────────────────────────────────

function showModal(id) {
  const overlay = document.getElementById(id);
  if (overlay) {
    overlay.classList.add('active');
    // Focus first input or textarea
    setTimeout(() => {
      const focusable = overlay.querySelector('textarea, input, select');
      if (focusable) focusable.focus();
    }, 300);
  }
}

function hideModal(id) {
  const overlay = document.getElementById(id);
  if (overlay) overlay.classList.remove('active');
}

// Close modal on overlay click
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-overlay') && e.target.classList.contains('active')) {
    e.target.classList.remove('active');
  }
});

// Close modal on Escape
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    $$('.modal-overlay.active').forEach((m) => m.classList.remove('active'));
  }
});

// Expose for inline onclick handlers in HTML
window.showModal = showModal;
window.hideModal = hideModal;

// ─────────────────────────────────────────────────────────────
// Loading / Status
// ─────────────────────────────────────────────────────────────

function setLoading(isLoading) {
  state.isGenerating = isLoading;

  // Status dot
  dom.statusDot.classList.toggle('generating', isLoading);
  dom.statusText.textContent = isLoading ? 'Generating...' : 'Ready';
  dom.aiStatusText.textContent = isLoading ? 'Generating...' : 'Ready';

  // Draft panel
  dom.draftPanel.classList.toggle('generating', isLoading);

  // Disable send while generating
  dom.sendBtn.disabled = isLoading;
  dom.regenBtn.disabled = isLoading;

  if (isLoading) {
    dom.draftContent.innerHTML = `
      <div class="loading-dots">
        <span></span><span></span><span></span>
      </div>`;
    dom.draftActions.classList.add('hidden');
    if (dom.draftVariants) dom.draftVariants.classList.add('hidden');
    dom.confidenceBadge.classList.add('hidden');
    dom.draftShortcutHint.classList.add('hidden');
  }
}

// ─────────────────────────────────────────────────────────────
// Render Functions
// ─────────────────────────────────────────────────────────────

/**
 * Render message history into the chat panel.
 */
function renderMessages(messages) {
  // Remove empty state
  const emptyEl = dom.emptyState;
  if (emptyEl) emptyEl.remove();

  // Clear existing messages (keep non-message children)
  const existing = dom.messageHistory.querySelectorAll('.message-row');
  existing.forEach((el) => el.remove());

  if (!messages || messages.length === 0) {
    // Re-add empty state
    dom.messageHistory.innerHTML = `
      <div class="message-history-empty" id="emptyState">
        <div class="empty-icon">💬</div>
        <p>No messages yet.<br />Paste their message below to get started.</p>
      </div>`;
    return;
  }

  const fragment = document.createDocumentFragment();

  messages.forEach((msg) => {
    const row = document.createElement('div');
    const isOutgoing = msg.role === 'assistant' || msg.role === 'you' || msg.role === 'outgoing';
    row.className = `message-row ${isOutgoing ? 'outgoing' : 'incoming'}`;

    const wasEdited = isOutgoing && msg.was_edited;
    const senderName = isOutgoing ? 'You' : (state.currentContact?.name || 'Them');

    row.innerHTML = `
      <div class="message-sender">${senderName}</div>
      <div class="message-bubble${wasEdited ? ' was-edited' : ''}">${escapeHtml(msg.content || msg.text || '')}</div>
      <div class="message-timestamp">${relativeTime(msg.timestamp)}</div>
    `;
    fragment.appendChild(row);
  });

  dom.messageHistory.appendChild(fragment);

  // Auto-scroll to bottom immediately
  requestAnimationFrame(() => {
    dom.messageHistory.scrollTop = dom.messageHistory.scrollHeight;
  });
}

/**
 * Add a single message to the chat (for live updates).
 */
function appendMessage(msg) {
  if (!state.messages) state.messages = [];
  state.messages.push(msg);

  // Remove empty state if present
  const emptyEl = dom.messageHistory.querySelector('.message-history-empty');
  if (emptyEl) emptyEl.remove();

  const row = document.createElement('div');
  const isOutgoing = msg.role === 'assistant' || msg.role === 'you' || msg.role === 'outgoing';
  row.className = `message-row animate-in ${isOutgoing ? 'outgoing' : 'incoming'}`;

  const wasEdited = isOutgoing && msg.was_edited;
  const senderName = isOutgoing ? 'You' : (state.currentContact?.name || 'Them');

  row.innerHTML = `
    <div class="message-sender">${senderName}</div>
    <div class="message-bubble${wasEdited ? ' was-edited' : ''}">${escapeHtml(msg.content || msg.text || '')}</div>
    <div class="message-timestamp">${relativeTime(msg.timestamp)}</div>
  `;
  dom.messageHistory.appendChild(row);

  requestAnimationFrame(() => {
    dom.messageHistory.scrollTop = dom.messageHistory.scrollHeight;
  });
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

/**
 * Render contacts into the selector dropdown.
 */
function renderContacts(contacts) {
  // Keep the first two static options
  dom.contactSelector.innerHTML = `
    <option value="">— Select Contact —</option>
    <option value="__new__">＋ New Contact</option>
  `;

  contacts.forEach((c) => {
    const opt = document.createElement('option');
    opt.value = c.id;
    opt.textContent = c.name || `Contact ${c.id}`;
    if (state.currentContact && state.currentContact.id === c.id) {
      opt.selected = true;
    }
    dom.contactSelector.appendChild(opt);
  });
}

/**
 * Render contact profile into the sidebar form.
 */
function renderContactProfile(contact) {
  if (!contact) {
    dom.contactName.value = '';
    dom.contactStage.value = 'stranger';
    if (dom.contactGoal) dom.contactGoal.value = 'just_vibing';
    if (dom.contactImpression) dom.contactImpression.value = '';
    if (dom.contactStrategyNote) dom.contactStrategyNote.value = '';
    dom.contactHow.value = '';
    dom.contactInterests.value = '';
    dom.contactJokes.value = '';
    dom.contactNotes.value = '';
    renderFacts([]);
    if (dom.newFactRow) dom.newFactRow.classList.add('hidden');
    return;
  }

  dom.contactName.value = contact.name || '';
  dom.contactStage.value = contact.relationship_stage || 'stranger';
  if (dom.contactGoal) dom.contactGoal.value = contact.convo_goal || 'just_vibing';
  if (dom.contactImpression) dom.contactImpression.value = contact.my_impression || '';
  if (dom.contactStrategyNote) dom.contactStrategyNote.value = contact.strategy_note || '';
  dom.contactHow.value = contact.how_you_know || '';
  dom.contactInterests.value = contact.their_interests ? contact.their_interests.join(', ') : '';
  dom.contactJokes.value = contact.inside_jokes ? contact.inside_jokes.join(', ') : '';
  dom.contactNotes.value = contact.notes || '';

  // Load and render facts for this contact
  loadAndRenderFacts(contact.id);
}

/**
 * Render list of facts into the facts inspector.
 */
function renderFacts(facts) {
  state.facts = facts || [];
  if (dom.contactFactCount) {
    dom.contactFactCount.textContent = state.facts.length;
  }
  if (!dom.contactFactList) return;

  if (state.facts.length === 0) {
    dom.contactFactList.innerHTML = '<div class="fact-empty-hint">No facts recorded yet.</div>';
    return;
  }

  dom.contactFactList.innerHTML = '';
  state.facts.forEach((f) => {
    const item = document.createElement('div');
    item.className = 'fact-item';
    const cat = f.category || 'preference';
    item.innerHTML = `
      <span class="fact-cat-badge fact-cat-${escapeHtml(cat)}">${escapeHtml(cat)}</span>
      <span class="fact-text">${escapeHtml(f.fact)}</span>
      <button class="fact-delete-btn" title="Delete fact" data-id="${f.id}">✕</button>
    `;
    const delBtn = item.querySelector('.fact-delete-btn');
    delBtn.addEventListener('click', () => handleDeleteFact(f.id));
    dom.contactFactList.appendChild(item);
  });
}

/**
 * Load facts from API for active contact.
 */
async function loadAndRenderFacts(contactId) {
  if (!contactId) {
    renderFacts([]);
    return;
  }
  try {
    const facts = await api.getFacts(contactId);
    renderFacts(Array.isArray(facts) ? facts : []);
  } catch (err) {
    console.error('Failed to load facts:', err);
    renderFacts([]);
  }
}

/**
 * Handle adding a new fact.
 */
async function handleAddFact() {
  if (!state.currentContact || !state.currentContact.id) {
    showToast('Select a contact first.', 'warning');
    return;
  }
  const factText = dom.newFactInput.value.trim();
  if (!factText) return;

  const category = dom.newFactCategory.value;
  try {
    const created = await api.addFact(state.currentContact.id, {
      category,
      fact: factText,
      confidence: 0.95
    });
    state.facts.unshift(created);
    renderFacts(state.facts);
    dom.newFactInput.value = '';
    showToast('Fact added!', 'success');
  } catch (err) {
    console.error('Add fact error:', err);
    showToast(`Failed to add fact: ${err.message}`, 'error');
  }
}

/**
 * Handle deleting a fact.
 */
async function handleDeleteFact(factId) {
  try {
    await api.deleteFact(factId);
    state.facts = state.facts.filter((f) => f.id !== factId);
    renderFacts(state.facts);
    showToast('Fact removed.', 'info');
  } catch (err) {
    console.error('Delete fact error:', err);
    showToast(`Failed to delete fact: ${err.message}`, 'error');
  }
}

function renderDraftContent(draftText, bubbles = []) {
  dom.draftContent.innerHTML = '';
  if (bubbles && bubbles.length > 1) {
    const container = document.createElement('div');
    container.className = 'dashboard-bubbles-stack';
    bubbles.forEach((bText, idx) => {
      const bEl = document.createElement('div');
      bEl.className = 'dashboard-bubble-item';
      bEl.innerHTML = `<span class="bubble-idx">${idx + 1}</span> <span class="bubble-text">${escapeHtml(bText)}</span>`;
      container.appendChild(bEl);
    });
    dom.draftContent.appendChild(container);
  } else {
    dom.draftContent.textContent = draftText;
  }
}

/**
 * Show the AI draft in the draft panel.
 */
function showDraft(draft, confidence, variants = [], bubbles = []) {
  state.currentDraft = draft;
  state.currentDraftRaw = draft;
  state.currentConfidence = confidence;
  state.currentVariants = variants;
  state.isEditing = false;

  // Render variant chips if available
  if (dom.draftVariants) {
    if (variants && variants.length > 0) {
      dom.draftVariants.innerHTML = '';
      const icons = { chill: '🧊', direct: '🎯', banter: '🔥' };
      variants.forEach((v) => {
        const countBadge = v.bubbles && v.bubbles.length > 1
          ? `<span class="variant-count" style="font-size:10px; background:rgba(255,255,255,0.12); padding:1px 5px; border-radius:999px; margin-left:4px;">${v.bubbles.length}</span>`
          : '';
        const btn = document.createElement('button');
        btn.className = `variant-chip ${v.text === draft ? 'active' : ''}`;
        btn.dataset.variant = v.label;
        btn.innerHTML = `<span class="variant-icon">${icons[v.label] || '⚡'}</span> ${v.label.charAt(0).toUpperCase() + v.label.slice(1)}${countBadge}`;
        btn.addEventListener('click', () => {
          dom.draftVariants.querySelectorAll('.variant-chip').forEach((b) => b.classList.remove('active'));
          btn.classList.add('active');
          state.currentDraft = v.text;
          state.currentDraftRaw = v.text;
          renderDraftContent(v.text, v.bubbles);
        });
        dom.draftVariants.appendChild(btn);
      });
      dom.draftVariants.classList.remove('hidden');
    } else {
      dom.draftVariants.classList.add('hidden');
    }
  }

  // Content
  const activeVar = variants.find((v) => v.text === draft) || variants[0];
  renderDraftContent(draft, bubbles.length ? bubbles : (activeVar?.bubbles || []));
  dom.draftContent.classList.remove('editable');

  // Confidence badge
  let badgeClass = 'high';
  let badgeText = `${Math.round(confidence * 100)}%`;
  if (confidence < 0.5) badgeClass = 'low';
  else if (confidence < 0.8) badgeClass = 'medium';

  dom.confidenceBadge.className = `confidence-badge ${badgeClass}`;
  dom.confidenceBadge.textContent = badgeText;
  dom.confidenceBadge.classList.remove('hidden');

  // Show actions
  dom.draftActions.classList.remove('hidden');
  dom.draftShortcutHint.classList.remove('hidden');
}

// ─────────────────────────────────────────────────────────────
// Event Handlers
// ─────────────────────────────────────────────────────────────

/**
 * Handle sending an incoming message.
 */
async function handleSend() {
  const text = dom.messageInput.value.trim();
  if (!text || state.isGenerating) return;

  if (!state.currentContact) {
    showToast('Please select or create a contact first.', 'warning');
    return;
  }

  // Guard immediately against duplicate submits
  state.isGenerating = true;
  dom.sendBtn.disabled = true;

  state.lastIncomingMessage = text;

  // Add incoming message to chat
  appendMessage({
    role: 'incoming',
    content: text,
    timestamp: new Date().toISOString()
  });

  // Clear input
  dom.messageInput.value = '';
  autoResize(dom.messageInput);

  // Start generation UI
  setLoading(true);

  const steering = dom.steeringInput ? dom.steeringInput.value.trim() : '';

  try {
    const result = await api.sendMessage(
      state.currentContact.id,
      text,
      state.currentMood,
      state.proMode,
      steering
    );

    setLoading(false);

    if (result && result.draft) {
      showDraft(result.draft, result.confidence ?? 0.85, result.variants || [], result.bubbles || []);

      // If a steering directive was passed, refresh contact profile to reflect updates
      if (steering) {
        try {
          const contacts = await api.getContacts();
          state.contacts = Array.isArray(contacts) ? contacts : (contacts?.contacts || []);
          const updated = state.contacts.find((c) => String(c.id) === String(state.currentContact.id));
          if (updated) {
            state.currentContact = updated;
            renderContactProfile(updated);
          }
        } catch {
          // ignore background profile sync error
        }
      }

      // Update contextual memory count if returned
      if (result.retrieved_memories !== undefined) {
        const count = Array.isArray(result.retrieved_memories)
          ? result.retrieved_memories.length
          : result.retrieved_memories;
        dom.aiMemoryCount.textContent = count;
      }
    } else {
      showToast('No draft generated. Try again.', 'warning');
    }
  } catch (err) {
    setLoading(false);
    console.error('Send error:', err);
    showToast(`Error: ${err.message}`, 'error');
    dom.statusDot.classList.add('error');
    setTimeout(() => dom.statusDot.classList.remove('error'), 3000);
  }
}

/**
 * Handle regenerating a draft.
 */
async function handleRegenerate() {
  if (!state.currentContact || !state.lastIncomingMessage || state.isGenerating) return;

  setLoading(true);

  const steering = dom.steeringInput ? dom.steeringInput.value.trim() : '';

  try {
    const result = await api.regenerate(
      state.currentContact.id,
      state.lastIncomingMessage,
      state.currentMood,
      state.proMode,
      steering
    );

    setLoading(false);

    if (result && result.draft) {
      showDraft(result.draft, result.confidence ?? 0.85, result.variants || [], result.bubbles || []);
      showToast(state.proMode ? '⚡ Pro draft regenerated' : 'Draft regenerated', 'info');
    }
  } catch (err) {
    setLoading(false);
    console.error('Regenerate error:', err);
    showToast(`Error: ${err.message}`, 'error');
  }
}

/**
 * Handle editing the draft inline.
 */
function handleEditDraft() {
  if (!state.currentDraft) return;

  state.isEditing = !state.isEditing;

  if (state.isEditing) {
    const currentText = state.currentDraft;
    dom.draftContent.innerHTML = '';
    dom.draftContent.classList.add('editable');
    const textarea = document.createElement('textarea');
    textarea.value = currentText;
    textarea.addEventListener('input', () => {
      state.currentDraft = textarea.value;
      autoResize(textarea);
    });
    dom.draftContent.appendChild(textarea);
    textarea.focus();
    autoResize(textarea);
    dom.editDraftBtn.innerHTML = '✅';
    dom.editDraftBtn.title = 'Done editing';
  } else {
    const editedText = state.currentDraft;
    dom.draftContent.innerHTML = '';
    dom.draftContent.textContent = editedText;
    dom.draftContent.classList.remove('editable');
    dom.editDraftBtn.innerHTML = '✏️';
    dom.editDraftBtn.title = 'Edit draft';
  }
}

/**
 * Handle approving the draft — copy to clipboard + save.
 */
async function handleApprove() {
  if (!state.currentDraft || !state.currentContact) return;

  const finalMessage = state.currentDraft;
  const draftRaw = state.currentDraftRaw;
  const wasEdited = finalMessage !== draftRaw;

  // Immediately clear state and disable button to prevent double approvals
  state.currentDraft = null;
  state.currentDraftRaw = null;
  state.currentConfidence = null;
  dom.approveBtn.disabled = true;

  // Add outgoing message to chat
  appendMessage({
    role: 'outgoing',
    content: finalMessage,
    timestamp: new Date().toISOString(),
    was_edited: wasEdited
  });

  // Success flash on draft panel
  dom.draftPanel.classList.add('success-flash');
  setTimeout(() => dom.draftPanel.classList.remove('success-flash'), 700);

  // Reset draft panel
  dom.draftContent.innerHTML = '<span class="draft-placeholder">AI-generated response will appear here...</span>';
  dom.draftContent.classList.remove('editable');
  dom.draftActions.classList.add('hidden');
  if (dom.draftVariants) dom.draftVariants.classList.add('hidden');
  dom.confidenceBadge.classList.add('hidden');
  dom.draftShortcutHint.classList.add('hidden');
  dom.editDraftBtn.innerHTML = '✏️';
  state.isEditing = false;
  dom.approveBtn.disabled = false;

  // Copy to clipboard
  const copied = await copyToClipboard(finalMessage);
  if (copied) {
    showToast('Copied! ✅', 'success');
  } else {
    showToast('Approved but clipboard copy failed.', 'warning');
  }

  // Save to backend
  try {
    await api.approve(state.currentContact.id, draftRaw, finalMessage);
    updateStats();
  } catch (err) {
    console.error('Approve save error:', err);
    // Non-blocking — message already copied
  }
}

/**
 * Handle saving the contact profile.
 */
async function handleSaveContact() {
  const interestsVal = dom.contactInterests.value.trim();
  const jokesVal = dom.contactJokes.value.trim();

  const contactData = {
    name: dom.contactName.value.trim(),
    relationship_stage: dom.contactStage.value,
    convo_goal: dom.contactGoal ? dom.contactGoal.value : 'just_vibing',
    my_impression: dom.contactImpression ? dom.contactImpression.value.trim() : '',
    strategy_note: dom.contactStrategyNote ? dom.contactStrategyNote.value.trim() : '',
    how_you_know: dom.contactHow.value.trim(),
    their_interests: interestsVal ? interestsVal.split(',').map(s => s.trim()) : [],
    inside_jokes: jokesVal ? jokesVal.split(',').map(s => s.trim()) : [],
    notes: dom.contactNotes.value.trim()
  };

  if (!contactData.name) {
    showToast('Please enter a contact name.', 'warning');
    dom.contactName.focus();
    return;
  }

  try {
    if (state.currentContact && state.currentContact.id) {
      // Update existing
      const updated = await api.updateContact(state.currentContact.id, contactData);
      state.currentContact = { ...state.currentContact, ...contactData, ...updated };
      showToast('Contact updated!', 'success');
    } else {
      // Create new
      const created = await api.createContact(contactData);
      state.currentContact = created;
      state.contacts.push(created);
      renderContacts(state.contacts);
      // Select the new contact
      dom.contactSelector.value = created.id;
      showToast('Contact created!', 'success');
    }
  } catch (err) {
    console.error('Save contact error:', err);
    showToast(`Error saving contact: ${err.message}`, 'error');
  }
}

/**
 * Handle switching contacts.
 */
async function handleContactChange() {
  const val = dom.contactSelector.value;

  if (val === '__new__') {
    // Clear form for new contact
    state.currentContact = null;
    renderContactProfile(null);
    state.messages = [];
    renderMessages([]);
    dom.contactName.focus();
    return;
  }

  if (!val) {
    state.currentContact = null;
    renderContactProfile(null);
    state.messages = [];
    renderMessages([]);
    return;
  }

  // Load contact
  const contact = state.contacts.find((c) => String(c.id) === String(val));
  if (contact) {
    state.currentContact = contact;
    renderContactProfile(contact);

    // Load history
    try {
      const history = await api.getHistory(contact.id);
      state.messages = Array.isArray(history) ? history : (history?.messages || []);
      renderMessages(state.messages);
    } catch (err) {
      console.error('Load history error:', err);
      state.messages = [];
      renderMessages([]);
    }
  }
}

/**
 * Handle mood chip selection.
 */
function handleMoodSelect(e) {
  const chip = e.target.closest('.mood-chip');
  if (!chip) return;

  $$('.mood-chip').forEach((c) => c.classList.remove('active'));
  chip.classList.add('active');
  state.currentMood = chip.dataset.mood;
}

/**
 * Handle SOUL.md editing.
 */
async function handleOpenSoul() {
  showModal('soulModal');
  dom.soulEditor.value = 'Loading...';
  try {
    const data = await api.getSoul();
    dom.soulEditor.value = data?.content || data || '';
  } catch (err) {
    dom.soulEditor.value = `Error loading SOUL.md: ${err.message}`;
    showToast('Failed to load SOUL.md', 'error');
  }
}

async function handleSaveSoul() {
  try {
    await api.saveSoul(dom.soulEditor.value);
    hideModal('soulModal');
    showToast('SOUL.md saved!', 'success');
  } catch (err) {
    showToast(`Error saving: ${err.message}`, 'error');
  }
}

/**
 * Handle STYLE.md viewing.
 */
async function handleOpenStyle() {
  showModal('styleModal');
  dom.styleContent.textContent = 'Loading...';
  try {
    const data = await api.getStyle();
    dom.styleContent.textContent = data?.content || data || 'No STYLE.md found.';
  } catch (err) {
    dom.styleContent.textContent = `Error loading STYLE.md: ${err.message}`;
    showToast('Failed to load STYLE.md', 'error');
  }
}

/**
 * Handle chat data ingestion.
 */
function handleOpenIngest() {
  showModal('ingestModal');
}

async function handleStartIngest() {
  const userName = dom.ingestUserName.value.trim();
  const path = dom.ingestPath.value.trim() || '';

  if (!userName) {
    showToast('Please enter your display name.', 'warning');
    dom.ingestUserName.focus();
    return;
  }

  dom.startIngestBtn.disabled = true;
  dom.startIngestBtn.textContent = '⏳ Ingesting...';
  
  // Show progress container
  dom.ingestProgressContainer.classList.remove('hidden');
  dom.ingestProgressBar.style.width = '0%';
  dom.ingestProgressText.textContent = 'Starting ingestion...';
  dom.ingestProgressPercent.textContent = '0%';

  try {
    // Start background ingestion
    const result = await api.ingest(state.ingestSource, userName, path);
    
    // Start polling
    let isComplete = false;
    while (!isComplete) {
      await new Promise(r => setTimeout(r, 1500)); // wait 1.5s
      const statusRes = await fetch('/api/ingest/status');
      const statusData = await statusRes.json();
      
      dom.ingestProgressBar.style.width = `${statusData.progress}%`;
      dom.ingestProgressText.textContent = statusData.message;
      dom.ingestProgressPercent.textContent = `${statusData.progress}%`;
      
      if (statusData.status === 'completed') {
        isComplete = true;
        showToast('Ingestion complete!', 'success', 5000);
        updateStats();
        try {
          const contacts = await api.getContacts();
          state.contacts = Array.isArray(contacts) ? contacts : (contacts?.contacts || []);
          renderContacts(state.contacts);
        } catch {
          // ignore contact refresh error
        }
      } else if (statusData.status === 'error') {
        isComplete = true;
        throw new Error(statusData.message);
      }
    }
    
    setTimeout(() => {
      hideModal('ingestModal');
      dom.ingestProgressContainer.classList.add('hidden');
    }, 1000);

  } catch (err) {
    console.error('Ingest error:', err);
    showToast(`Ingestion failed: ${err.message}`, 'error');
  } finally {
    dom.startIngestBtn.disabled = false;
    dom.startIngestBtn.textContent = '🚀 Start Ingestion';
  }
}

/**
 * Handle Image Upload & OCR
 */
async function processImageForOCR(file) {
  if (!file || !file.type.startsWith('image/')) return;
  
  const formData = new FormData();
  formData.append('file', file);
  
  // Show loading in input
  const originalPlaceholder = dom.messageInput.placeholder;
  dom.messageInput.placeholder = 'Extracting text from image...';
  dom.messageInput.disabled = true;
  dom.uploadImgBtn.disabled = true;
  
  try {
    const res = await fetch('/api/extract-text', {
      method: 'POST',
      body: formData
    });
    
    if (!res.ok) {
      throw new Error(`OCR failed: ${res.status}`);
    }
    
    const data = await res.json();
    if (data.extracted_text) {
      dom.messageInput.value = data.extracted_text;
      autoResize(dom.messageInput);
      showToast('Text extracted successfully!', 'success');
    } else {
      showToast('No text found in image.', 'info');
    }
  } catch (err) {
    console.error('OCR Error:', err);
    showToast('Failed to extract text from image.', 'error');
  } finally {
    dom.messageInput.placeholder = originalPlaceholder;
    dom.messageInput.disabled = false;
    dom.uploadImgBtn.disabled = false;
    dom.messageInput.focus();
    dom.imageUpload.value = ''; // reset
  }
}

// ─────────────────────────────────────────────────────────────
// Event Binding
// ─────────────────────────────────────────────────────────────

function bindEvents() {
  // Pro Mode toggle
  if (dom.proModeBtn) {
    dom.proModeBtn.addEventListener('click', () => {
      state.proMode = !state.proMode;
      dom.proModeBtn.classList.toggle('active', state.proMode);
      showToast(
        state.proMode
          ? '⚡ Pro Mode enabled: deep reasoning & strategic steering active'
          : 'Pro Mode disabled: standard casual texting',
        'info'
      );
    });
  }

  // Steering directive clear button
  if (dom.steeringInput && dom.clearSteerBtn) {
    dom.steeringInput.addEventListener('input', () => {
      dom.clearSteerBtn.classList.toggle('hidden', !dom.steeringInput.value.trim());
    });
    dom.clearSteerBtn.addEventListener('click', () => {
      dom.steeringInput.value = '';
      dom.clearSteerBtn.classList.add('hidden');
      dom.steeringInput.focus();
    });
  }

  // Send message
  dom.sendBtn.addEventListener('click', handleSend);

  // Auto-resize input
  dom.messageInput.addEventListener('input', () => autoResize(dom.messageInput));

  // Image Upload & Paste
  if (dom.uploadImgBtn) {
    dom.uploadImgBtn.addEventListener('click', () => dom.imageUpload.click());
  }
  if (dom.imageUpload) {
    dom.imageUpload.addEventListener('change', (e) => {
      if (e.target.files && e.target.files[0]) {
        processImageForOCR(e.target.files[0]);
      }
    });
  }
  dom.messageInput.addEventListener('paste', (e) => {
    const items = (e.clipboardData || e.originalEvent.clipboardData).items;
    for (let item of items) {
      if (item.type.indexOf('image/') === 0) {
        e.preventDefault();
        const file = item.getAsFile();
        processImageForOCR(file);
        break;
      }
    }
  });

  // Draft actions
  dom.editDraftBtn.addEventListener('click', handleEditDraft);
  dom.regenBtn.addEventListener('click', handleRegenerate);
  dom.approveBtn.addEventListener('click', handleApprove);

  // Contact
  dom.contactSelector.addEventListener('change', handleContactChange);
  dom.saveContactBtn.addEventListener('click', handleSaveContact);

  // Facts Inspector
  if (dom.addFactToggleBtn && dom.newFactRow) {
    dom.addFactToggleBtn.addEventListener('click', () => {
      dom.newFactRow.classList.toggle('hidden');
      if (!dom.newFactRow.classList.contains('hidden')) {
        dom.newFactInput.focus();
      }
    });
  }
  if (dom.saveNewFactBtn) {
    dom.saveNewFactBtn.addEventListener('click', handleAddFact);
  }
  if (dom.newFactInput) {
    dom.newFactInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleAddFact();
      }
    });
  }

  // Mood
  dom.moodSelector.addEventListener('click', handleMoodSelect);

  // Data management
  dom.ingestBtn.addEventListener('click', handleOpenIngest);
  dom.editSoulBtn.addEventListener('click', handleOpenSoul);
  dom.viewStyleBtn.addEventListener('click', handleOpenStyle);

  // Soul save
  dom.saveSoulBtn.addEventListener('click', handleSaveSoul);

  // Ingest source selection
  $$('.ingest-option').forEach((opt) => {
    opt.addEventListener('click', () => {
      $$('.ingest-option').forEach((o) => o.classList.remove('selected'));
      opt.classList.add('selected');
      state.ingestSource = opt.dataset.source;
    });
  });

  // Start ingest
  dom.startIngestBtn.addEventListener('click', handleStartIngest);

  // ── Keyboard Shortcuts ──

  document.addEventListener('keydown', (e) => {
    // Ctrl+Enter → Send
    if (e.ctrlKey && e.key === 'Enter') {
      e.preventDefault();
      // Only if focus is in message input or anywhere
      handleSend();
    }

    // Ctrl+Shift+C → Copy draft
    if (e.ctrlKey && e.shiftKey && (e.key === 'c' || e.key === 'C')) {
      e.preventDefault();
      if (state.currentDraft) {
        handleApprove();
      }
    }
  });
}

// ─────────────────────────────────────────────────────────────
// Initialization
// ─────────────────────────────────────────────────────────────

/**
 * Refresh global memory and system statistics.
 */
async function updateStats() {
  try {
    const stats = await api.getStats();
    if (stats && typeof stats.total_memories === 'number') {
      dom.memoryCount.textContent = stats.total_memories;
    }
  } catch (err) {
    console.warn('Could not fetch stats:', err.message);
  }
}

async function init() {
  bindEvents();
  updateStats();

  // Load contacts
  try {
    const contacts = await api.getContacts();
    state.contacts = Array.isArray(contacts) ? contacts : (contacts?.contacts || []);
    renderContacts(state.contacts);

    // Auto-select first contact if available
    if (state.contacts.length > 0) {
      state.currentContact = state.contacts[0];
      dom.contactSelector.value = state.contacts[0].id;
      renderContactProfile(state.contacts[0]);

      // Load history
      try {
        const history = await api.getHistory(state.contacts[0].id);
        state.messages = Array.isArray(history) ? history : (history?.messages || []);
        renderMessages(state.messages);
      } catch {
        // History might not exist yet
      }
    }
  } catch (err) {
    // API might not be ready yet — that's fine on first load
    console.warn('Could not load contacts:', err.message);
  }
}

// Boot
document.addEventListener('DOMContentLoaded', init);
