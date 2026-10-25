/* ============================================================
   TALKING — PROOF DESK DASHBOARD
   Frontend Application Logic & Editorial State Machine
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
  previousDraft: null,        // for MARKS revision tracking
  showMarks: false,
  currentConfidence: null,
  currentVariants: [],
  currentMood: 'default',
  facts: [],
  proMode: false,
  isGenerating: false,
  isEditing: false,
  ingestSource: 'instagram',
  lastIncomingMessage: null,
  theme: localStorage.getItem('talking_theme') || 'light'
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
  themeToggleBtn:   $('#themeToggleBtn'),
  themeToggleText:  $('#themeToggleText'),

  // Chat & Composer
  messageHistory:   $('#messageHistory'),
  emptyState:       $('#emptyState'),
  proModeBtn:       $('#proModeBtn'),
  noteToggleBtn:    $('#noteToggleBtn'),
  marginNoteRow:    $('#marginNoteRow'),
  steeringInput:    $('#steeringInput'),
  clearSteerBtn:    $('#clearSteerBtn'),
  messageInput:     $('#messageInput'),
  sendBtn:          $('#sendBtn'),
  uploadImgBtn:     $('#uploadImgBtn'),
  imageUpload:      $('#imageUpload'),

  // Draft Desk
  draftPanel:       $('#draftPanel'),
  draftEmptyRow:    $('#draftEmptyRow'),
  draftHeader:      $('#draftHeader'),
  draftProvenance:  $('#draftProvenance'),
  confidenceBadge:  $('#confidenceBadge'),
  marksToggleBtn:   $('#marksToggleBtn'),
  draftVariants:    $('#draftVariants'),
  draftContent:     $('#draftContent'),
  draftActions:     $('#draftActions'),
  editDraftBtn:     $('#editDraftBtn'),
  regenBtn:         $('#regenBtn'),
  approveBtn:       $('#approveBtn'),
  draftShortcutHint:$('#draftShortcutHint'),

  // Contact Profile
  contactProfilePanel: $('#contactProfilePanel'),
  contactName:         $('#contactName'),
  contactStage:        $('#contactStage'),
  stageSegmentedGroup: $('#stageSegmentedGroup'),
  contactGoal:         $('#contactGoal'),
  goalSegmentedGroup:  $('#goalSegmentedGroup'),
  contactImpression:   $('#contactImpression'),
  contactStrategyNote: $('#contactStrategyNote'),
  contactHow:          $('#contactHow'),
  contactInterests:    $('#contactInterests'),
  interestsTagsContainer: $('#interestsTagsContainer'),
  contactJokes:        $('#contactJokes'),
  jokesListContainer:  $('#jokesListContainer'),
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
  soulModal:        $('#soulModal'),
  soulEditor:       $('#soulEditor'),
  saveSoulBtn:      $('#saveSoulBtn'),
  styleModal:       $('#styleModal'),
  styleContent:     $('#styleContent'),
  ingestModal:      $('#ingestModal'),
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
// Theme Management (Light Paper / Dark Carbon)
// ─────────────────────────────────────────────────────────────

function applyTheme(theme) {
  state.theme = theme;
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('talking_theme', theme);
  if (dom.themeToggleText) {
    dom.themeToggleText.textContent = theme.toUpperCase();
  }
}

function toggleTheme() {
  const next = state.theme === 'dark' ? 'light' : 'dark';
  applyTheme(next);
}

// ─────────────────────────────────────────────────────────────
// Utility Helpers
// ─────────────────────────────────────────────────────────────

function relativeTime(dateStr) {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now - date;
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHr  = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);

  if (diffSec < 10) return 'JUST NOW';
  if (diffSec < 60) return `${diffSec}S AGO`;
  if (diffMin < 60) return `${diffMin}M AGO`;
  if (diffHr < 24)  return `${diffHr}H AGO`;
  if (diffDay === 1) return 'YESTERDAY';
  if (diffDay < 7)  return `${diffDay}D AGO`;

  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }).toUpperCase();
}

function autoResize(textarea) {
  if (!textarea) return;
  textarea.style.height = 'auto';
  textarea.style.height = Math.min(textarea.scrollHeight, 180) + 'px';
}

async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
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

function escapeHtml(str) {
  if (typeof str !== 'string') return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ─────────────────────────────────────────────────────────────
// Revision Marks (Client-Side Word Diff Engine)
// ─────────────────────────────────────────────────────────────

/**
 * Highlights word additions (accent underline) and removals (muted strikethrough).
 */
