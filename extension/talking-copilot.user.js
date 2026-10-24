// ==UserScript==
// @name         Talking Copilot (WhatsApp Web & Instagram Direct)
// @namespace    https://github.com/maneeshk/talking
// @version      1.0.0
// @description  AI texting copilot for WhatsApp Web and Instagram Direct powered by local Talking autopilot
// @match        https://web.whatsapp.com/*
// @match        https://www.instagram.com/direct/*
// @grant        GM_xmlhttpRequest
// @connect      localhost
// @connect      127.0.0.1
// @run-at       document-end
// ==/UserScript==

(function () {
  'use strict';

  const BACKEND_BASE = 'http://localhost:8000';
  let activeContactId = null;
  let activeOriginalDraft = null;
  let activeVariants = [];
  let currentVariantLabel = 'direct';
  let isProMode = false;
  try {
    isProMode = localStorage.getItem('talking_copilot_pro') === 'true';
  } catch {}

  // Inject Styles
  const css = `
    #talking-copilot-pill {
      position: fixed;
      bottom: 84px;
      right: 28px;
      z-index: 999999;
      display: flex;
      align-items: center;
      gap: 8px;
      background: rgba(15, 15, 23, 0.92);
      backdrop-filter: blur(14px);
      -webkit-backdrop-filter: blur(14px);
      border: 1px solid rgba(255, 255, 255, 0.12);
      box-shadow: 0 12px 36px rgba(0, 0, 0, 0.45);
      color: #f4f4f5;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      font-size: 13px;
      font-weight: 600;
      padding: 8px 14px;
      border-radius: 999px;
      cursor: pointer;
      user-select: none;
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    }
    #talking-copilot-pill:hover {
      transform: translateY(-2px);
      border-color: #a855f7;
      box-shadow: 0 14px 40px rgba(124, 58, 237, 0.35);
    }
    #talking-copilot-pill .tk-kbd {
      font-size: 10px;
      background: rgba(255, 255, 255, 0.1);
      padding: 2px 5px;
      border-radius: 4px;
      color: #a1a1aa;
    }
    #talking-copilot-modal {
      position: fixed;
      bottom: 120px;
      right: 28px;
      width: 380px;
      max-width: calc(100vw - 40px);
      background: rgba(15, 15, 23, 0.95);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border: 1px solid rgba(255, 255, 255, 0.12);
      box-shadow: 0 12px 36px rgba(0, 0, 0, 0.45);
      border-radius: 16px;
      z-index: 1000000;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      color: #f4f4f5;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      animation: tkFadeSlide 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    }
    @keyframes tkFadeSlide {
      from { opacity: 0; transform: translateY(12px) scale(0.97); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }
    .tk-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 16px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(255, 255, 255, 0.02);
    }
    .tk-title-wrap {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .tk-brand {
      font-weight: 700;
      font-size: 14px;
      color: #fff;
    }
    .tk-contact-tag {
      font-size: 11px;
      padding: 2px 7px;
      border-radius: 999px;
      background: rgba(124, 58, 237, 0.2);
      color: #c084fc;
      font-weight: 500;
      max-width: 140px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .tk-close-btn {
      background: transparent;
      border: none;
      color: #a1a1aa;
      font-size: 16px;
      cursor: pointer;
    }
    .tk-close-btn:hover { color: #fff; }
    .tk-body {
      padding: 14px 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .tk-incoming-snippet {
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: 8px;
      padding: 8px 10px;
      font-size: 12px;
      color: #a1a1aa;
      max-height: 54px;
      overflow-y: auto;
    }
    .tk-incoming-snippet strong { color: #e4e4e7; }
    .tk-variants-bar { display: flex; gap: 6px; }
    .tk-variant-btn {
      flex: 1;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.08);
      color: #a1a1aa;
      padding: 6px 4px;
      font-size: 11px;
      font-weight: 600;
      border-radius: 8px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 4px;
    }
    .tk-variant-btn:hover { background: rgba(255, 255, 255, 0.1); color: #fff; }
    .tk-variant-btn.tk-active {
      background: rgba(124, 58, 237, 0.25);
      border-color: rgba(168, 85, 247, 0.45);
      color: #fff;
    }
    .tk-draft-textarea {
      width: 100%;
      background: rgba(0, 0, 0, 0.3);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 10px;
      color: #fff;
      font-size: 13px;
      line-height: 1.45;
      padding: 10px 12px;
      resize: vertical;
      min-height: 70px;
      box-sizing: border-box;
      outline: none;
    }
    .tk-draft-textarea:focus { border-color: #a855f7; }
    .tk-loading-indicator {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
      gap: 8px;
      color: #a1a1aa;
      font-size: 13px;
    }
    .tk-spinner {
      width: 16px;
      height: 16px;
      border: 2px solid rgba(255, 255, 255, 0.2);
      border-top-color: #a855f7;
      border-radius: 50%;
      animation: tkSpin 0.7s linear infinite;
    }
    @keyframes tkSpin { to { transform: rotate(360deg); } }
    .tk-footer {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 16px 14px;
      border-top: 1px solid rgba(255, 255, 255, 0.06);
      gap: 8px;
    }
    .tk-left-actions { display: flex; align-items: center; gap: 8px; }
    .tk-pro-toggle {
      display: flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      color: #a1a1aa;
      cursor: pointer;
    }
    .tk-right-actions { display: flex; align-items: center; gap: 6px; }
    .tk-btn {
      font-size: 12px;
      font-weight: 600;
      padding: 7px 12px;
      border-radius: 8px;
      cursor: pointer;
      border: none;
    }
    .tk-btn-secondary {
      background: rgba(255, 255, 255, 0.05);
      color: #a1a1aa;
      border: 1px solid rgba(255, 255, 255, 0.08);
    }
    .tk-btn-secondary:hover { color: #fff; background: rgba(255, 255, 255, 0.1); }
    .tk-btn-primary {
      background: linear-gradient(135deg, #7c3aed, #a855f7);
      color: #fff;
      box-shadow: 0 4px 14px rgba(124, 58, 237, 0.4);
    }
    .tk-btn-primary:hover { filter: brightness(1.1); }
  `;

  const styleEl = document.createElement('style');
  styleEl.textContent = css;
  document.head.appendChild(styleEl);

  const isWhatsApp = () => window.location.hostname.includes('web.whatsapp.com') || window.__MOCK_PLATFORM__ === 'whatsapp';
  const isInstagram = () => window.location.hostname.includes('instagram.com') || window.__MOCK_PLATFORM__ === 'instagram';

  function getActiveContactName() {
    if (isWhatsApp()) {
      const titleEl =
        document.querySelector('header span[dir="auto"]') ||
        document.querySelector('header [data-testid="conversation-info-header-chat-title"]') ||
        document.querySelector('header div[role="button"] span[title]');
      return titleEl ? (titleEl.getAttribute('title') || titleEl.textContent || '').trim() : 'Friend';
    }
    if (isInstagram()) {
      const headerEl =
        document.querySelector('main header h2') ||
        document.querySelector('main header span[dir="auto"]') ||
        document.querySelector('header span');
      return headerEl ? headerEl.textContent.trim() : 'Friend';
    }
    return 'Friend';
  }

  // ── Quoted & Swipe-to-Reply Detection ──────────────────────────────

  function getActiveReplyBarContext() {
    if (isWhatsApp()) {
      // WhatsApp Web renders the active reply preview inside footer
      const replyBar =
        document.querySelector('footer [data-testid="quoted-message"]') ||
        document.querySelector('footer [data-testid="quote-message-container"]') ||
        document.querySelector('footer [aria-label*="Quoted"]') ||
        document.querySelector('footer .quoted-mention')?.closest('div');

      if (replyBar) {
        const senderEl =
          replyBar.querySelector('[data-testid="quoted-mention"]') ||
          replyBar.querySelector('span[dir="auto"]');
        const sender = senderEl ? senderEl.textContent.trim() : '';

        // Extract message content from the quote preview
        const clone = replyBar.cloneNode(true);
        clone.querySelectorAll('button, [data-testid="cancel-reply"]').forEach((b) => b.remove());
        let quoteText = clone.textContent.trim();
        if (sender && quoteText.startsWith(sender)) {
          quoteText = quoteText.slice(sender.length).trim();
        }

        if (quoteText || sender) {
          return `[Replying to ${sender || 'message'}: "${quoteText || sender}"]`;
        }
      }
    }

    if (isInstagram()) {
      // Instagram Direct renders a reply banner directly above the text input
      const footer =
        document.querySelector('div[role="main"] footer') ||
        document.querySelector('footer');

      if (footer) {
        const allSpans = Array.from(footer.querySelectorAll('span, div, p'));
        const replyHeader = allSpans.find((el) => {
          const t = el.textContent ? el.textContent.trim() : '';
          return t.startsWith('Replying to ') || t === 'Replying to yourself';
        });

        if (replyHeader) {
          const container =
            replyHeader.closest('div[style*="flex"]') ||
            replyHeader.closest('div') ||
            replyHeader.parentElement;

          let quoteSnippet = '';
          if (container) {
            const texts = Array.from(container.querySelectorAll('span, div, p'))
              .map((t) => t.textContent.trim())
              .filter((t) => t && !t.startsWith('Replying to') && t.length > 1);
            quoteSnippet = texts[0] || '';
          }
          return `[${replyHeader.textContent.trim()}${quoteSnippet ? ': "' + quoteSnippet + '"' : ''}]`;
        }
      }
    }

    return null;
  }

  function getLastIncomingMessage() {
    // 1. If user swiped or clicked reply to a specific message, prioritize active reply bar
    const activeReply = getActiveReplyBarContext();
    if (activeReply) {
      return activeReply;
    }

    if (isWhatsApp()) {
      const incomingNodes = document.querySelectorAll('div.message-in');
      if (incomingNodes.length === 0) return '';
      const last = incomingNodes[incomingNodes.length - 1];

      // Check if this incoming bubble quotes a previous message
      let quotedContext = '';
      const quotedEl =
        last.querySelector('[data-testid="quoted-message"]') ||
        last.querySelector('[data-testid="quote-message-container"]') ||
        last.querySelector('.quoted-mention');

      if (quotedEl) {
        const quoteClone = quotedEl.cloneNode(true);
        const quotedSender = quoteClone.querySelector('.quoted-mention')?.textContent?.trim() || '';
        const qText = quoteClone.textContent.trim();
        quotedContext = `[Replying to ${quotedSender ? quotedSender + ': ' : ''}"${qText}"]`;
      }

      const textEl = last.querySelector('.selectable-text') || last.querySelector('.copyable-text');
      let text = textEl ? textEl.textContent.trim() : '';
      if (quotedEl && text.includes(quotedEl.textContent.trim())) {
        text = text.replace(quotedEl.textContent.trim(), '').trim();
      }

      // Media checks
      const img = last.querySelector('img[src]');
      const isSticker = last.querySelector('[data-testid="sticker"]') || (img && img.src && img.src.includes('sticker'));
      const isVoice = last.querySelector('[data-testid="audio-play"]') || last.querySelector('audio') || last.querySelector('span[data-icon*="audio"]');
      const isVideo = last.querySelector('video') || last.querySelector('[data-testid="video-thumb"]');
      const isPhoto = img && !isSticker && (img.width > 50 || img.naturalWidth > 50 || last.querySelector('[data-testid="image-thumb"]'));

      let mainBody = text;
      if (isSticker) mainBody = text ? `[Sticker] ${text}` : '[Sticker]';
      else if (isVoice) mainBody = text ? `[Voice Message] ${text}` : '[Voice Message]';
      else if (isVideo) mainBody = text ? `[Video: ${text}]` : (text || '[Sent a video]');
      else if (isPhoto) {
        const alt = img.getAttribute('alt') || '';
        const desc = alt && !alt.toLowerCase().includes('photo') ? `: ${alt}` : '';
        mainBody = text ? `[Photo${desc}] ${text}` : `[Photo${desc}]`;
      }

      if (quotedContext) {
        return mainBody ? `"${mainBody}" ${quotedContext}` : quotedContext;
      }
      return mainBody;
    }

    if (isInstagram()) {
      const mainContainer = document.querySelector('div[role="main"]') || document.querySelector('main');
      if (!mainContainer) return '';

      const candidateElements = Array.from(mainContainer.querySelectorAll('div[dir="auto"], a[href*="/reel/"], a[href*="/p/"], div[role="button"] img, img'));

      for (let i = candidateElements.length - 1; i >= 0; i--) {
        const el = candidateElements[i];

        if (el.closest('header') || el.closest('footer') || el.closest('form') || el.closest('nav')) continue;
        if (el.tagName.toLowerCase() === 'img') {
          const w = el.width || parseInt(el.getAttribute('width') || '0', 10) || el.getBoundingClientRect().width;
          const h = el.height || parseInt(el.getAttribute('height') || '0', 10) || el.getBoundingClientRect().height;
          if (w < 40 && h < 40 && w > 0) continue;
        }

        let isOutgoing = false;
        let curr = el;
        while (curr && curr !== mainContainer) {
          const align = window.getComputedStyle(curr).alignSelf;
          const justify = window.getComputedStyle(curr).justifyContent;
          if (align === 'flex-end' || justify === 'flex-end') {
            isOutgoing = true;
            break;
          }
          if (align === 'flex-start' || justify === 'flex-start') {
            isOutgoing = false;
            break;
          }
          curr = curr.parentElement;
        }

        if (!isOutgoing) {
          const rect = el.getBoundingClientRect();
          let parent = el.parentElement;
          let rowRect = null;
          while (parent && parent !== mainContainer) {
            const pRect = parent.getBoundingClientRect();
            if (pRect.width >= 200 && pRect.width > rect.width * 1.1) {
              rowRect = pRect;
              break;
            }
            parent = parent.parentElement;
          }
          if (rowRect) {
            const leftDist = Math.abs(rect.left - rowRect.left);
            const rightDist = Math.abs(rowRect.right - rect.right);
            if (rightDist < leftDist * 0.75) {
              isOutgoing = true;
            }
          }
        }

        if (isOutgoing) continue;

        // Check if the message bubble has a quoted reply context inside it
        const parentRow = el.closest('div[role="row"]') || el.closest('div[style*="flex"]') || el.parentElement;
        let bubbleQuote = '';
        if (parentRow) {
          const quoteEl = parentRow.querySelector('div[style*="border-left"], div[aria-label*="replied"], a[href*="/direct/t/"]');
          if (quoteEl && quoteEl !== el && !quoteEl.contains(el)) {
            const q = quoteEl.textContent.trim();
            if (q && q.length > 2) {
              bubbleQuote = `[Replying to: "${q.slice(0, 100)}"]`;
            }
          }
        }

        const reelLink = el.closest('a[href*="/reel/"]') || el.closest('a[href*="/p/"]');
        if (reelLink) {
          const href = reelLink.href || '';
          const isReel = href.includes('/reel/');
          const img = reelLink.querySelector('img');
          const altText = img?.getAttribute('alt') || '';
          const textSnippet = Array.from(reelLink.querySelectorAll('div, span'))
            .map((s) => s.innerText?.trim())
            .filter((t) => t && !t.includes('Watch on') && !t.includes('Reel') && t.length > 2)
            .slice(0, 2)
            .join(' - ');

          let detail = textSnippet || altText;
          const reelTag = `[Shared ${isReel ? 'Instagram Reel' : 'Post'}: ${href}${detail ? ' | ' + detail : ''}]`;
          return bubbleQuote ? `${reelTag} ${bubbleQuote}` : reelTag;
        }

        if (el.tagName.toLowerCase() === 'img') {
          const alt = el.getAttribute('alt') || '';
          const photoTag = alt ? `[Sent a photo: ${alt}]` : '[Sent a photo]';
          return bubbleQuote ? `${photoTag} ${bubbleQuote}` : photoTag;
        }

        const text = el.innerText ? el.innerText.trim() : '';
        if (text && !text.includes('Seen') && !text.includes('Delivered') && text.length > 0) {
          const parentBubble = el.closest('div[role="row"]') || el.parentElement;
          if (parentBubble) {
            const innerReel = parentBubble.querySelector('a[href*="/reel/"], a[href*="/p/"]');
            if (innerReel) {
              return `[Shared Reel: ${innerReel.href}] "${text}"${bubbleQuote ? ' ' + bubbleQuote : ''}`;
            }
            const innerImg = parentBubble.querySelector('img');
            if (innerImg && innerImg.width > 60) {
              return `[Photo] "${text}"${bubbleQuote ? ' ' + bubbleQuote : ''}`;
            }
          }
          return bubbleQuote ? `"${text}" ${bubbleQuote}` : text;
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
      alert('Draft copied! Paste into chat.');
      return;
    }
    inputEl.focus();
    try {
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

  function ensureFloatingPill() {
    if (document.getElementById('talking-copilot-pill')) return;
    const pill = document.createElement('div');
    pill.id = 'talking-copilot-pill';
    pill.innerHTML = `<span>⚡</span> <span>Draft</span> <span class="tk-kbd">Alt+D</span>`;
    pill.addEventListener('click', triggerDraftGeneration);
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
    const safeSnippet = incomingText ? `"${incomingText.slice(0, 140)}"` : 'No incoming text detected';

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
        <div class="tk-incoming-snippet"><strong>They said:</strong> ${escapeHtml(safeSnippet)}</div>
        ${
          isLoading
            ? `<div class="tk-loading-indicator"><div class="tk-spinner"></div><span>Drafting personalized reply...</span></div>`
            : `<div class="tk-variants-bar" id="tk-variants-bar"></div>
               <textarea class="tk-draft-textarea" id="tk-draft-text" placeholder="Draft reply..."></textarea>`
        }
      </div>
      ${
        isLoading
          ? ''
          : `<div class="tk-footer">
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
             </div>`
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

    proToggle?.addEventListener('change', (e) => {
      isProMode = e.target.checked;
      try {
        localStorage.setItem('talking_copilot_pro', isProMode ? 'true' : 'false');
      } catch {}
    });

    regenBtn?.addEventListener('click', triggerDraftGeneration);

    copyBtn?.addEventListener('click', () => {
      navigator.clipboard.writeText(draftTextarea.value);
      copyBtn.textContent = 'Copied!';
      setTimeout(() => (copyBtn.textContent = 'Copy'), 1500);
    });

    const doInsert = () => {
      const finalMsg = draftTextarea.value.trim();
      if (!finalMsg) return;
      insertTextIntoChat(finalMsg);
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
    draftTextarea?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        doInsert();
      }
    });
    draftTextarea?.focus();
  }

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
        draft: `Could not connect to Talking at ${BACKEND_BASE}. Make sure the backend is running.`,
        variants: [],
      });
    }
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  window.addEventListener('keydown', (e) => {
    if (e.altKey && (e.key === 'd' || e.key === 'D')) {
      e.preventDefault();
      triggerDraftGeneration();
    }
    if (e.key === 'Escape') {
      closeCopilotModal();
    }
  });

  function init() {
    ensureFloatingPill();
    const observer = new MutationObserver(() => ensureFloatingPill());
    observer.observe(document.body, { childList: true, subtree: true });
  }

  // Expose internal helpers on window for extension messaging and testing
  window._talkingCopilot = {
    getActiveContactName,
    getLastIncomingMessage,
    insertTextIntoChat,
    triggerDraftGeneration,
    closeCopilotModal,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
