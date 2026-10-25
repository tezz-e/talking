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
      background: rgba(17, 19, 26, 0.94);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-top: 1px solid rgba(255, 255, 255, 0.18);
      box-shadow: 0 16px 48px rgba(0, 0, 0, 0.55), 0 0 0 1px rgba(255, 255, 255, 0.08);
      color: #f1f3f9;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      font-size: 13px;
      font-weight: 600;
      padding: 9px 16px;
      border-radius: 999px;
      cursor: pointer;
      user-select: none;
      transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1);
    }
    #talking-copilot-pill:hover {
      transform: translateY(-2px);
      border-color: #c4b5fd;
      box-shadow: 0 16px 44px rgba(196, 181, 253, 0.25);
    }
    #talking-copilot-pill .tk-kbd {
      font-size: 10px;
      font-family: monospace;
      background: rgba(255, 255, 255, 0.08);
      padding: 2px 6px;
      border-radius: 6px;
      color: #9ba1b5;
    }
    #talking-copilot-modal {
      position: fixed;
      bottom: 120px;
      right: 28px;
      width: 400px;
      max-width: calc(100vw - 40px);
      background: rgba(17, 19, 26, 0.94);
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-top: 1px solid rgba(255, 255, 255, 0.18);
      box-shadow: 0 24px 64px rgba(0, 0, 0, 0.65), 0 0 0 1px rgba(255, 255, 255, 0.18);
      border-radius: 24px;
      z-index: 1000000;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      color: #f1f3f9;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      animation: tkFadeSlide 0.26s cubic-bezier(0.16, 1, 0.3, 1);
    }
    @keyframes tkFadeSlide {
      from { opacity: 0; transform: translateY(16px) scale(0.96); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }
    .tk-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 18px;
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
      letter-spacing: -0.01em;
    }
    .tk-contact-tag {
      font-size: 11px;
      padding: 3px 9px;
      border-radius: 999px;
      background: rgba(196, 181, 253, 0.16);
      color: #c4b5fd;
      font-weight: 600;
      max-width: 150px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      border: 1px solid rgba(196, 181, 253, 0.25);
    }
    .tk-close-btn {
      background: transparent;
      border: none;
      color: #9ba1b5;
      font-size: 15px;
      cursor: pointer;
      padding: 4px 6px;
      line-height: 1;
      border-radius: 6px;
      transition: color 0.15s;
    }
    .tk-close-btn:hover { color: #fff; }
    .tk-body {
      padding: 16px 18px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .tk-incoming-snippet {
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 14px;
      padding: 10px 14px;
      font-size: 12px;
      color: #9ba1b5;
      max-height: 60px;
      overflow-y: auto;
      line-height: 1.45;
    }
    .tk-incoming-snippet strong { color: #f1f3f9; }
    .tk-variants-bar {
      display: flex;
      gap: 6px;
      background: rgba(255, 255, 255, 0.03);
      padding: 4px;
      border-radius: 999px;
      border: 1px solid rgba(255, 255, 255, 0.07);
    }
    .tk-variant-btn {
      flex: 1;
      background: transparent;
      border: 1px solid transparent;
      color: #9ba1b5;
      padding: 6px 6px;
      font-size: 11px;
      font-weight: 600;
      border-radius: 999px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 4px;
      transition: all 0.16s ease;
    }
    .tk-variant-btn:hover { background: rgba(255, 255, 255, 0.06); color: #fff; }
    .tk-variant-btn.tk-active {
      background: rgba(196, 181, 253, 0.18);
      border-color: rgba(196, 181, 253, 0.35);
      color: #fff;
      box-shadow: 0 2px 12px rgba(196, 181, 253, 0.18);
    }
    .tk-draft-textarea {
      width: 100%;
      background: rgba(11, 12, 17, 0.75);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-top: 1px solid rgba(255, 255, 255, 0.18);
      border-radius: 14px;
      color: #fff;
      font-size: 13px;
      line-height: 1.5;
      padding: 12px 14px;
      resize: vertical;
      min-height: 72px;
      box-sizing: border-box;
      outline: none;
      transition: border-color 0.18s, box-shadow 0.18s;
    }
    .tk-draft-textarea:focus {
      border-color: #c4b5fd;
      box-shadow: 0 0 18px rgba(196, 181, 253, 0.2);
    }
    .tk-variant-count-badge {
      font-size: 9px;
      padding: 1px 5px;
      background: rgba(255, 255, 255, 0.12);
      border-radius: 999px;
      color: #fff;
      margin-left: 2px;
      font-family: monospace;
    }
    .tk-bubbles-stack {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-bottom: 2px;
    }
    .tk-bubble-item {
      position: relative;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.09);
      border-top: 1px solid rgba(255, 255, 255, 0.16);
      border-radius: 16px 16px 16px 5px;
      padding: 8px 12px;
      font-size: 12.5px;
      color: #f1f3f9;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      cursor: pointer;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
      transition: all 0.18s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .tk-bubble-item:hover {
      background: rgba(196, 181, 253, 0.14);
      border-color: rgba(196, 181, 253, 0.35);
      transform: translateY(-1px);
      box-shadow: 0 6px 20px rgba(196, 181, 253, 0.15);
    }
    .tk-bubble-num {
      font-size: 10px;
      font-weight: 700;
      color: #c4b5fd;
      background: rgba(196, 181, 253, 0.14);
      padding: 1px 6px;
      border-radius: 4px;
      flex-shrink: 0;
      font-family: monospace;
    }
    .tk-bubble-text { flex: 1; word-break: break-word; }
    .tk-bubble-insert-icon { font-size: 11px; opacity: 0.5; transition: opacity 0.15s; }
    .tk-bubble-item:hover .tk-bubble-insert-icon { opacity: 1; color: #c4b5fd; }
    .tk-loading-indicator {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
      gap: 10px;
      color: #9ba1b5;
      font-size: 13px;
    }
    .tk-spinner {
      width: 16px;
      height: 16px;
      border: 2px solid rgba(255, 255, 255, 0.15);
      border-top-color: #c4b5fd;
      border-radius: 50%;
      animation: tkSpin 0.7s linear infinite;
    }
    @keyframes tkSpin { to { transform: rotate(360deg); } }
    .tk-footer {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 18px 16px;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      gap: 8px;
    }
    .tk-left-actions { display: flex; align-items: center; gap: 8px; }
    .tk-pro-toggle {
      display: flex;
      align-items: center;
      gap: 5px;
      font-size: 11.5px;
      color: #9ba1b5;
      cursor: pointer;
      user-select: none;
    }
    .tk-pro-toggle input { accent-color: #fda4af; cursor: pointer; }
    .tk-right-actions { display: flex; align-items: center; gap: 8px; }
    .tk-btn {
      font-size: 12px;
      font-weight: 600;
      padding: 8px 14px;
      border-radius: 999px;
      cursor: pointer;
      border: none;
      display: inline-flex;
      align-items: center;
      gap: 5px;
      transition: all 0.18s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .tk-btn-secondary {
      background: rgba(255, 255, 255, 0.05);
      color: #9ba1b5;
      border: 1px solid rgba(255, 255, 255, 0.09);
    }
    .tk-btn-secondary:hover { color: #fff; background: rgba(255, 255, 255, 0.09); }
    .tk-btn-primary {
      background: linear-gradient(135deg, #86efac, #6ee7b7);
      color: #0b0c11;
      font-weight: 700;
      box-shadow: 0 4px 18px rgba(134, 239, 172, 0.28);
    }
    .tk-btn-primary:hover {
      transform: translateY(-1px);
      box-shadow: 0 6px 24px rgba(134, 239, 172, 0.38);
    }
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
    pill.innerHTML = `<span class="tk-icon">✦</span> <span>Draft</span> <span class="tk-kbd">Alt+D</span>`;
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
          <span class="tk-icon">✦</span>
          <span class="tk-brand">Talking</span>
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
               <div class="tk-bubbles-stack" id="tk-bubbles-stack" style="display: none;"></div>
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
                   <span>Pro Mode</span>
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
    const bubblesStack = modal.querySelector('#tk-bubbles-stack');
    const proToggle = modal.querySelector('#tk-pro-toggle-cb');
    const regenBtn = modal.querySelector('#tk-regen-btn');
    const copyBtn = modal.querySelector('#tk-copy-btn');
    const insertBtn = modal.querySelector('#tk-insert-btn');

    activeContactId = data.contact_id;
    activeOriginalDraft = data.draft;
    activeVariants = data.variants || [];

    function renderBubbles(bubbles) {
      if (!bubblesStack) return;
      if (!bubbles || bubbles.length <= 1) {
        bubblesStack.innerHTML = '';
        bubblesStack.style.display = 'none';
        return;
      }
      bubblesStack.style.display = 'flex';
      bubblesStack.innerHTML = '';
      bubbles.forEach((bText, idx) => {
        const item = document.createElement('div');
        item.className = 'tk-bubble-item';
        item.title = 'Click to insert only this bubble';
        item.innerHTML = `
          <span class="tk-bubble-num">${idx + 1}</span>
          <span class="tk-bubble-text">${escapeHtml(bText)}</span>
          <span class="tk-bubble-insert-icon">↵</span>
        `;
        item.addEventListener('click', () => {
          insertTextIntoChat(bText);
          if (activeContactId) {
            fetch(`${BACKEND_BASE}/api/approve`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                contact_id: activeContactId,
                original_draft: activeOriginalDraft || bText,
                final_message: bText,
              }),
            }).catch(() => {});
          }
          closeCopilotModal();
        });
        bubblesStack.appendChild(item);
      });
    }

    if (variantsBar && activeVariants.length > 0) {
      const icons = { chill: '🧊', direct: '🎯', banter: '🔥' };
      variantsBar.innerHTML = '';
      activeVariants.forEach((v) => {
        const countBadge = v.bubbles && v.bubbles.length > 1
          ? `<span class="tk-variant-count-badge">${v.bubbles.length}</span>`
          : '';
        const btn = document.createElement('button');
        btn.className = `tk-variant-btn ${v.label === currentVariantLabel ? 'tk-active' : ''}`;
        btn.innerHTML = `<span>${icons[v.label] || '⚡'}</span> ${v.label.charAt(0).toUpperCase() + v.label.slice(1)}${countBadge}`;
        btn.addEventListener('click', () => {
          variantsBar.querySelectorAll('.tk-variant-btn').forEach((b) => b.classList.remove('tk-active'));
          btn.classList.add('tk-active');
          currentVariantLabel = v.label;
          draftTextarea.value = v.text;
          renderBubbles(v.bubbles);
        });
        variantsBar.appendChild(btn);
      });
    }

    draftTextarea.value = data.draft || '';
    const activeVar = activeVariants.find((v) => v.label === currentVariantLabel) || activeVariants[0];
    renderBubbles(data.bubbles || activeVar?.bubbles);

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
    let pillDebounceTimer = null;
    const observer = new MutationObserver(() => {
      if (pillDebounceTimer) clearTimeout(pillDebounceTimer);
      pillDebounceTimer = setTimeout(() => {
        ensureFloatingPill();
      }, 250);
    });
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