function renderTextWithMarks(newText, oldText) {
  if (!state.showMarks || !oldText || oldText === newText) {
    return escapeHtml(newText);
  }

  const oldWords = oldText.trim().split(/\s+/);
  const newWords = newText.trim().split(/\s+/);

  const oldFreq = new Map();
  oldWords.forEach(w => {
    const k = w.toLowerCase().replace(/[^\w]/g, '');
    oldFreq.set(k, (oldFreq.get(k) || 0) + 1);
  });

  const markedWords = newWords.map(w => {
    const k = w.toLowerCase().replace(/[^\w]/g, '');
    if (!k || !oldFreq.has(k) || oldFreq.get(k) <= 0) {
      return `<span class="mark-added">${escapeHtml(w)}</span>`;
    } else {
      oldFreq.set(k, oldFreq.get(k) - 1);
      return escapeHtml(w);
    }
  });

  // Calculate deleted words
  const newSet = new Set(newWords.map(w => w.toLowerCase().replace(/[^\w]/g, '')));
  const deletedWords = oldWords.filter(w => {
    const k = w.toLowerCase().replace(/[^\w]/g, '');
    return k && !newSet.has(k);
  });

  let deletedHtml = '';
  if (deletedWords.length > 0) {
    const preview = deletedWords.slice(0, 5).join(' ');
    deletedHtml = ` <span class="mark-deleted">[DEL: ${escapeHtml(preview)}]</span>`;
  }

  return markedWords.join(' ') + deletedHtml;
}

// ─────────────────────────────────────────────────────────────
// Toast Notifications
// ─────────────────────────────────────────────────────────────

function showToast(message, type = 'info', duration = 3000) {
  if (!dom.toastContainer) return;
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message.toUpperCase();
  dom.toastContainer.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 200ms ease';
    setTimeout(() => toast.remove(), 200);
  }, duration);
}

// ─────────────────────────────────────────────────────────────
// Modal Management
// ─────────────────────────────────────────────────────────────

function showModal(id) {
  const overlay = document.getElementById(id);
  if (overlay) {
    overlay.classList.remove('hidden');
    setTimeout(() => {
      const focusable = overlay.querySelector('textarea, input, select');
      if (focusable) focusable.focus();
    }, 50);
  }
}

function hideModal(id) {
  const overlay = document.getElementById(id);
  if (overlay) overlay.classList.add('hidden');
}

// Expose for inline handlers
window.showModal = showModal;
window.hideModal = hideModal;

// ─────────────────────────────────────────────────────────────
// Loading & Status
// ─────────────────────────────────────────────────────────────

function setLoading(isLoading) {
  state.isGenerating = isLoading;

  if (dom.statusDot) dom.statusDot.classList.toggle('active', isLoading);
  if (dom.statusText) dom.statusText.textContent = isLoading ? 'PROOFING...' : 'READY';
  if (dom.aiStatusText) dom.aiStatusText.textContent = isLoading ? 'PROOFING...' : 'READY';

  if (dom.sendBtn) dom.sendBtn.disabled = isLoading;
  if (dom.regenBtn) dom.regenBtn.disabled = isLoading;

  if (isLoading) {
    if (dom.draftEmptyRow) dom.draftEmptyRow.classList.add('hidden');
    if (dom.draftHeader) dom.draftHeader.classList.remove('hidden');
    if (dom.draftContent) {
      dom.draftContent.classList.remove('hidden');
      dom.draftContent.innerHTML = '<span class="draft-placeholder">Composing takes on baseline grid...</span>';
    }
    if (dom.draftActions) dom.draftActions.classList.add('hidden');
    if (dom.draftVariants) dom.draftVariants.classList.add('hidden');
    if (dom.confidenceBadge) dom.confidenceBadge.classList.add('hidden');
    if (dom.draftShortcutHint) dom.draftShortcutHint.classList.add('hidden');
  }
}

// ─────────────────────────────────────────────────────────────
// Render Functions
// ─────────────────────────────────────────────────────────────

/**
 * Render message history into the chat panel.
 */
