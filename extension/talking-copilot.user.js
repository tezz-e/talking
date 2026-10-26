// ==UserScript==
// @name         Talking Copilot (WhatsApp Web & Instagram Direct)
// @namespace    https://github.com/maneeshk/talking
// @version      2.0.0
// @description  Proof Desk AI texting copilot for WhatsApp Web and Instagram Direct powered by local Talking autopilot
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
  let cachedApiToken = null;
  async function getApiHeaders() {
    if (!cachedApiToken) {
      try {
        const r = await fetch(`${BACKEND_BASE}/api/auth/token`);
        if (r.ok) {
          const data = await r.json();
          cachedApiToken = data.token;
        }
      } catch (e) {
        console.warn('[Talking Copilot] Failed to fetch auth token:', e);
      }
    }
    return {
      'Content-Type': 'application/json',
      ...(cachedApiToken ? { 'X-Talking-Token': cachedApiToken } : {}),
    };
  }

  let activeContactId = null;
  let activeOriginalDraft = null;
  let activeVariants = [];
  let currentVariantLabel = 'direct';
  let isProMode = false;
  try {
    isProMode = localStorage.getItem('talking_copilot_pro') === 'true';
  } catch {}

  // ── Shadow DOM Infrastructure ───────────────────────────────────────
  let shadowHost = null;
  let shadowRoot = null;

  const COPILOT_CSS = `
    /* ============================================================
       TALKING COPILOT — PROOF DESK IN-PAGE OVERLAY STYLES
       Isolated Shadow DOM Stylesheet for WhatsApp Web & Instagram
       ============================================================ */

    :host, :root {
      /* Light Mode (Paper substrate - default) */
      --tk-paper: #F2EFE8;
      --tk-bg: #F7F5F0;
      --tk-surface: #E8E4DC;
      --tk-surface-elevated: #EDE9E1;
      --tk-ink: #16140F;
      --tk-text: #16140F;
      --tk-text-muted: rgba(22, 20, 15, 0.62);
      --tk-text-faint: rgba(22, 20, 15, 0.38);
      --tk-hairline: rgba(22, 20, 15, 0.18);
      --tk-hairline-subtle: rgba(22, 20, 15, 0.10);
      --tk-hairline-strong: rgba(22, 20, 15, 0.32);
      --tk-grid: rgba(22, 20, 15, 0.06);
      --tk-accent: #FF4F1F;

      /* Liquid Glass Specular Bevels & Shadows */
      --tk-glass-specular: inset 0 1px 1px 0 rgba(255, 255, 255, 0.75), inset 0 -1px 1px 0 rgba(22, 20, 15, 0.06);
      --tk-glass-specular-active: inset 0 1px 2px 0 rgba(255, 255, 255, 0.95), inset 0 -1px 1px 0 rgba(22, 20, 15, 0.12);
      --tk-glass-shadow: 0 8px 30px rgba(22, 20, 15, 0.08), 0 2px 6px rgba(22, 20, 15, 0.04);
      --tk-glass-bg: rgba(247, 245, 240, 0.92);
      --tk-glass-surface: rgba(232, 228, 220, 0.85);

      /* Fluid Kinematics (Apple Fluid Interfaces & Wispr Flow rational curves) */
      --tk-spring-fluid: cubic-bezier(0.16, 1, 0.3, 1);
      --tk-spring-snappy: cubic-bezier(0.34, 1.45, 0.64, 1);
      --tk-spring-squish: cubic-bezier(0.2, 0.8, 0.2, 1);

      --tk-font-voice: "Newsreader", "Source Serif 4", Georgia, "Times New Roman", serif, "Apple Color Emoji", "Segoe UI Emoji";
      --tk-font-machine: "Geist Mono", "JetBrains Mono", ui-monospace, "SF Mono", Menlo, Consolas, monospace;
    }

    :host([data-theme="dark"]), [data-theme="dark"] {
      --tk-paper: #0F0E0B;
      --tk-bg: #13120D;
      --tk-surface: #17150F;
      --tk-surface-elevated: #1D1B13;
      --tk-ink: #ECE7DA;
      --tk-text: #ECE7DA;
      --tk-text-muted: rgba(236, 231, 218, 0.62);
      --tk-text-faint: rgba(236, 231, 218, 0.38);
      --tk-hairline: rgba(236, 231, 218, 0.18);
      --tk-hairline-subtle: rgba(236, 231, 218, 0.10);
      --tk-hairline-strong: rgba(236, 231, 218, 0.32);
      --tk-grid: rgba(236, 231, 218, 0.06);
      --tk-accent: #FF4F1F;

      /* Dark Liquid Glass Tokens */
      --tk-glass-specular: inset 0 1px 1px 0 rgba(255, 255, 255, 0.20), inset 0 -1px 1px 0 rgba(0, 0, 0, 0.45);
      --tk-glass-specular-active: inset 0 1px 2px 0 rgba(255, 255, 255, 0.35), inset 0 -1px 1px 0 rgba(0, 0, 0, 0.65);
      --tk-glass-shadow: 0 12px 36px rgba(0, 0, 0, 0.6), 0 2px 8px rgba(0, 0, 0, 0.35);
      --tk-glass-bg: rgba(19, 18, 13, 0.92);
      --tk-glass-surface: rgba(23, 21, 15, 0.85);
    }

    /* Box model resets & Craft Scrollbar */
    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      scrollbar-width: thin;
      scrollbar-color: var(--tk-hairline-strong) transparent;
    }

    ::-webkit-scrollbar {
      width: 5px;
      height: 5px;
    }

    ::-webkit-scrollbar-track {
      background: transparent;
    }

    ::-webkit-scrollbar-thumb {
      background: var(--tk-hairline-strong);
      border-radius: 3px;
      transition: background 160ms ease;
    }

    ::-webkit-scrollbar-thumb:hover {
      background: var(--tk-text-muted);
    }

    ::-webkit-scrollbar-thumb:active {
      background: var(--tk-accent);
    }

    /* Floating Launch Pill: 2px radius rectangle with mono TALK Alt+D and block caret */
    #talking-copilot-pill {
      position: fixed;
      bottom: 80px;
      right: 28px;
      z-index: 2147483647;
      display: flex;
      align-items: center;
      gap: 8px;
      background: var(--tk-glass-bg);
      backdrop-filter: blur(16px) saturate(180%);
      -webkit-backdrop-filter: blur(16px) saturate(180%);
      box-shadow: var(--tk-glass-specular), var(--tk-glass-shadow);
      border: 1px solid var(--tk-hairline-strong);
      border-radius: 2px;
      color: var(--tk-text);
      font-family: var(--tk-font-machine);
      font-size: 11px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      padding: 7px 12px;
      cursor: pointer;
      user-select: none;
      min-height: 32px;
      line-height: 1;
      transition: transform 180ms var(--tk-spring-snappy), background 160ms ease, border-color 160ms ease, box-shadow 180ms ease;
      transform-origin: center center;
    }

    #talking-copilot-pill:hover {
      background: var(--tk-glass-surface);
      border-color: var(--tk-accent);
      transform: translateY(-1px);
      box-shadow: var(--tk-glass-specular-active), var(--tk-glass-shadow);
    }

    /* Apple volume preservation squish on active click (delta V = 0) */
    #talking-copilot-pill:active {
      transform: scale(0.96, 1.04);
    }

    #talking-copilot-pill.tk-launching {
      animation: tkPillSquishLaunch 360ms var(--tk-spring-snappy);
    }

    @keyframes tkPillSquishLaunch {
      0% { transform: scale(1); }
      35% { transform: scale(0.94, 1.06); }
      70% { transform: scale(1.02, 0.98); }
      100% { transform: scale(1); }
    }

    .tk-brand-wordmark {
      font-family: var(--tk-font-voice);
      font-size: 14px;
      font-weight: 600;
      color: var(--tk-text);
      display: flex;
      align-items: center;
      gap: 3px;
      text-transform: lowercase;
    }

    .tk-block-caret {
      display: inline-block;
      width: 6px;
      height: 13px;
      background-color: var(--tk-accent);
      animation: tk-caret-blink 1s steps(1) infinite;
    }

    @keyframes tk-caret-blink {
      0%, 100% { opacity: 1; }
      50% { opacity: 0; }
    }

    @media (prefers-reduced-motion: reduce) {
      .tk-block-caret {
        animation: none;
        opacity: 1;
      }
    }

    .tk-pill-kbd {
      font-family: var(--tk-font-machine);
      font-size: 10px;
      color: var(--tk-text-muted);
      border-left: 1px solid var(--tk-hairline);
      padding-left: 8px;
    }

    /* Floating Modal: Editorial Proof Desk with Liquid Glass Optics & Apple Fluid Entrance */
    #talking-copilot-modal {
      position: fixed;
      bottom: 120px;
      right: 28px;
      width: 440px;
      max-width: calc(100vw - 40px);
      background: var(--tk-glass-bg);
      backdrop-filter: blur(20px) saturate(190%);
      -webkit-backdrop-filter: blur(20px) saturate(190%);
      box-shadow: var(--tk-glass-specular), var(--tk-glass-shadow);
      border: 1px solid var(--tk-hairline-strong);
      border-radius: 2px;
      z-index: 2147483647;
      color: var(--tk-text);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      transform-origin: bottom right;
      animation: tkFluidModalEntrance 280ms var(--tk-spring-fluid) forwards;
    }

    @keyframes tkFluidModalEntrance {
      0% {
        opacity: 0;
        transform: translateY(12px) scale(0.97);
      }
      100% {
        opacity: 1;
        transform: translateY(0) scale(1);
      }
    }

    @keyframes tkFluidModalExit {
      0% {
        opacity: 1;
        transform: translateY(0) scale(1);
      }
      100% {
        opacity: 0;
        transform: translateY(8px) scale(0.97);
      }
    }

    /* Registration marks on modal corners */
    #talking-copilot-modal::before {
      content: "⌜";
      position: absolute;
      top: 2px;
      left: 4px;
      font-family: var(--tk-font-machine);
      font-size: 10px;
      color: var(--tk-hairline-strong);
      line-height: 1;
      pointer-events: none;
    }

    #talking-copilot-modal::after {
      content: "⌟";
      position: absolute;
      bottom: 2px;
      right: 4px;
      font-family: var(--tk-font-machine);
      font-size: 10px;
      color: var(--tk-hairline-strong);
      line-height: 1;
      pointer-events: none;
    }

    /* Modal Header */
    .tk-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px 14px;
      background: var(--tk-surface);
      border-bottom: 1px solid var(--tk-hairline);
    }

    .tk-title-wrap {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .tk-brand {
      font-family: var(--tk-font-voice);
      font-size: 15px;
      font-weight: 600;
      color: var(--tk-text);
      display: flex;
      align-items: center;
      gap: 3px;
      text-transform: lowercase;
    }

    .tk-contact-tag {
      font-family: var(--tk-font-machine);
      font-size: 10px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      padding: 2px 6px;
      border: 1px solid var(--tk-hairline);
      border-radius: 2px;
      color: var(--tk-text-muted);
      max-width: 160px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .tk-close-btn {
      background: transparent;
      border: none;
      color: var(--tk-text-muted);
      font-family: var(--tk-font-machine);
      font-size: 13px;
      cursor: pointer;
      padding: 2px 4px;
      line-height: 1;
      min-height: auto;
    }

    .tk-close-btn:hover {
      color: var(--tk-accent);
    }

    /* Modal Body */
    .tk-body {
      padding: 12px 16px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      background-color: var(--tk-bg);
      /* 24px baseline grid */
      background-image: repeating-linear-gradient(
        to bottom,
        transparent 0px,
        transparent 23px,
        var(--tk-grid) 23px,
        var(--tk-grid) 24px
      );
      background-size: 100% 24px;
      background-position: top left;
    }

    .tk-incoming-snippet {
      font-family: var(--tk-font-voice);
      font-size: 13px;
      line-height: 20px;
      color: var(--tk-text-muted);
      border-left: 2px solid var(--tk-accent);
      padding: 2px 8px;
      background: var(--tk-surface);
      border-radius: 2px;
    }

    .tk-loading-indicator {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 18px 0;
      font-family: var(--tk-font-machine);
      font-size: 11px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--tk-text-muted);
      justify-content: center;
    }

    /* Takes / Tabs (A · CHILL [2], B · DIRECT, C · BANTER [2]) */
    .tk-variants-bar {
      display: flex;
      align-items: center;
      gap: 4px;
      border-bottom: 1px solid var(--tk-hairline-subtle);
      padding-bottom: 4px;
    }

    .tk-variant-btn {
      font-family: var(--tk-font-machine);
      font-size: 10px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      background: transparent;
      border: none;
      border-bottom: 2px solid transparent;
      padding: 4px 8px;
      color: var(--tk-text-muted);
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 4px;
      border-radius: 0;
      min-height: 26px;
      transition: color 150ms ease, border-color 200ms var(--tk-spring-snappy), transform 150ms var(--tk-spring-snappy);
    }

    .tk-variant-btn:hover {
      color: var(--tk-text);
      transform: translateY(-1px);
    }

    .tk-variant-btn:active {
      transform: scale(0.96);
    }

    .tk-variant-btn.tk-active {
      color: var(--tk-text);
      font-weight: 600;
      border-bottom: 2px solid var(--tk-accent);
    }

    .tk-variant-count-badge {
      font-family: var(--tk-font-machine);
      font-size: 9px;
      border: 1px solid var(--tk-hairline);
      padding: 0 3px;
      border-radius: 2px;
      color: var(--tk-text-muted);
    }

    .tk-variant-btn.tk-active .tk-variant-count-badge {
      border-color: var(--tk-accent);
      color: var(--tk-accent);
    }

    /* Multi-Bubble Bursts */
    .tk-bubbles-stack {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .tk-bubble-item {
      align-self: flex-end;
      max-width: 85%;
      border: 1px dashed var(--tk-accent);
      background: var(--tk-paper);
      color: var(--tk-text);
      box-shadow: var(--tk-glass-specular);
      border-radius: 14px 14px 2px 14px;
      padding: 6px 12px;
      font-family: var(--tk-font-voice);
      font-size: 14px;
      line-height: 22px;
      cursor: pointer;
      display: flex;
      align-items: baseline;
      gap: 8px;
      animation: tkBubbleBounceIn 280ms cubic-bezier(0.34, 1.56, 0.64, 1) backwards;
      transition: transform 200ms cubic-bezier(0.34, 1.56, 0.64, 1), border-color 140ms ease, box-shadow 160ms ease;
      transform-origin: bottom right;
    }

    @keyframes tkBubbleBounceIn {
      0% {
        opacity: 0;
        transform: translateY(12px) scale(0.9);
      }
      65% {
        opacity: 1;
        transform: translateY(-2px) scale(1.02);
      }
      100% {
        opacity: 1;
        transform: translateY(0) scale(1);
      }
    }

    .tk-bubble-item:hover {
      border-color: var(--tk-ink);
      transform: translateY(-2px) scale(1.02);
      box-shadow: var(--tk-glass-specular-active), 0 4px 12px rgba(0, 0, 0, 0.08);
    }

    .tk-bubble-item:active {
      transform: scale(0.96);
    }

    .tk-bubble-num {
      font-family: var(--tk-font-machine);
      font-size: 10px;
      color: var(--tk-accent);
      user-select: none;
    }

    .tk-bubble-text {
      font-family: var(--tk-font-voice);
      font-size: 14px;
      line-height: 22px;
    }

    .tk-bubble-insert-icon {
      font-family: var(--tk-font-machine);
      font-size: 11px;
      color: var(--tk-text-muted);
      margin-left: auto;
    }

    /* Editable Take Area */
    .tk-draft-textarea {
      width: 100%;
      min-height: 72px;
      background: transparent;
      border: 1px solid var(--tk-hairline);
      border-radius: 2px;
      padding: 8px 10px;
      font-family: var(--tk-font-voice);
      font-size: 14px;
      line-height: 22px;
      color: var(--tk-text);
      resize: vertical;
      outline: none;
    }

    .tk-draft-textarea:focus {
      border-color: var(--tk-accent);
    }

    /* Modal Footer */
    .tk-footer {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px 14px;
      background: var(--tk-surface);
      border-top: 1px solid var(--tk-hairline);
    }

    .tk-left-actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .tk-right-actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .tk-pro-toggle {
      display: flex;
      align-items: center;
      gap: 5px;
      font-family: var(--tk-font-machine);
      font-size: 10px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--tk-text-muted);
      cursor: pointer;
      user-select: none;
    }

    .tk-pro-toggle input {
      accent-color: var(--tk-accent);
    }

    .tk-btn {
      font-family: var(--tk-font-machine);
      font-size: 11px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      padding: 5px 12px;
      border-radius: 2px;
      border: 1px solid var(--tk-hairline);
      background: var(--tk-bg);
      box-shadow: var(--tk-glass-specular);
      color: var(--tk-text);
      cursor: pointer;
      min-height: 30px;
      transition: transform 140ms var(--tk-spring-snappy), background 140ms ease, border-color 140ms ease, box-shadow 140ms ease;
    }

    .tk-btn:hover {
      background: var(--tk-surface-elevated);
      border-color: var(--tk-hairline-strong);
      transform: translateY(-1px);
    }

    .tk-btn:active {
      transform: scale(0.97);
    }

    /* Primary Insert Button: Solid Ink with Specular Bevel */
    .tk-btn-primary {
      background: var(--tk-ink) !important;
      color: var(--tk-paper) !important;
      border: 1px solid var(--tk-ink) !important;
      box-shadow: inset 0 1px 1px 0 rgba(255, 255, 255, 0.25), 0 2px 8px rgba(0, 0, 0, 0.15) !important;
      font-weight: 600;
      transition: transform 140ms var(--tk-spring-snappy), opacity 140ms ease, box-shadow 140ms ease !important;
    }

    .tk-btn-primary:hover {
      opacity: 0.94;
      transform: translateY(-1px);
      box-shadow: inset 0 1px 1px 0 rgba(255, 255, 255, 0.35), 0 4px 12px rgba(0, 0, 0, 0.2) !important;
    }

    .tk-btn-primary:active {
      transform: scale(0.97);
    }
  `;

  function ensureShadowRoot() {
    if (!shadowHost) {
      shadowHost = document.getElementById('talking-copilot-host');
    }
    if (!shadowHost) {
      shadowHost = document.createElement('div');
      shadowHost.id = 'talking-copilot-host';
      shadowHost.style.display = 'contents';
      document.body.appendChild(shadowHost);
    }
    if (!shadowRoot) {
      shadowRoot = shadowHost.shadowRoot || shadowHost.attachShadow({ mode: 'open' });
    }

    const isDark = document.body.classList.contains('dark') || 
                   document.documentElement.classList.contains('dark') ||
                   window.matchMedia('(prefers-color-scheme: dark)').matches;
    shadowHost.setAttribute('data-theme', isDark ? 'dark' : 'light');

    if (!shadowRoot.querySelector('style#talking-copilot-styles')) {
      const styleEl = document.createElement('style');
      styleEl.id = 'talking-copilot-styles';
      styleEl.textContent = COPILOT_CSS;
      shadowRoot.appendChild(styleEl);
    }

    return shadowRoot;
  }

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
        document.querySelector('main header a span') ||
        document.querySelector('header span');
      return headerEl ? headerEl.textContent.trim() : 'Friend';
    }

    return 'Friend';
  }

  function getActiveReplyBarContext() {
    if (isWhatsApp()) {
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
    const activeReply = getActiveReplyBarContext();
    if (activeReply) return activeReply;

    if (isWhatsApp()) {
      const incomingNodes = document.querySelectorAll('div.message-in');
      if (incomingNodes.length === 0) return '';
      const last = incomingNodes[incomingNodes.length - 1];

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
    const root = ensureShadowRoot();
    if (root.getElementById('talking-copilot-pill')) return;

    const pill = document.createElement('div');
    pill.id = 'talking-copilot-pill';
    pill.innerHTML = `
      <span class="tk-brand-wordmark">talking<span class="tk-block-caret"></span></span>
      <span class="tk-pill-kbd">Alt+D</span>
    `;

    pill.addEventListener('click', () => {
      pill.classList.remove('tk-launching');
      void pill.offsetWidth;
      pill.classList.add('tk-launching');
      setTimeout(() => pill.classList.remove('tk-launching'), 400);
      triggerDraftGeneration();
    });

    root.appendChild(pill);
  }

  function closeCopilotModal() {
    const root = ensureShadowRoot();
    const existing = root.getElementById('talking-copilot-modal');
    if (existing) {
      existing.style.animation = 'tkFluidModalExit 180ms cubic-bezier(0.16, 1, 0.3, 1) forwards';
      setTimeout(() => {
        if (existing.parentNode) existing.remove();
      }, 160);
    }
  }

  function openCopilotModal(contactName, incomingText, isLoading = true, draftData = null) {
    closeCopilotModal();
    const root = ensureShadowRoot();

    const modal = document.createElement('div');
    modal.id = 'talking-copilot-modal';

    const safeContact = contactName || 'Friend';
    const safeSnippet = incomingText ? `"${incomingText.slice(0, 140)}${incomingText.length > 140 ? '...' : ''}"` : 'No incoming text detected';

    modal.innerHTML = `
      <div class="tk-header">
        <div class="tk-title-wrap">
          <span class="tk-brand">talking<span class="tk-block-caret"></span></span>
          <span class="tk-contact-tag">${escapeHtml(safeContact)}</span>
        </div>
        <button class="tk-close-btn" id="tk-close-modal">✕</button>
      </div>

      <div class="tk-body">
        <div class="tk-incoming-snippet">
          ${escapeHtml(safeSnippet)}
        </div>

        ${
          isLoading
            ? `
          <div class="tk-loading-indicator">
            <span>Proofing drafts on baseline grid...</span>
          </div>`
            : `
          <div class="tk-variants-bar" id="tk-variants-bar"></div>
          <div class="tk-bubbles-stack" id="tk-bubbles-stack" style="display: none;"></div>
          <textarea class="tk-draft-textarea" id="tk-draft-text" placeholder="Proof draft reply..."></textarea>
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
            <span>PRO</span>
          </label>
          <button class="tk-btn" id="tk-regen-btn" title="Regenerate">REGEN</button>
        </div>
        <div class="tk-right-actions">
          <button class="tk-btn" id="tk-copy-btn">COPY</button>
          <button class="tk-btn tk-btn-primary" id="tk-insert-btn">INSERT ↵</button>
        </div>
      </div>
      `
      }
    `;

    root.appendChild(modal);

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
        item.style.animationDelay = `${idx * 40}ms`;
        item.title = 'Click to insert only this bubble';
        item.innerHTML = `
          <span class="tk-bubble-num">0${idx + 1}</span>
          <span class="tk-bubble-text">${escapeHtml(bText)}</span>
          <span class="tk-bubble-insert-icon">↵</span>
        `;
        item.addEventListener('click', async () => {
          insertTextIntoChat(bText);
          if (activeContactId) {
            const hdrs = await getApiHeaders();
            fetch(`${BACKEND_BASE}/api/approve`, {
              method: 'POST',
              headers: hdrs,
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
      const letters = ['A', 'B', 'C', 'D'];
      variantsBar.innerHTML = '';
      activeVariants.forEach((v, idx) => {
        const letter = letters[idx] || String(idx + 1);
        const countBadge = v.bubbles && v.bubbles.length > 1
          ? `<span class="tk-variant-count-badge">[${v.bubbles.length}]</span>`
          : '';
        const btn = document.createElement('button');
        btn.className = `tk-variant-btn ${v.label === currentVariantLabel ? 'tk-active' : ''}`;
        btn.innerHTML = `<span>${letter} · ${escapeHtml(v.label.toUpperCase())}</span> ${countBadge}`;
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

    regenBtn?.addEventListener('click', () => {
      triggerDraftGeneration();
    });

    copyBtn?.addEventListener('click', () => {
      navigator.clipboard.writeText(draftTextarea.value);
      copyBtn.textContent = 'COPIED';
      setTimeout(() => (copyBtn.textContent = 'COPY'), 1500);
    });

    const doInsert = async () => {
      const finalMsg = draftTextarea.value.trim();
      if (!finalMsg) return;

      insertTextIntoChat(finalMsg);

      if (activeContactId) {
        const hdrs = await getApiHeaders();
        fetch(`${BACKEND_BASE}/api/approve`, {
          method: 'POST',
          headers: hdrs,
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
      const hdrs = await getApiHeaders();
      const res = await fetch(`${BACKEND_BASE}/api/copilot/draft`, {
        method: 'POST',
        headers: hdrs,
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
      const root = ensureShadowRoot();
      const pill = root.getElementById('talking-copilot-pill');
      if (pill) {
        pill.classList.remove('tk-launching');
        void pill.offsetWidth;
        pill.classList.add('tk-launching');
        setTimeout(() => pill.classList.remove('tk-launching'), 400);
      }
      triggerDraftGeneration();
      return;
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

  window._talkingCopilot = {
    getActiveContactName,
    getLastIncomingMessage,
    insertTextIntoChat,
    triggerDraftGeneration,
    closeCopilotModal,
    openCopilotModal,
    getShadowRoot: () => ensureShadowRoot(),
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
