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
  theme: localStorage.getItem('talking_theme') || (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),
  watcherRunning: false,
  watcherFullAuto: false,
  watcherPollInterval: null
};

// ─────────────────────────────────────────────────────────────
// API Layer
// ─────────────────────────────────────────────────────────────

const api = {
  /** Helper: make a fetch request and return parsed JSON. */
  async _fetch(url, options = {}) {
    const isFormData = options.body instanceof FormData;
    const defaultHeaders = isFormData ? {} : { 'Content-Type': 'application/json' };
    const res = await fetch(url, {
      ...options,
      headers: { ...defaultHeaders, ...(options.headers || {}) }
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
  },

  // ── Image OCR / Extraction ──
  extractText(file) {
    const formData = new FormData();
    formData.append('file', file);
    return this._fetch('/api/extract-text', {
      method: 'POST',
      body: formData
    });
  },

  // ── Watcher ──
  startWatcher(contactId, instagramUrl, mood = 'default', fullAuto = false) {
    return this._fetch('/api/watcher/start', {
      method: 'POST',
      body: JSON.stringify({
        contact_id: contactId,
        instagram_url: instagramUrl,
        mood: mood,
        full_auto: fullAuto
      })
    });
  },

  stopWatcher() {
    return this._fetch('/api/watcher/stop', {
      method: 'POST'
    });
  },

  getWatcherStatus() {
    return this._fetch('/api/watcher/status');
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

  // Watcher / Autopilot
  watcherPanel:        $('#watcherPanel'),
  watcherStatusBadge:  $('#watcherStatusBadge'),
  watcherThreadUrl:    $('#watcherThreadUrl'),
  watcherFullAutoBtn:  $('#watcherFullAutoBtn'),
  watcherLaunchBtn:    $('#watcherLaunchBtn'),
  watcherEngineStatus: $('#watcherEngineStatus'),
  watcherLastMsgRow:   $('#watcherLastMsgRow'),
  watcherLastMsg:      $('#watcherLastMsg'),

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
  let s = String(dateStr).trim();
  if (s && !s.endsWith('Z') && !/[+-]\d{2}:?\d{2}$/.test(s)) {
    s = s.replace(' ', 'T') + 'Z';
  }
  const date = new Date(s);
  if (isNaN(date.getTime())) return '';
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

  const oldWords = oldText.trim().split(/\s+/).filter(Boolean);
  const newWords = newText.trim().split(/\s+/).filter(Boolean);

  const m = oldWords.length;
  const n = newWords.length;

  // LCS dynamic programming table
  const dp = Array.from({ length: m + 1 }, () => new Int32Array(n + 1));
  const norm = (w) => w.toLowerCase().replace(/[^\w]/g, '');

  for (let i = 1; i <= m; i++) {
    const w1 = norm(oldWords[i - 1]);
    for (let j = 1; j <= n; j++) {
      if (w1 && w1 === norm(newWords[j - 1])) {
        dp[i][j] = dp[i - 1][j - 1] + 1;
      } else {
        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
      }
    }
  }

  // Backtrack to preserve word order with deletions and additions in place
  let i = m;
  let j = n;
  const tokens = [];

  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && norm(oldWords[i - 1]) && norm(oldWords[i - 1]) === norm(newWords[j - 1])) {
      tokens.push(escapeHtml(newWords[j - 1]));
      i--;
      j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      tokens.push(`<span class="mark-added">${escapeHtml(newWords[j - 1])}</span>`);
      j--;
    } else if (i > 0) {
      tokens.push(`<span class="mark-deleted">${escapeHtml(oldWords[i - 1])}</span>`);
      i--;
    }
  }

  tokens.reverse();
  return tokens.join(' ');
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
// Modal Management (Focus Trapping & Escape Stack)
// ─────────────────────────────────────────────────────────────

const modalStack = [];

function showModal(id, openerElement) {
  const overlay = document.getElementById(id);
  if (!overlay) return;

  const opener = openerElement || document.activeElement;
  modalStack.push({ id, overlay, opener });

  overlay.classList.remove('hidden');

  setTimeout(() => {
    const focusable = overlay.querySelectorAll('textarea:not([disabled]), input:not([disabled]), select:not([disabled]), button:not([disabled]), [tabindex]:not([tabindex="-1"])');
    const inputOrTextarea = overlay.querySelector('textarea, input, select');
    if (inputOrTextarea) {
      inputOrTextarea.focus();
    } else {
      const modalBox = overlay.querySelector('.modal');
      if (modalBox) {
        modalBox.setAttribute('tabindex', '-1');
        modalBox.focus();
      } else if (focusable.length > 0) {
        focusable[0].focus();
      }
    }
  }, 40);
}

function hideModal(id) {
  let modalEntry = null;
  if (id) {
    const idx = modalStack.findIndex(m => m.id === id);
    if (idx !== -1) {
      modalEntry = modalStack.splice(idx, 1)[0];
    }
  } else if (modalStack.length > 0) {
    modalEntry = modalStack.pop();
  }

  const overlay = modalEntry?.overlay || (id ? document.getElementById(id) : null);
  if (overlay) overlay.classList.add('hidden');

  if (modalEntry && modalEntry.opener && typeof modalEntry.opener.focus === 'function' && document.body.contains(modalEntry.opener)) {
    modalEntry.opener.focus();
  }
}

// Modal Focus Trap and Escape key listener
document.addEventListener('keydown', (e) => {
  if (modalStack.length === 0) return;
  const top = modalStack[modalStack.length - 1];

  if (e.key === 'Escape') {
    e.preventDefault();
    e.stopPropagation();
    hideModal(top.id);
    return;
  }

  if (e.key === 'Tab') {
    const focusableElements = Array.from(top.overlay.querySelectorAll(
      'button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )).filter(el => el.offsetParent !== null || el.offsetWidth > 0 || el.offsetHeight > 0);

    if (focusableElements.length === 0) {
      e.preventDefault();
      return;
    }

    const first = focusableElements[0];
    const last = focusableElements[focusableElements.length - 1];

    if (e.shiftKey) {
      if (document.activeElement === first || !top.overlay.contains(document.activeElement)) {
        e.preventDefault();
        last.focus();
      }
    } else {
      if (document.activeElement === last || !top.overlay.contains(document.activeElement)) {
        e.preventDefault();
        first.focus();
      }
    }
  }
});

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
  row.className = `message ${isOutgoing ? 'message-outgoing' : 'message-incoming'} message-animate-in`;

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

  // Announce only newest message to screen readers
  const announcer = document.getElementById('messageAnnouncer');
  if (announcer) {
    announcer.textContent = `${senderName}: ${msg.content || msg.text || ''}`;
  }

  // Smooth scroll so the thread's last message is always in full view
  requestAnimationFrame(() => {
    dom.messageHistory.scrollTop = dom.messageHistory.scrollHeight;
  });
  return row;
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

  if (dom.watcherThreadUrl) {
    dom.watcherThreadUrl.value = localStorage.getItem(`talking_ig_url_${contact.id}`) || '';
  }
}

/**
 * Sync custom segmented buttons with underlying source-of-truth select values.
 */
function syncSegmentedControls(stageVal, goalVal) {
  if (dom.stageSegmentedGroup) {
    dom.stageSegmentedGroup.querySelectorAll('.segmented-btn').forEach(btn => {
      const isActive = btn.dataset.val === stageVal;
      btn.classList.toggle('active', isActive);
      btn.setAttribute('aria-pressed', String(isActive));
    });
  }
  if (dom.goalSegmentedGroup) {
    dom.goalSegmentedGroup.querySelectorAll('.segmented-btn').forEach(btn => {
      const isActive = btn.dataset.val === goalVal;
      btn.classList.toggle('active', isActive);
      btn.setAttribute('aria-pressed', String(isActive));
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
  state.facts = state.facts.filter((f) => f.id !== factId);
  renderFacts(state.facts);
  try {
    await api.deleteFact(factId);
    showToast('Fact removed.', 'info');
  } catch (err) {
    showToast(`Failed: ${err.message}`, 'error');
    if (state.currentContact) loadAndRenderFacts(state.currentContact.id);
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
        btn.setAttribute('role', 'tab');
        btn.setAttribute('aria-selected', v.text === draft ? 'true' : 'false');
        btn.innerHTML = `<span>${letter} · ${escapeHtml(v.label.toUpperCase())}</span> ${countBadge}`;
        
        btn.addEventListener('click', () => {
          dom.draftVariants.querySelectorAll('.variant-chip').forEach((b) => {
            b.classList.remove('active');
            b.setAttribute('aria-selected', 'false');
          });
          btn.classList.add('active');
          btn.setAttribute('aria-selected', 'true');
          updateVariantSlider(btn);
          state.currentDraft = v.text;
          state.currentDraftRaw = v.text;
          state.isEditing = false;
          if (dom.editDraftBtn) {
            dom.editDraftBtn.title = 'Edit draft manually';
            dom.editDraftBtn.setAttribute('aria-pressed', 'false');
          }
          renderDraftContent(v.text, v.bubbles);
        });
        dom.draftVariants.appendChild(btn);
      });
      const activeBtn = dom.draftVariants.querySelector('.variant-chip.active') || dom.draftVariants.querySelector('.variant-chip');
      requestAnimationFrame(() => updateVariantSlider(activeBtn));
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

function updateVariantSlider(activeBtn) {
  if (!dom.draftVariants) return;
  const target = activeBtn || dom.draftVariants.querySelector('.variant-chip.active') || dom.draftVariants.querySelector('.variant-chip');
  if (!target) return;
  let indicator = dom.draftVariants.querySelector('.variant-sliding-indicator');
  if (!indicator) {
    indicator = document.createElement('div');
    indicator.className = 'variant-sliding-indicator';
    dom.draftVariants.appendChild(indicator);
  }
  const left = target.offsetLeft;
  const width = target.offsetWidth;
  indicator.style.width = `${width}px`;
  indicator.style.transform = `translateX(${left}px)`;
}

// Re-measure variant indicator on font load and container resize
if (document.fonts && document.fonts.ready) {
  document.fonts.ready.then(() => {
    updateVariantSlider();
  });
}
if (window.ResizeObserver) {
  const ro = new ResizeObserver(() => {
    updateVariantSlider();
  });
  const variantsContainer = document.getElementById('draftVariants');
  if (variantsContainer) ro.observe(variantsContainer);
}

function updateNoteButtonIndicator() {
  if (!dom.noteToggleBtn || !dom.steeringInput) return;
  const hasText = Boolean(dom.steeringInput.value.trim());
  const isCollapsed = dom.marginNoteRow ? dom.marginNoteRow.classList.contains('hidden') : true;
  dom.noteToggleBtn.classList.toggle('has-note', hasText && isCollapsed);
}

function resetDraftState() {
  state.currentDraft = null;
  state.currentDraftRaw = null;
  state.previousDraft = null;
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

  const targetContactId = state.currentContact.id;
  state.isGenerating = true;
  dom.sendBtn.disabled = true;
  state.lastIncomingMessage = text;

  // New incoming message: reset previous draft diff baseline
  state.previousDraft = null;

  // Add incoming message bubble optimistically to chat
  const msgObj = {
    role: 'incoming',
    content: text,
    timestamp: new Date().toISOString()
  };
  const msgRow = appendMessage(msgObj);

  // Clear composer textarea
  dom.messageInput.value = '';
  autoResize(dom.messageInput);

  setLoading(true);

  const steering = dom.steeringInput ? dom.steeringInput.value.trim() : '';

  try {
    const result = await api.sendMessage(
      targetContactId,
      text,
      state.currentMood,
      state.proMode,
      steering
    );

    // Discard if the contact was changed while the request was in flight
    if (!state.currentContact || String(state.currentContact.id) !== String(targetContactId)) {
      return;
    }

    setLoading(false);

    if (result && result.draft) {
      showDraft(result.draft, result.confidence ?? 0.85, result.variants || [], result.bubbles || []);
      updateNoteButtonIndicator();

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
      // Revert optimistic bubble and restore text
      if (!dom.messageInput.value) {
        dom.messageInput.value = text;
        autoResize(dom.messageInput);
      }
      if (msgRow && msgRow.parentNode) msgRow.remove();
      if (state.messages) {
        const idx = state.messages.indexOf(msgObj);
        if (idx !== -1) state.messages.splice(idx, 1);
        if (state.messages.length === 0) renderMessages([]);
      }
      showToast('No draft generated. Try again.', 'warning');
      resetDraftState();
    }
  } catch (err) {
    if (state.currentContact && String(state.currentContact.id) === String(targetContactId)) {
      setLoading(false);
      resetDraftState();
      // Revert optimistic bubble and restore text
      if (!dom.messageInput.value) {
        dom.messageInput.value = text;
        autoResize(dom.messageInput);
      }
      if (msgRow && msgRow.parentNode) msgRow.remove();
      if (state.messages) {
        const idx = state.messages.indexOf(msgObj);
        if (idx !== -1) state.messages.splice(idx, 1);
        if (state.messages.length === 0) renderMessages([]);
      }
      showToast(`Error: ${err.message}`, 'error');
    }
  } finally {
    state.isGenerating = false;
    dom.sendBtn.disabled = false;
  }
}

async function handleRegenerate() {
  if (!state.currentContact || !state.lastIncomingMessage || state.isGenerating) return;

  const targetContactId = state.currentContact.id;
  // Snapshot previous draft state in case regenerate fails or returns empty
  const prevDraft = state.currentDraft;
  const prevConfidence = state.currentConfidence;
  const prevVariants = state.currentVariants;
  const prevRaw = state.currentDraftRaw;
  const prevMarksDiff = state.previousDraft;

  setLoading(true);
  const steering = dom.steeringInput ? dom.steeringInput.value.trim() : '';

  try {
    const result = await api.regenerate(
      targetContactId,
      state.lastIncomingMessage,
      state.currentMood,
      state.proMode,
      steering
    );

    // Discard if the contact was changed while regenerating
    if (!state.currentContact || String(state.currentContact.id) !== String(targetContactId)) {
      return;
    }

    setLoading(false);

    if (result && result.draft) {
      showDraft(result.draft, result.confidence ?? 0.85, result.variants || [], result.bubbles || []);
      showToast(state.proMode ? 'PRO DRAFT REGENERATED' : 'DRAFT REGENERATED', 'info');
    } else {
      if (prevDraft) {
        state.previousDraft = prevMarksDiff;
        state.currentDraftRaw = prevRaw;
        showDraft(prevDraft, prevConfidence ?? 0.85, prevVariants || []);
        showToast('Regenerate returned empty. Restored previous draft.', 'warning');
      } else {
        resetDraftState();
      }
    }
  } catch (err) {
    if (state.currentContact && String(state.currentContact.id) === String(targetContactId)) {
      setLoading(false);
      if (prevDraft) {
        state.previousDraft = prevMarksDiff;
        state.currentDraftRaw = prevRaw;
        showDraft(prevDraft, prevConfidence ?? 0.85, prevVariants || []);
      } else {
        resetDraftState();
      }
      showToast(`Error: ${err.message}`, 'error');
    }
  } finally {
    state.isGenerating = false;
    if (dom.regenBtn) dom.regenBtn.disabled = false;
    if (dom.sendBtn) dom.sendBtn.disabled = false;
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
    dom.editDraftBtn.setAttribute('aria-pressed', 'true');
  } else {
    const trimmed = (state.currentDraft || '').trim();
    const doubleSplit = trimmed.split(/\n\n+/).filter(Boolean);
    const singleSplit = trimmed.split(/\n+/).filter(Boolean);
    const bubbles = doubleSplit.length > 1 ? doubleSplit : (singleSplit.length > 1 ? singleSplit : []);
    renderDraftContent(state.currentDraft, bubbles);
    dom.editDraftBtn.title = 'Edit draft manually';
    dom.editDraftBtn.setAttribute('aria-pressed', 'false');
  }
}

async function handleApprove() {
  if (!state.currentDraft || !state.currentContact) return;
  // Never approve a draft that isn't visible on screen
  if (!dom.draftContent || dom.draftContent.classList.contains('hidden') || dom.draftContent.querySelector('.draft-placeholder')) {
    return;
  }

  const finalMessage = state.currentDraft;
  const draftRaw = state.currentDraftRaw;
  const wasEdited = finalMessage !== draftRaw;

  // Copy to clipboard first; only proceed if copy succeeded
  const copied = await copyToClipboard(finalMessage);
  if (!copied) {
    showToast('Failed to copy to clipboard. Draft kept.', 'error');
    return;
  }

  showToast('APPROVED & COPIED', 'success');

  // Solidify the dashed draft bubbles into solid ink bubbles by adding to message history
  appendMessage({
    role: 'outgoing',
    content: finalMessage,
    timestamp: new Date().toISOString(),
    was_edited: wasEdited
  });

  // Clear draft desk back to empty state row
  resetDraftState();

  // Save approval to backend
  try {
    await api.approve(state.currentContact.id, draftRaw, finalMessage);
    updateStats();
  } catch (err) {
    console.error('Approve save error:', err);
    showToast('Edit was not saved for learning.', 'warning');
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

let currentHistoryRequestId = 0;

async function handleContactChange() {
  const reqId = ++currentHistoryRequestId;
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
      if (reqId !== currentHistoryRequestId || !state.currentContact || String(state.currentContact.id) !== String(contact.id)) {
        return;
      }
      state.messages = Array.isArray(history) ? history : (history?.messages || []);
      renderMessages(state.messages);
    } catch {
      if (reqId !== currentHistoryRequestId || !state.currentContact || String(state.currentContact.id) !== String(contact.id)) {
        return;
      }
      state.messages = [];
      renderMessages([]);
    }
  }
}

function handleMoodSelect(e) {
  const chip = e.target.closest('.mood-chip');
  if (!chip) return;

  $$('.mood-chip').forEach((c) => {
    c.classList.remove('active');
    c.setAttribute('aria-pressed', 'false');
  });
  chip.classList.add('active');
  chip.setAttribute('aria-pressed', 'true');
  state.currentMood = chip.dataset.mood;
}

function selectDropdownOption(val) {
  const trigger = document.getElementById('customContactTrigger');
  const dropdown = document.getElementById('customContactDropdown');
  if (dom.contactSelector) {
    dom.contactSelector.value = val;
    dom.contactSelector.dispatchEvent(new Event('change'));
  }
  if (dropdown) dropdown.classList.add('hidden');
  if (trigger) {
    trigger.classList.remove('open');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.focus();
  }
  renderCustomContactDropdown(state.contacts);
}

function renderCustomContactDropdown(contacts) {
  const trigger = document.getElementById('customContactTrigger');
  const label = document.getElementById('customContactLabel');
  const dropdown = document.getElementById('customContactDropdown');
  if (!trigger || !dropdown || !label) return;

  // Update label
  if (state.currentContact) {
    label.textContent = (state.currentContact.name || 'CONTACT').toUpperCase();
  } else if (dom.contactSelector && dom.contactSelector.value === '__new__') {
    label.textContent = '+ NEW CONTACT';
  } else {
    label.textContent = '— SELECT CONTACT —';
  }

  dropdown.setAttribute('role', 'listbox');

  // Populate dropdown items
  dropdown.innerHTML = '';

  const addOption = (val, text, isSpecial = false) => {
    const item = document.createElement('div');
    const isSel = dom.contactSelector && dom.contactSelector.value === val;
    item.className = `custom-select-item ${isSel ? 'selected' : ''}`;
    item.dataset.value = val;
    item.setAttribute('role', 'option');
    item.setAttribute('aria-selected', isSel ? 'true' : 'false');
    item.setAttribute('tabindex', '-1');
    item.innerHTML = `<span>${escapeHtml(text)}</span>${isSel ? '<span style="color:var(--accent);">✓</span>' : ''}`;
    item.addEventListener('click', (e) => {
      e.stopPropagation();
      selectDropdownOption(val);
    });
    dropdown.appendChild(item);
  };

  addOption('', '— SELECT CONTACT —');
  addOption('__new__', '+ NEW CONTACT', true);

  if (contacts && contacts.length > 0) {
    const divider = document.createElement('div');
    divider.className = 'custom-select-divider';
    divider.setAttribute('role', 'separator');
    dropdown.appendChild(divider);

    contacts.forEach((c) => {
      addOption(c.id, (c.name || `CONTACT ${c.id}`).toUpperCase());
    });
  }
}

function initCustomContactDropdown() {
  const trigger = document.getElementById('customContactTrigger');
  const dropdown = document.getElementById('customContactDropdown');
  if (!trigger || !dropdown) return;

  trigger.setAttribute('aria-expanded', 'false');

  const openDropdown = () => {
    document.querySelectorAll('.custom-select-dropdown').forEach(d => d.classList.add('hidden'));
    document.querySelectorAll('.custom-select-trigger').forEach(t => {
      t.classList.remove('open');
      t.setAttribute('aria-expanded', 'false');
    });
    dropdown.classList.remove('hidden');
    trigger.classList.add('open');
    trigger.setAttribute('aria-expanded', 'true');

    // Focus selected option or first option
    const selected = dropdown.querySelector('.custom-select-item.selected') || dropdown.querySelector('.custom-select-item');
    if (selected) selected.focus();
  };

  const closeDropdown = () => {
    dropdown.classList.add('hidden');
    trigger.classList.remove('open');
    trigger.setAttribute('aria-expanded', 'false');
  };

  trigger.addEventListener('click', (e) => {
    e.stopPropagation();
    const isHidden = dropdown.classList.contains('hidden');
    if (isHidden) {
      openDropdown();
    } else {
      closeDropdown();
    }
  });

  // Keyboard navigation on trigger
  trigger.addEventListener('keydown', (e) => {
    if (dropdown.classList.contains('hidden')) {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') {
        e.preventDefault();
        openDropdown();
      }
    } else {
      if (e.key === 'Escape') {
        e.preventDefault();
        closeDropdown();
        trigger.focus();
      }
    }
  });

  // Keyboard navigation inside dropdown listbox
  dropdown.addEventListener('keydown', (e) => {
    const items = Array.from(dropdown.querySelectorAll('.custom-select-item'));
    if (!items.length) return;
    const currentIndex = items.indexOf(document.activeElement);

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      const nextIndex = currentIndex < items.length - 1 ? currentIndex + 1 : 0;
      items[nextIndex].focus();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const prevIndex = currentIndex > 0 ? currentIndex - 1 : items.length - 1;
      items[prevIndex].focus();
    } else if (e.key === 'Home') {
      e.preventDefault();
      items[0].focus();
    } else if (e.key === 'End') {
      e.preventDefault();
      items[items.length - 1].focus();
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      if (currentIndex !== -1) {
        selectDropdownOption(items[currentIndex].dataset.value);
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      closeDropdown();
      trigger.focus();
    } else if (e.key === 'Tab') {
      closeDropdown();
    }
  });

  document.addEventListener('click', () => {
    closeDropdown();
  });

  if (dom.contactSelector) {
    dom.contactSelector.addEventListener('change', () => {
      renderCustomContactDropdown(state.contacts);
    });
  }
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

  renderCustomContactDropdown(contacts);
}

// ─────────────────────────────────────────────────────────────
// Watcher / Autopilot Controller (Playwright Instagram Watcher)
// ─────────────────────────────────────────────────────────────

async function toggleWatcher() {
  if (state.watcherRunning) {
    // Stop watcher
    dom.watcherLaunchBtn.disabled = true;
    try {
      await api.stopWatcher();
      showToast('PLAYWRIGHT WATCHER STOPPED', 'info');
      state.watcherRunning = false;
      updateWatcherUI({ running: false, status_text: 'Stopped' });
      if (state.watcherPollInterval) {
        clearInterval(state.watcherPollInterval);
        state.watcherPollInterval = null;
      }
    } catch (err) {
      showToast(`STOP ERROR: ${err.message}`, 'error');
    } finally {
      dom.watcherLaunchBtn.disabled = false;
    }
  } else {
    // Start watcher
    if (!state.currentContact) {
      showToast('SELECT A CONTACT FIRST', 'warning');
      return;
    }
    const url = dom.watcherThreadUrl?.value.trim() || '';
    if (!url) {
      showToast('ENTER INSTAGRAM THREAD URL OR @USERNAME', 'warning');
      dom.watcherThreadUrl?.focus();
      return;
    }

    dom.watcherLaunchBtn.disabled = true;
    try {
      const res = await api.startWatcher(
        state.currentContact.id,
        url,
        state.currentMood,
        state.watcherFullAuto
      );
      state.watcherRunning = true;
      showToast('CHROME PLAYWRIGHT LAUNCHED', 'success');
      updateWatcherUI(res.state || { running: true, status_text: 'Starting...' });
      startWatcherPolling();
    } catch (err) {
      showToast(`LAUNCH ERROR: ${err.message}`, 'error');
    } finally {
      dom.watcherLaunchBtn.disabled = false;
    }
  }
}

function updateWatcherUI(ws) {
  if (!dom.watcherStatusBadge || !dom.watcherLaunchBtn) return;
  const isRunning = Boolean(ws?.running);
  state.watcherRunning = isRunning;

  dom.watcherLaunchBtn.innerHTML = isRunning
    ? `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="12" height="12"/></svg><span>STOP WATCHER</span>`
    : `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg><span>LAUNCH WATCHER</span>`;

  if (dom.watcherEngineStatus) {
    dom.watcherEngineStatus.textContent = ws?.status_text || (isRunning ? 'ACTIVE' : 'CHROME PERSISTENT');
  }

  dom.watcherStatusBadge.className = 'watcher-status-tag mono';
  if (isRunning) {
    if (ws?.status_text?.toLowerCase().includes('watching')) {
      dom.watcherStatusBadge.classList.add('watching');
      dom.watcherStatusBadge.textContent = 'WATCHING';
    } else {
      dom.watcherStatusBadge.classList.add('active');
      dom.watcherStatusBadge.textContent = 'CONNECTING...';
    }
  } else {
    dom.watcherStatusBadge.textContent = 'IDLE';
  }

  if (dom.watcherLastMsgRow && dom.watcherLastMsg) {
    if (ws?.last_message) {
      dom.watcherLastMsgRow.style.display = 'flex';
      dom.watcherLastMsg.textContent = ws.last_message;
    } else {
      dom.watcherLastMsgRow.style.display = 'none';
    }
  }

  // If a pending reply was generated by watcher and we're not in full auto, display it in draft panel!
  if (ws?.pending_reply && !state.currentDraft) {
    showDraft(ws.pending_reply, 0.92, [{ text: ws.pending_reply, label: 'direct', bubbles: [ws.pending_reply] }], ['live_dm']);
  }
}

function startWatcherPolling() {
  if (state.watcherPollInterval) clearInterval(state.watcherPollInterval);
  state.watcherPollInterval = setInterval(async () => {
    try {
      const ws = await api.getWatcherStatus();
      updateWatcherUI(ws);
      if (!ws.running && state.watcherRunning) {
        state.watcherRunning = false;
        clearInterval(state.watcherPollInterval);
        state.watcherPollInterval = null;
      }
    } catch {}
  }, 2500);
}

// ─────────────────────────────────────────────────────────────
// Event Binding
// ─────────────────────────────────────────────────────────────

function bindEvents() {
  initCustomContactDropdown();

  // Theme toggle
  if (dom.themeToggleBtn) {
    dom.themeToggleBtn.addEventListener('click', toggleTheme);
  }

  // Pro Mode toggle
  if (dom.proModeBtn) {
    dom.proModeBtn.addEventListener('click', () => {
      state.proMode = !state.proMode;
      dom.proModeBtn.classList.toggle('active', state.proMode);
      dom.proModeBtn.setAttribute('aria-pressed', String(state.proMode));
      dom.proModeBtn.textContent = state.proMode ? 'PRO [ON]' : 'PRO [OFF]';
      showToast(state.proMode ? 'PRO MODE ENGAGED' : 'PRO MODE DISENGAGED', 'info');

      // Auto-reveal steering directive control row when Pro Mode is engaged
      if (dom.marginNoteRow && dom.noteToggleBtn) {
        if (state.proMode) {
          dom.marginNoteRow.classList.remove('hidden');
          dom.noteToggleBtn.classList.add('active');
          dom.noteToggleBtn.setAttribute('aria-pressed', 'true');
          if (dom.steeringInput) {
            dom.steeringInput.focus();
          }
        } else if (!dom.steeringInput?.value.trim()) {
          dom.marginNoteRow.classList.add('hidden');
          dom.noteToggleBtn.classList.remove('active');
          dom.noteToggleBtn.setAttribute('aria-pressed', 'false');
        }
        updateNoteButtonIndicator();
      }
    });
  }

  // Margin-Note toggle
  if (dom.noteToggleBtn && dom.marginNoteRow) {
    dom.noteToggleBtn.addEventListener('click', () => {
      dom.marginNoteRow.classList.toggle('hidden');
      const isOpen = !dom.marginNoteRow.classList.contains('hidden');
      dom.noteToggleBtn.classList.toggle('active', isOpen);
      dom.noteToggleBtn.setAttribute('aria-pressed', String(isOpen));
      updateNoteButtonIndicator();
      if (isOpen) {
        dom.steeringInput.focus();
      }
    });
  }

  // Steering directive clear button
  if (dom.steeringInput && dom.clearSteerBtn) {
    dom.steeringInput.addEventListener('input', () => {
      dom.clearSteerBtn.classList.toggle('hidden', !dom.steeringInput.value.trim());
      updateNoteButtonIndicator();
    });
    dom.clearSteerBtn.addEventListener('click', () => {
      dom.steeringInput.value = '';
      dom.clearSteerBtn.classList.add('hidden');
      updateNoteButtonIndicator();
      dom.steeringInput.focus();
    });
  }

  // Revision marks toggle
  if (dom.marksToggleBtn) {
    dom.marksToggleBtn.addEventListener('click', () => {
      state.showMarks = !state.showMarks;
      dom.marksToggleBtn.classList.toggle('active', state.showMarks);
      dom.marksToggleBtn.setAttribute('aria-pressed', String(state.showMarks));
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
    dom.imageUpload.addEventListener('change', async (e) => {
      const file = e.target.files && e.target.files[0];
      if (!file) return;

      showToast('Extracting text from image...', 'info');
      if (dom.uploadImgBtn) dom.uploadImgBtn.disabled = true;

      try {
        const res = await api.extractText(file);
        if (res && res.extracted_text) {
          if (dom.messageInput) {
            dom.messageInput.value = res.extracted_text;
            autoResize(dom.messageInput);
            dom.messageInput.focus();
          }
          showToast('Text extracted from image', 'success');
        } else {
          showToast('No text detected in image.', 'warning');
        }
      } catch (err) {
        showToast(`Extraction failed: ${err.message}`, 'error');
      } finally {
        if (dom.uploadImgBtn) dom.uploadImgBtn.disabled = false;
        dom.imageUpload.value = '';
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
      dom.stageSegmentedGroup.querySelectorAll('.segmented-btn').forEach(b => {
        b.classList.remove('active');
        b.setAttribute('aria-pressed', 'false');
      });
      btn.classList.add('active');
      btn.setAttribute('aria-pressed', 'true');
      dom.contactStage.value = btn.dataset.val;
      dom.contactStage.dispatchEvent(new Event('change'));
    });
  }

  if (dom.goalSegmentedGroup) {
    dom.goalSegmentedGroup.addEventListener('click', (e) => {
      const btn = e.target.closest('.segmented-btn');
      if (!btn) return;
      dom.goalSegmentedGroup.querySelectorAll('.segmented-btn').forEach(b => {
        b.classList.remove('active');
        b.setAttribute('aria-pressed', 'false');
      });
      btn.classList.add('active');
      btn.setAttribute('aria-pressed', 'true');
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

  // Watcher / Autopilot
  if (dom.watcherLaunchBtn) {
    dom.watcherLaunchBtn.addEventListener('click', toggleWatcher);
  }
  if (dom.watcherFullAutoBtn) {
    dom.watcherFullAutoBtn.addEventListener('click', () => {
      state.watcherFullAuto = !state.watcherFullAuto;
      dom.watcherFullAutoBtn.classList.toggle('active', state.watcherFullAuto);
      dom.watcherFullAutoBtn.setAttribute('aria-pressed', String(state.watcherFullAuto));
      dom.watcherFullAutoBtn.textContent = state.watcherFullAuto ? 'AUTO-SEND [ON]' : 'AUTO-SEND [OFF]';
      showToast(state.watcherFullAuto ? 'FULL AUTO ENGAGED (AUTO-DISPATCH DMs)' : 'AUTO-SEND DISABLED', 'info');
    });
  }
  if (dom.watcherThreadUrl) {
    dom.watcherThreadUrl.addEventListener('input', () => {
      dom.watcherThreadUrl.style.height = 'auto';
      dom.watcherThreadUrl.style.height = Math.max(38, Math.min(dom.watcherThreadUrl.scrollHeight, 140)) + 'px';
      if (state.currentContact) {
        localStorage.setItem(`talking_ig_url_${state.currentContact.id}`, dom.watcherThreadUrl.value.trim());
      }
    });
  }

  const pasteWatcherUrlBtn = document.getElementById('pasteWatcherUrlBtn');
  if (pasteWatcherUrlBtn) {
    pasteWatcherUrlBtn.addEventListener('click', async () => {
      try {
        const text = await navigator.clipboard.readText();
        if (text && dom.watcherThreadUrl) {
          dom.watcherThreadUrl.value = text.trim();
          dom.watcherThreadUrl.dispatchEvent(new Event('input'));
          showToast('PASTED FROM CLIPBOARD', 'info');
        }
      } catch {
        dom.watcherThreadUrl?.focus();
      }
    });
  }

  // Ingest Source Options Buttons
  const ingestOptions = $$('.ingest-option');
  if (ingestOptions.length > 0) {
    ingestOptions.forEach((btn) => {
      btn.addEventListener('click', () => {
        ingestOptions.forEach(b => {
          b.classList.remove('selected');
          b.setAttribute('aria-pressed', 'false');
        });
        btn.classList.add('selected');
        btn.setAttribute('aria-pressed', 'true');
        state.ingestSource = btn.dataset.source;
      });
    });
  }

  // Modals & Data management
  if (dom.ingestBtn) dom.ingestBtn.addEventListener('click', (e) => showModal('ingestModal', e.currentTarget));
  if (dom.startIngestBtn) {
    dom.startIngestBtn.addEventListener('click', async () => {
      const selectedOpt = document.querySelector('.ingest-option.selected');
      const source = selectedOpt?.dataset.source || state.ingestSource || 'instagram';
      const userName = dom.ingestUserName ? dom.ingestUserName.value.trim() : '';
      const path = dom.ingestPath ? dom.ingestPath.value.trim() : '';
      if (!userName) {
        showToast('Please provide your display name.', 'warning');
        if (dom.ingestUserName) dom.ingestUserName.focus();
        return;
      }
      try {
        if (dom.ingestProgressContainer) dom.ingestProgressContainer.classList.remove('hidden');
        if (dom.ingestProgressBar) dom.ingestProgressBar.style.width = '30%';
        if (dom.ingestProgressText) dom.ingestProgressText.textContent = 'INGESTING ARCHIVE...';
        showToast('Ingesting archive...', 'info');
        await api.ingest(source, userName, path);
        if (dom.ingestProgressBar) dom.ingestProgressBar.style.width = '100%';
        if (dom.ingestProgressText) dom.ingestProgressText.textContent = 'COMPLETE';
        showToast('Ingest complete.', 'success');
        setTimeout(() => {
          hideModal('ingestModal');
          if (dom.ingestProgressContainer) dom.ingestProgressContainer.classList.add('hidden');
        }, 1000);
      } catch (err) {
        showToast(`Ingest failed: ${err.message}`, 'error');
        if (dom.ingestProgressContainer) dom.ingestProgressContainer.classList.add('hidden');
      }
    });
  }
  if (dom.editSoulBtn) dom.editSoulBtn.addEventListener('click', async (e) => {
    showModal('soulModal', e.currentTarget);
    dom.soulEditor.value = 'Loading...';
    try {
      const data = await api.getSoul();
      dom.soulEditor.value = data?.content || data || '';
    } catch (err) {
      dom.soulEditor.value = `Error: ${err.message}`;
    }
  });
  if (dom.viewStyleBtn) dom.viewStyleBtn.addEventListener('click', async (e) => {
    showModal('styleModal', e.currentTarget);
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
    // Alt+T → Toggle theme
    if (e.altKey && (e.key === 't' || e.key === 'T')) {
      e.preventDefault();
      toggleTheme();
      return;
    }

    // Ignore global action shortcuts if a modal is open
    const isModalOpen = Boolean(document.querySelector('.modal-overlay:not(.hidden)'));
    if (isModalOpen) return;

    const isCtrl = e.ctrlKey || e.metaKey;

    // Ctrl/Cmd + Shift + Enter → Copy/Approve draft
    if (isCtrl && e.shiftKey && e.key === 'Enter') {
      e.preventDefault();
      if (state.currentDraft) {
        handleApprove();
      }
      return;
    }

    // Ctrl/Cmd + Enter → Send
    if (isCtrl && !e.shiftKey && e.key === 'Enter') {
      e.preventDefault();
      handleSend();
      return;
    }

    // Ctrl/Cmd + K → Toggle Note row
    if (isCtrl && (e.key === 'k' || e.key === 'K')) {
      e.preventDefault();
      if (dom.marginNoteRow && dom.noteToggleBtn) {
        dom.marginNoteRow.classList.toggle('hidden');
        const isOpen = !dom.marginNoteRow.classList.contains('hidden');
        dom.noteToggleBtn.classList.toggle('active', isOpen);
        dom.noteToggleBtn.setAttribute('aria-pressed', String(isOpen));
        updateNoteButtonIndicator();
        if (isOpen && dom.steeringInput) {
          dom.steeringInput.focus();
        }
      }
      return;
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

  // Check initial Watcher status
  try {
    const ws = await api.getWatcherStatus();
    if (ws?.running) {
      state.watcherRunning = true;
      updateWatcherUI(ws);
      startWatcherPolling();
    }
  } catch {}

  try {
    const contacts = await api.getContacts();
    state.contacts = Array.isArray(contacts) ? contacts : (contacts?.contacts || []);
    renderContacts(state.contacts);

    if (state.contacts.length > 0) {
      state.currentContact = state.contacts[0];
      dom.contactSelector.value = state.contacts[0].id;
      renderCustomContactDropdown(state.contacts);
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