function renderMessages(messages) {
  if (!dom.messageHistory) return;

  // Clear existing
  dom.messageHistory.innerHTML = '';

  if (!messages || messages.length === 0) {
    dom.messageHistory.innerHTML = `
      <div class="message-history-empty" id="emptyState">
        <div class="empty-icon-box">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        </div>
        <p>No messages recorded yet.<br />Paste incoming message below to begin proofing.</p>
      </div>`;
    return;
  }

  const fragment = document.createDocumentFragment();

  messages.forEach((msg) => {
    const row = document.createElement('div');
    const isOutgoing = msg.role === 'assistant' || msg.role === 'you' || msg.role === 'outgoing';
    row.className = `message ${isOutgoing ? 'message-outgoing' : 'message-incoming'}`;

    const wasEdited = isOutgoing && msg.was_edited;
    const senderName = isOutgoing ? 'YOU' : (state.currentContact?.name?.toUpperCase() || 'THEM');

    row.innerHTML = `
      <div class="message-bubble${wasEdited ? ' was-edited' : ''}">
        ${escapeHtml(msg.content || msg.text || '')}
      </div>
      <div class="message-meta">
        <span>${senderName}</span> · <span>${relativeTime(msg.timestamp)}</span>
      </div>
    `;
    fragment.appendChild(row);
  });

  dom.messageHistory.appendChild(fragment);

  // Keep last message strictly visible
  requestAnimationFrame(() => {
    dom.messageHistory.scrollTop = dom.messageHistory.scrollHeight;
  });
}

/**
 * Append a single message live.
 */
function appendMessage(msg) {
  if (!state.messages) state.messages = [];
  state.messages.push(msg);

  const emptyEl = dom.messageHistory.querySelector('.message-history-empty');
  if (emptyEl) emptyEl.remove();

  const row = document.createElement('div');
  const isOutgoing = msg.role === 'assistant' || msg.role === 'you' || msg.role === 'outgoing';
  row.className = `message ${isOutgoing ? 'message-outgoing' : 'message-incoming'}`;

  const wasEdited = isOutgoing && msg.was_edited;
  const senderName = isOutgoing ? 'YOU' : (state.currentContact?.name?.toUpperCase() || 'THEM');

  row.innerHTML = `
    <div class="message-bubble${wasEdited ? ' was-edited' : ''}">
      ${escapeHtml(msg.content || msg.text || '')}
    </div>
    <div class="message-meta">
      <span>${senderName}</span> · <span>${relativeTime(msg.timestamp)}</span>
    </div>
  `;

  dom.messageHistory.appendChild(row);

  // Smooth scroll so the thread's last message is always in full view
  requestAnimationFrame(() => {
    dom.messageHistory.scrollTop = dom.messageHistory.scrollHeight;
  });
}

/**
 * Render contact profile into the sidebar form.
 */
function renderContactProfile(contact) {
  if (!contact) {
    if (dom.contactName) dom.contactName.value = '';
    if (dom.contactStage) dom.contactStage.value = 'stranger';
    if (dom.contactGoal) dom.contactGoal.value = 'just_vibing';
    if (dom.contactImpression) dom.contactImpression.value = '';
    if (dom.contactStrategyNote) dom.contactStrategyNote.value = '';
    if (dom.contactHow) dom.contactHow.value = '';
    if (dom.contactInterests) dom.contactInterests.value = '';
    if (dom.contactJokes) dom.contactJokes.value = '';
    if (dom.contactNotes) dom.contactNotes.value = '';
    syncSegmentedControls('stranger', 'just_vibing');
    renderInterestTags('');
    renderFacts([]);
    if (dom.newFactRow) dom.newFactRow.classList.add('hidden');
    return;
  }

  if (dom.contactName) dom.contactName.value = contact.name || '';
  if (dom.contactStage) dom.contactStage.value = contact.relationship_stage || 'stranger';
  if (dom.contactGoal) dom.contactGoal.value = contact.convo_goal || 'just_vibing';
  if (dom.contactImpression) dom.contactImpression.value = contact.my_impression || '';
  if (dom.contactStrategyNote) dom.contactStrategyNote.value = contact.strategy_note || '';
  if (dom.contactHow) dom.contactHow.value = contact.how_you_know || '';
  
  const interestsStr = contact.their_interests ? contact.their_interests.join(', ') : '';
  if (dom.contactInterests) dom.contactInterests.value = interestsStr;
  renderInterestTags(interestsStr);

  const jokesStr = contact.inside_jokes ? contact.inside_jokes.join('\n') : '';
  if (dom.contactJokes) dom.contactJokes.value = jokesStr;

  if (dom.contactNotes) dom.contactNotes.value = contact.notes || '';

  syncSegmentedControls(contact.relationship_stage || 'stranger', contact.convo_goal || 'just_vibing');
  loadAndRenderFacts(contact.id);
}

/**
 * Sync custom segmented buttons with underlying source-of-truth select values.
 */
function syncSegmentedControls(stageVal, goalVal) {
  if (dom.stageSegmentedGroup) {
    dom.stageSegmentedGroup.querySelectorAll('.segmented-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.val === stageVal);
    });
  }
  if (dom.goalSegmentedGroup) {
    dom.goalSegmentedGroup.querySelectorAll('.segmented-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.val === goalVal);
    });
  }
}

/**
 * Render removable interest tag chips.
 */
function renderInterestTags(interestsStr) {
  if (!dom.interestsTagsContainer) return;
  dom.interestsTagsContainer.innerHTML = '';
  if (!interestsStr) return;

  const tags = interestsStr.split(',').map(s => s.trim()).filter(Boolean);
  tags.forEach((tag, idx) => {
    const chip = document.createElement('span');
    chip.className = 'tag-chip';
    chip.innerHTML = `#${escapeHtml(tag)} <span class="tag-chip-remove" data-idx="${idx}" title="Remove interest">✕</span>`;
    
    chip.querySelector('.tag-chip-remove').addEventListener('click', () => {
      tags.splice(idx, 1);
      const updatedStr = tags.join(', ');
      dom.contactInterests.value = updatedStr;
      renderInterestTags(updatedStr);
    });
    dom.interestsTagsContainer.appendChild(chip);
  });
}

/**
 * Render list of facts into index-card rows.
 */
function renderFacts(facts) {
  state.facts = facts || [];
  if (dom.contactFactCount) {
    dom.contactFactCount.textContent = state.facts.length;
  }
  if (!dom.contactFactList) return;

  if (state.facts.length === 0) {
    dom.contactFactList.innerHTML = '<div class="fact-empty-hint machine" style="font-size:11px; color:var(--text-muted); padding:4px 0;">NO FACTS RECORDED YET.</div>';
    return;
  }

  dom.contactFactList.innerHTML = '';
  state.facts.forEach((f) => {
    const item = document.createElement('div');
    item.className = 'fact-item';
    const cat = (f.category || 'preference').toLowerCase();
    item.innerHTML = `
      <div class="fact-item-content">
        <span class="fact-cat-badge fact-cat-${escapeHtml(cat)}">${escapeHtml(cat)}</span>
        <span class="fact-text">${escapeHtml(f.fact)}</span>
      </div>
      <button class="fact-delete-btn" title="Remove fact" data-id="${f.id}">✕</button>
    `;
    const delBtn = item.querySelector('.fact-delete-btn');
    delBtn.addEventListener('click', () => handleDeleteFact(f.id));
    dom.contactFactList.appendChild(item);
  });
}

async function loadAndRenderFacts(contactId) {
  if (!contactId) {
    renderFacts([]);
    return;
  }
  try {
    const facts = await api.getFacts(contactId);
    renderFacts(Array.isArray(facts) ? facts : []);
  } catch (err) {
    renderFacts([]);
  }
}

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
    showToast('Fact recorded.', 'success');
  } catch (err) {
    showToast(`Failed: ${err.message}`, 'error');
  }
}

async function handleDeleteFact(factId) {
  try {
    await api.deleteFact(factId);
    state.facts = state.facts.filter((f) => f.id !== factId);
    renderFacts(state.facts);
    showToast('Fact removed.', 'info');
  } catch (err) {
    showToast(`Failed: ${err.message}`, 'error');
  }
}

/**
 * Render draft content as dashed bubble bursts or single bubble resting on baseline grid.
 */
function renderDraftContent(draftText, bubbles = []) {
  if (!dom.draftContent) return;
  dom.draftContent.innerHTML = '';

  if (bubbles && bubbles.length > 1) {
    const stack = document.createElement('div');
    stack.className = 'dashboard-bubbles-stack';
    bubbles.forEach((bText, idx) => {
      const bEl = document.createElement('div');
      bEl.className = 'dashboard-bubble-item';
      bEl.style.animationDelay = `${idx * 45}ms`;
      const formatted = renderTextWithMarks(bText, state.previousDraft);
      bEl.innerHTML = `
        <span class="bubble-idx">0${idx + 1}</span>
        <span class="bubble-text">${formatted}</span>
      `;
      stack.appendChild(bEl);
    });
    dom.draftContent.appendChild(stack);
  } else {
    const bEl = document.createElement('div');
    bEl.className = 'dashboard-bubble-item';
    bEl.style.maxWidth = '100%';
    bEl.style.alignSelf = 'stretch';
    const formatted = renderTextWithMarks(draftText, state.previousDraft);
    bEl.innerHTML = `<span class="bubble-text">${formatted}</span>`;
    dom.draftContent.appendChild(bEl);
  }
}

/**
 * Show the AI draft in the draft panel.
 */
function showDraft(draft, confidence, variants = [], bubbles = []) {
  // Track previous draft for revision diff
  if (state.currentDraft && state.currentDraft !== draft) {
    state.previousDraft = state.currentDraft;
  }

  state.currentDraft = draft;
  state.currentDraftRaw = draft;
  state.currentConfidence = confidence;
  state.currentVariants = variants;
  state.isEditing = false;

  // Reveal active draft controls and hide empty row
  if (dom.draftEmptyRow) dom.draftEmptyRow.classList.add('hidden');
  if (dom.draftHeader) dom.draftHeader.classList.remove('hidden');
  if (dom.draftContent) dom.draftContent.classList.remove('hidden');
  if (dom.draftActions) dom.draftActions.classList.remove('hidden');
  if (dom.draftShortcutHint) dom.draftShortcutHint.classList.remove('hidden');

  // Render Tone Takes Tabs (A · CHILL [2], B · DIRECT, C · BANTER [2])
  if (dom.draftVariants) {
    if (variants && variants.length > 0) {
      dom.draftVariants.innerHTML = '';
      const tabLetters = ['A', 'B', 'C', 'D'];
      variants.forEach((v, idx) => {
        const letter = tabLetters[idx] || String(idx + 1);
        const countBadge = v.bubbles && v.bubbles.length > 1
          ? `<span class="variant-count">[${v.bubbles.length}]</span>`
          : '';
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = `variant-chip ${v.text === draft ? 'active' : ''}`;
        btn.dataset.variant = v.label;
        btn.innerHTML = `<span>${letter} · ${escapeHtml(v.label.toUpperCase())}</span> ${countBadge}`;
        
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

  // Active Take Content
  const activeVar = variants.find((v) => v.text === draft) || variants[0];
  const activeBubbles = bubbles.length ? bubbles : (activeVar?.bubbles || []);
  renderDraftContent(draft, activeBubbles);

  // Confidence badge
  if (dom.confidenceBadge) {
    dom.confidenceBadge.textContent = `${Math.round(confidence * 100)}% CONF`;
    dom.confidenceBadge.classList.remove('hidden');
  }

  // Auto-scroll chat so the last received message remains 100% visible
  requestAnimationFrame(() => {
    dom.messageHistory.scrollTop = dom.messageHistory.scrollHeight;
  });
}

function resetDraftState() {
  state.currentDraft = null;
  state.currentDraftRaw = null;
  state.currentConfidence = null;
  state.isEditing = false;

  if (dom.draftEmptyRow) dom.draftEmptyRow.classList.remove('hidden');
  if (dom.draftHeader) dom.draftHeader.classList.add('hidden');
  if (dom.draftVariants) dom.draftVariants.classList.add('hidden');
  if (dom.draftContent) {
    dom.draftContent.classList.add('hidden');
    dom.draftContent.innerHTML = '';
  }
  if (dom.draftActions) dom.draftActions.classList.add('hidden');
  if (dom.draftShortcutHint) dom.draftShortcutHint.classList.add('hidden');
}

// ─────────────────────────────────────────────────────────────
// Event Handlers
// ─────────────────────────────────────────────────────────────

async function handleSend() {
  const text = dom.messageInput.value.trim();
  if (!text || state.isGenerating) return;

  if (!state.currentContact) {
    showToast('Select a contact first.', 'warning');
    return;
  }

  state.isGenerating = true;
  dom.sendBtn.disabled = true;
  state.lastIncomingMessage = text;

  // Add incoming message bubble to chat
  appendMessage({
    role: 'incoming',
    content: text,
    timestamp: new Date().toISOString()
  });

  // Clear composer textarea
  dom.messageInput.value = '';
  autoResize(dom.messageInput);

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

      if (steering) {
        try {
          const contacts = await api.getContacts();
          state.contacts = Array.isArray(contacts) ? contacts : (contacts?.contacts || []);
          const updated = state.contacts.find((c) => String(c.id) === String(state.currentContact.id));
          if (updated) {
            state.currentContact = updated;
            renderContactProfile(updated);
          }
        } catch {}
      }

      if (result.retrieved_memories !== undefined) {
        const count = Array.isArray(result.retrieved_memories)
          ? result.retrieved_memories.length
          : result.retrieved_memories;
        dom.aiMemoryCount.textContent = count;
      }
    } else {
      showToast('No draft generated. Try again.', 'warning');
      resetDraftState();
    }
  } catch (err) {
    setLoading(false);
    resetDraftState();
    showToast(`Error: ${err.message}`, 'error');
  }
}

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
      showToast(state.proMode ? 'PRO DRAFT REGENERATED' : 'DRAFT REGENERATED', 'info');
    }
  } catch (err) {
    setLoading(false);
    showToast(`Error: ${err.message}`, 'error');
  }
}

function handleEditDraft() {
  if (!state.currentDraft) return;

  state.isEditing = !state.isEditing;

  if (state.isEditing) {
    const currentText = state.currentDraft;
    dom.draftContent.innerHTML = '';
    const textarea = document.createElement('textarea');
    textarea.value = currentText;
    textarea.addEventListener('input', () => {
      state.currentDraft = textarea.value;
      autoResize(textarea);
    });
    dom.draftContent.appendChild(textarea);
    textarea.focus();
    autoResize(textarea);
    dom.editDraftBtn.title = 'Done editing';
  } else {
    renderDraftContent(state.currentDraft);
    dom.editDraftBtn.title = 'Edit draft manually';
  }
}

async function handleApprove() {
  if (!state.currentDraft || !state.currentContact) return;

  const finalMessage = state.currentDraft;
  const draftRaw = state.currentDraftRaw;
  const wasEdited = finalMessage !== draftRaw;

  // Solidify the dashed draft bubbles into solid ink bubbles by adding to message history
  appendMessage({
    role: 'outgoing',
    content: finalMessage,
    timestamp: new Date().toISOString(),
    was_edited: wasEdited
  });

  // Copy to clipboard
  const copied = await copyToClipboard(finalMessage);
  if (copied) {
    showToast('APPROVED & COPIED', 'success');
  }

  // Clear draft desk back to empty state row
  resetDraftState();

  // Save approval to backend
  try {
    await api.approve(state.currentContact.id, draftRaw, finalMessage);
    updateStats();
  } catch (err) {
    console.error('Approve save error:', err);
  }
}

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
    inside_jokes: jokesVal ? jokesVal.split('\n').map(s => s.trim()).filter(Boolean) : [],
    notes: dom.contactNotes.value.trim()
  };

  if (!contactData.name) {
    showToast('Please enter a contact name.', 'warning');
    dom.contactName.focus();
    return;
  }

  try {
    if (state.currentContact && state.currentContact.id) {
      const updated = await api.updateContact(state.currentContact.id, contactData);
      state.currentContact = { ...state.currentContact, ...contactData, ...updated };
      showToast('DOSSIER UPDATED', 'success');
    } else {
      const created = await api.createContact(contactData);
      state.currentContact = created;
      state.contacts.push(created);
      renderContacts(state.contacts);
      dom.contactSelector.value = created.id;
      showToast('DOSSIER CREATED', 'success');
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, 'error');
  }
}

async function handleContactChange() {
  const val = dom.contactSelector.value;

  if (val === '__new__') {
    state.currentContact = null;
    renderContactProfile(null);
    state.messages = [];
    renderMessages([]);
    resetDraftState();
    dom.contactName.focus();
    return;
  }

  if (!val) {
    state.currentContact = null;
    renderContactProfile(null);
    state.messages = [];
    renderMessages([]);
    resetDraftState();
    return;
  }

  const contact = state.contacts.find((c) => String(c.id) === String(val));
  if (contact) {
    state.currentContact = contact;
    renderContactProfile(contact);
    resetDraftState();

    try {
      const history = await api.getHistory(contact.id);
      state.messages = Array.isArray(history) ? history : (history?.messages || []);
      renderMessages(state.messages);
    } catch {
      state.messages = [];
      renderMessages([]);
    }
  }
}

function handleMoodSelect(e) {
  const chip = e.target.closest('.mood-chip');
  if (!chip) return;

  $$('.mood-chip').forEach((c) => c.classList.remove('active'));
  chip.classList.add('active');
  state.currentMood = chip.dataset.mood;
}

function renderContacts(contacts) {
  dom.contactSelector.innerHTML = `
    <option value="">— SELECT CONTACT —</option>
    <option value="__new__">＋ NEW CONTACT</option>
  `;

  contacts.forEach((c) => {
    const opt = document.createElement('option');
    opt.value = c.id;
    opt.textContent = (c.name || `CONTACT ${c.id}`).toUpperCase();
    if (state.currentContact && state.currentContact.id === c.id) {
      opt.selected = true;
    }
    dom.contactSelector.appendChild(opt);
  });
}

// ─────────────────────────────────────────────────────────────
// Event Binding
// ─────────────────────────────────────────────────────────────

function bindEvents() {
  // Theme toggle
  if (dom.themeToggleBtn) {
    dom.themeToggleBtn.addEventListener('click', toggleTheme);
  }

  // Pro Mode toggle
  if (dom.proModeBtn) {
    dom.proModeBtn.addEventListener('click', () => {
      state.proMode = !state.proMode;
      dom.proModeBtn.classList.toggle('active', state.proMode);
      dom.proModeBtn.textContent = state.proMode ? 'PRO [ON]' : 'PRO [OFF]';
      showToast(state.proMode ? 'PRO MODE ENGAGED' : 'PRO MODE DISENGAGED', 'info');
    });
  }

  // Margin-Note toggle
  if (dom.noteToggleBtn && dom.marginNoteRow) {
    dom.noteToggleBtn.addEventListener('click', () => {
      dom.marginNoteRow.classList.toggle('hidden');
      dom.noteToggleBtn.classList.toggle('active', !dom.marginNoteRow.classList.contains('hidden'));
      if (!dom.marginNoteRow.classList.contains('hidden')) {
        dom.steeringInput.focus();
      }
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

  // Revision marks toggle
  if (dom.marksToggleBtn) {
    dom.marksToggleBtn.addEventListener('click', () => {
      state.showMarks = !state.showMarks;
      dom.marksToggleBtn.classList.toggle('active', state.showMarks);
      if (state.currentDraft) {
        renderDraftContent(state.currentDraft);
      }
      showToast(state.showMarks ? 'REVISION MARKS ON' : 'REVISION MARKS OFF', 'info');
    });
  }

  // Send message
  if (dom.sendBtn) {
    dom.sendBtn.addEventListener('click', handleSend);
  }

  // Auto-resize input
  if (dom.messageInput) {
    dom.messageInput.addEventListener('input', () => autoResize(dom.messageInput));
  }

  // Attach button & visually hidden native file input
  if (dom.uploadImgBtn && dom.imageUpload) {
    dom.uploadImgBtn.addEventListener('click', () => dom.imageUpload.click());
  }
  if (dom.imageUpload) {
    dom.imageUpload.addEventListener('change', (e) => {
      if (e.target.files && e.target.files[0]) {
        showToast('Processing attachment...', 'info');
      }
    });
  }

  // Draft actions
  if (dom.editDraftBtn) dom.editDraftBtn.addEventListener('click', handleEditDraft);
  if (dom.regenBtn) dom.regenBtn.addEventListener('click', handleRegenerate);
  if (dom.approveBtn) dom.approveBtn.addEventListener('click', handleApprove);

  // Contact
  if (dom.contactSelector) dom.contactSelector.addEventListener('change', handleContactChange);
  if (dom.saveContactBtn) dom.saveContactBtn.addEventListener('click', handleSaveContact);

  // Segmented controls for Stage & Goal
  if (dom.stageSegmentedGroup) {
    dom.stageSegmentedGroup.addEventListener('click', (e) => {
      const btn = e.target.closest('.segmented-btn');
      if (!btn) return;
      dom.stageSegmentedGroup.querySelectorAll('.segmented-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      dom.contactStage.value = btn.dataset.val;
      dom.contactStage.dispatchEvent(new Event('change'));
    });
  }

  if (dom.goalSegmentedGroup) {
    dom.goalSegmentedGroup.addEventListener('click', (e) => {
      const btn = e.target.closest('.segmented-btn');
      if (!btn) return;
      dom.goalSegmentedGroup.querySelectorAll('.segmented-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      dom.contactGoal.value = btn.dataset.val;
      dom.contactGoal.dispatchEvent(new Event('change'));
    });
  }

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

  // Mood selector
  if (dom.moodSelector) {
    dom.moodSelector.addEventListener('click', handleMoodSelect);
  }

  // Modals & Data management
  if (dom.ingestBtn) dom.ingestBtn.addEventListener('click', () => showModal('ingestModal'));
  if (dom.editSoulBtn) dom.editSoulBtn.addEventListener('click', async () => {
    showModal('soulModal');
    dom.soulEditor.value = 'Loading...';
    try {
      const data = await api.getSoul();
      dom.soulEditor.value = data?.content || data || '';
    } catch (err) {
      dom.soulEditor.value = `Error: ${err.message}`;
    }
  });
  if (dom.viewStyleBtn) dom.viewStyleBtn.addEventListener('click', async () => {
    showModal('styleModal');
    dom.styleContent.textContent = 'Loading...';
    try {
      const data = await api.getStyle();
      dom.styleContent.textContent = data?.content || data || 'No STYLE.md found.';
    } catch (err) {
      dom.styleContent.textContent = `Error: ${err.message}`;
    }
  });

  if (dom.saveSoulBtn) {
    dom.saveSoulBtn.addEventListener('click', async () => {
      try {
        await api.saveSoul(dom.soulEditor.value);
        hideModal('soulModal');
        showToast('SOUL.MD SAVED', 'success');
      } catch (err) {
        showToast(`Save failed: ${err.message}`, 'error');
      }
    });
  }

  // Keyboard Shortcuts
  document.addEventListener('keydown', (e) => {
    // Ctrl+Enter → Send
    if (e.ctrlKey && e.key === 'Enter') {
      e.preventDefault();
      handleSend();
    }

    // Ctrl+Shift+C → Copy/Approve draft
    if (e.ctrlKey && e.shiftKey && (e.key === 'c' || e.key === 'C')) {
      e.preventDefault();
      if (state.currentDraft) {
        handleApprove();
      }
    }

    // Ctrl+K → Toggle Note row
    if (e.ctrlKey && (e.key === 'k' || e.key === 'K')) {
      e.preventDefault();
      if (dom.marginNoteRow) {
        dom.marginNoteRow.classList.toggle('hidden');
        if (!dom.marginNoteRow.classList.contains('hidden')) {
          dom.steeringInput.focus();
        }
      }
    }
  });
}

// ─────────────────────────────────────────────────────────────
// Initialization
// ─────────────────────────────────────────────────────────────

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
  applyTheme(state.theme);
  bindEvents();
  updateStats();

  try {
    const contacts = await api.getContacts();
    state.contacts = Array.isArray(contacts) ? contacts : (contacts?.contacts || []);
    renderContacts(state.contacts);

    if (state.contacts.length > 0) {
      state.currentContact = state.contacts[0];
      dom.contactSelector.value = state.contacts[0].id;
      renderContactProfile(state.contacts[0]);

      try {
        const history = await api.getHistory(state.contacts[0].id);
        state.messages = Array.isArray(history) ? history : (history?.messages || []);
        renderMessages(state.messages);
      } catch {}
    }
  } catch (err) {
    console.warn('Could not load contacts:', err.message);
  }
}

// Expose helpers for external controllers and testing
window.showDraft = showDraft;
window.appendMessage = appendMessage;

document.addEventListener('DOMContentLoaded', init);
