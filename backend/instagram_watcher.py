"""
Instagram DM Watcher
====================
Monitors a single Instagram conversation for new incoming messages.
Uses a persistent browser session (you log in once, session is saved).
Posts new messages to the Talking backend, which generates AI replies.
"""

import asyncio
import json
import logging
import os
import random
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger("ig_watcher")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [IG] %(message)s")

# ─── Config ──────────────────────────────────────────────────────────────────
SESSION_DIR = Path(__file__).parent.parent / "data" / "ig_session"
BACKEND_URL = "http://localhost:8000"
POLL_MIN = 2.0  # seconds (snappy local DOM inspection)
POLL_MAX = 3.8  # seconds
IG_BASE = "https://www.instagram.com"

async def dismiss_popups(page):
    """Dismiss common Instagram popups like 'Turn on Notifications' or 'Save Info'."""
    popup_buttons = [
        'button:has-text("Not Now")',
        'button:has-text("Not now")',
        'button:has-text("Cancel")',
        'button:has-text("Close")',
        'button:has-text("Decline optional cookies")',
    ]
    for sel in popup_buttons:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                await asyncio.sleep(0.3)
                logger.info(f"Dismissed Instagram popup: {sel}")
        except Exception:
            pass

def _auth_headers() -> dict[str, str]:
    token = os.getenv("TALKING_API_TOKEN", "")
    if not token:
        try:
            from backend.main import SERVER_API_TOKEN
            token = SERVER_API_TOKEN
        except Exception:
            token = ""
    return {"X-Talking-Token": token} if token else {}

# ─── Shared state (read by backend API endpoints) ─────────────────────────────
_state = {
    "running": False,
    "contact_id": None,
    "ig_username": None,
    "full_auto": False,
    "last_message": None,
    "last_sent": None,
    "pending_reply": None,
    "error": None,
    "status_text": "Idle",
    "history_synced_at": 0,
}

# Global reference to the playwright page for sending messages
_page_ref = None
_loop_ref = None


def get_state() -> dict:
    return dict(_state)


def stop_watcher():
    _state["running"] = False
    _state["status_text"] = "Stopping..."


# ─── Login / Session ──────────────────────────────────────────────────────────
async def ensure_logged_in(page, context) -> bool:
    cookie_file = SESSION_DIR / "cookies.json"
    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    # Restore saved cookies if they exist
    if cookie_file.exists():
        try:
            cookies = json.loads(cookie_file.read_text())
            await context.add_cookies(cookies)
            logger.info("Restored saved Instagram session cookies.")
        except Exception:
            pass

    # Navigate to Instagram home first (less suspicious than going straight to DMs)
    await page.goto(IG_BASE, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(2)
    await dismiss_popups(page)

    # Check if actually logged in by looking for UI elements, not just URL
    def _is_login_page():
        url = page.url
        return "login" in url or "accounts/login" in url

    async def _is_logged_in():
        """Returns True if key logged-in UI elements are present."""
        try:
            # Look for the nav bar elements that only appear when logged in
            logged_in_selectors = [
                'a[href="/direct/inbox/"]',     # DM icon in nav
                'svg[aria-label="Home"]',         # Home icon
                '[aria-label="New post"]',
                'a[href*="/direct/"]',
            ]
            for sel in logged_in_selectors:
                el = await page.query_selector(sel)
                if el:
                    return True
            return False
        except Exception:
            return False

    # If already logged in, save fresh cookies and return
    if await _is_logged_in():
        logger.info("Already logged in.")
        cookies = await context.cookies()
        cookie_file.write_text(json.dumps(cookies))
        _state["status_text"] = "Logged in ✓"
        return True

    # Not logged in — go to login page and wait for user
    if not _is_login_page():
        await page.goto(f"{IG_BASE}/accounts/login/", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)

    _state["status_text"] = "⏳ Waiting for login — log in to Instagram in the browser"
    logger.info("=" * 60)
    logger.info("WAITING FOR MANUAL LOGIN")
    logger.info("Please log into Instagram in the browser window.")
    logger.info("The watcher will continue automatically once you're in.")
    logger.info("=" * 60)

    # Wait up to 3 minutes, checking every second
    for i in range(180):
        await asyncio.sleep(1)
        if await _is_logged_in():
            logger.info("Login detected! Continuing...")
            break
    else:
        _state["error"] = "Login timeout — took more than 3 minutes."
        _state["status_text"] = "Error: login timeout"
        return False

    # Save session for next time
    cookies = await context.cookies()
    cookie_file.write_text(json.dumps(cookies))
    logger.info("Session saved for future use.")
    _state["status_text"] = "Logged in ✓"
    return True

# ─── Navigation ───────────────────────────────────────────────────────────────
async def go_to_conversation(page, target: str) -> bool:
    """
    Navigate directly to a DM thread.
    target should be the full thread URL or just the numeric thread ID.
    """
    try:
        logger.info(f"go_to_conversation called with target='{target}'")

        # Build the thread URL
        if target.startswith("https://www.instagram.com/direct/t/"):
            thread_url = target
        elif target.startswith("https://"):
            thread_url = target  # some other IG URL, try anyway
        elif target.isdigit():
            thread_url = f"{IG_BASE}/direct/t/{target}/"
        elif "direct/t/" in target:
            # partial path like "direct/t/123456789/"
            thread_url = f"{IG_BASE}/{target.lstrip('/')}"
        else:
            # Treat as @username — build direct inbox URL by going to profile
            # then navigating to the full thread page (NOT clicking Message popup)
            logger.warning(f"No thread URL given. Got username '{target}'. "
                           f"For best results paste the full thread URL.")
            # Still try: go to inbox and look for the thread
            await page.goto(f"{IG_BASE}/direct/inbox/", wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(2)
            # Find thread link by name in sidebar
            link = page.locator(f'a[href*="/direct/t/"]').first
            if await link.count() > 0:
                href = await link.get_attribute("href")
                thread_url = f"{IG_BASE}{href}"
                logger.info(f"Found thread link in inbox: {thread_url}")
            else:
                _state["error"] = "Please paste the full thread URL (instagram.com/direct/t/...)"
                _state["status_text"] = "Error: need thread URL"
                return False

        logger.info(f"Navigating to: {thread_url}")
        _state["status_text"] = "Opening DM thread..."
        await page.goto(thread_url, wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(random.uniform(1.5, 2.5))
        await dismiss_popups(page)
        try:
            await page.wait_for_selector('div[role="main"]', timeout=8000)
        except Exception:
            pass
        await dismiss_popups(page)

        # Verify we landed on the right page
        current = page.url
        if "direct/t/" in current:
            logger.info(f"✅ On DM thread: {current}")
            _state["status_text"] = "Watching conversation"
            return True
        else:
            logger.warning(f"Expected DM thread but landed on: {current}")
            # Could be a redirect — still try
            _state["status_text"] = "Watching conversation"
            return True

    except Exception as e:
        _state["error"] = f"Navigation error: {e}"
        _state["status_text"] = "Error: navigation failed"
        logger.error(_state["error"])
        return False



# ─── Message Reading ──────────────────────────────────────────────────────────
async def get_latest_incoming(page) -> list[str]:
    """
    Returns the block of recent incoming messages on screen.
    Uses JS evaluation to inspect all message rows and classify by alignment.
    """
    try:
        result = await page.evaluate("""
            () => {
                const main = document.querySelector('div[role="main"]') || document.querySelector('main') || document.body;
                const allDivs = Array.from(main.querySelectorAll('div[dir="auto"]'));
                let currentBlock = [];

                for (const el of allDivs) {
                    if (el.closest('header') || el.closest('nav') || el.closest('form') || el.closest('footer')) continue;
                    const text = el.innerText ? el.innerText.trim() : '';
                    if (!text || text.length < 1 || text.length > 2000) continue;
                    const childDivs = el.querySelectorAll('div[dir="auto"]');
                    if (childDivs.length > 0) continue;

                    const rect = el.getBoundingClientRect();
                    if (rect.width < 10 || rect.height < 10) continue;
                    if (rect.top < 70 || rect.bottom > window.innerHeight - 50) continue;
                    if (window.innerWidth > 768 && rect.left < 320) continue;

                    let isThem = false;
                    let isYou = false;

                    let curr = el;
                    while (curr && curr !== main) {
                        const align = window.getComputedStyle(curr).alignSelf;
                        if (align === 'flex-end') { isYou = true; break; }
                        if (align === 'flex-start') { isThem = true; break; }
                        curr = curr.parentElement;
                    }

                    if (!isThem && !isYou) {
                        let parent = el.parentElement;
                        let rowRect = null;
                        while (parent && parent !== main) {
                            const pRect = parent.getBoundingClientRect();
                            if (pRect.width >= 250 && pRect.width > rect.width * 1.15) {
                                rowRect = pRect;
                                break;
                            }
                            parent = parent.parentElement;
                        }
                        if (!rowRect) rowRect = main.getBoundingClientRect();

                        const leftDist = Math.abs(rect.left - rowRect.left);
                        const rightDist = Math.abs(rowRect.right - rect.right);

                        if (leftDist < rightDist * 0.85) {
                            isThem = true;
                        } else if (rightDist < leftDist * 0.85) {
                            isYou = true;
                        }
                    }

                    if (isThem) {
                        currentBlock.push(text);
                    } else if (isYou) {
                        currentBlock = [];
                    }
                }
                return currentBlock;
            }
        """)
        return result
    except Exception as e:
        logger.debug(f"get_latest_incoming error: {e}")
        return None

async def get_recent_history(page, limit: int = 15) -> list[dict]:
    """
    Returns a list of the most recent messages on screen.
    Format: [{"role": "them"|"me", "content": "..."}]
    """
    try:
        messages = await page.evaluate(r"""
            (limit) => {
                const main = document.querySelector('div[role="main"]') || document.querySelector('main') || document.body;
                let results = [];

                // --- Pass 1: Text Messages ---
                const allDivs = Array.from(main.querySelectorAll('div[dir="auto"]'));
                const headerEl = main.querySelector('header') || document.querySelector('header');
                const headerBottom = headerEl ? headerEl.getBoundingClientRect().bottom : 50;

                for (const el of allDivs) {
                    if (el.closest('header') || el.closest('nav') || el.closest('form') || el.closest('footer')) continue;
                    // Skip if inside or part of a Reel / Post card or link
                    if (
                        el.closest('a[href*="/reel/"], a[href*="/reels/"], a[href*="/p/"]') || 
                        el.closest('[data-talking-reel-tagged]')
                    ) continue;
                    
                    const parentCard = el.closest('div[role="row"], div[role="none"], div[style*="flex"]') || el.parentElement;
                    if (parentCard && parentCard.querySelector('a[href*="/reel/"], a[href*="/reels/"], a[href*="/p/"]')) continue;
                    // Skip container divs that have child div[dir="auto"] elements (process only leaf text nodes)
                    if (el.querySelector('div[dir="auto"]')) continue;

                    const text = el.innerText ? el.innerText.trim() : '';
                    if (!text || text.length < 1 || text.length > 2000) continue;

                    // Skip delivery status receipts
                    if (/^(seen(\s+\d+.*|\s+just\s+now)?|sent|delivered)$/i.test(text)) continue;

                    // Skip timestamp headers (e.g. 1:20 AM, Yesterday 4:30 PM, Today, etc.)
                    if (/^(\d{1,2}:\d{2}\s*(?:am|pm)?|(yesterday|today|sunday|monday|tuesday|wednesday|thursday|friday|saturday)(\s+\d{1,2}:\d{2}\s*(?:am|pm)?)?|[a-z]{3}\s+\d{1,2}(,\s+\d{4})?(\s+\d{1,2}:\d{2}\s*(?:am|pm)?)?)$/i.test(text)) continue;

                    // Skip active indicators
                    if (/^active\s+.*$/i.test(text)) continue;

                    const rect = el.getBoundingClientRect();
                    if (rect.width < 10 || rect.height < 10) continue;
                    if (rect.bottom <= headerBottom || rect.top > window.innerHeight - 50) continue;
                    if (window.innerWidth > 768 && rect.left < 320) continue;

                    let role = null;
                    
                    // Fallback 1: CSS flex alignment
                    let curr = el;
                    while (curr && curr !== main) {
                        const align = window.getComputedStyle(curr).alignSelf;
                        if (align === 'flex-end') { role = 'you'; break; }
                        if (align === 'flex-start') { role = 'them'; break; }
                        curr = curr.parentElement;
                    }

                    // Fallback 2: Bounding box left/right math
                    if (!role) {
                        let parent = el.parentElement;
                        let rowRect = null;
                        while (parent && parent !== main) {
                            const pRect = parent.getBoundingClientRect();
                            if (pRect.width >= 250 && pRect.width > rect.width * 1.15) {
                                rowRect = pRect;
                                break;
                            }
                            parent = parent.parentElement;
                        }
                        if (!rowRect) rowRect = main.getBoundingClientRect();
                        const leftDist = Math.abs(rect.left - rowRect.left);
                        const rightDist = Math.abs(rowRect.right - rect.right);
                        if (leftDist < rightDist * 0.85) role = 'them';
                        else if (rightDist < leftDist * 0.85) role = 'you';
                        else role = 'them'; // default fallback
                    }
                    results.push({role, content: text, y_pos: rect.top, is_media: false});
                }
                
                // --- Pass 2: Media Elements ---
                const mediaElements = Array.from(main.querySelectorAll('img, video, a[href*="/reel/"], a[href*="/p/"]'));
                for (const el of mediaElements) {
                    if (el.closest('header') || el.closest('nav') || el.closest('form') || el.closest('footer')) continue;

                    const rect = el.getBoundingClientRect();
                    if (rect.width < 40 || rect.height < 40) continue;
                    if (rect.top < 70 || rect.bottom > window.innerHeight - 50) continue;
                    if (window.innerWidth > 768 && rect.left < 320) continue;

                    const alt = (el.getAttribute('alt') || '').toLowerCase();
                    const src = (el.getAttribute('src') || '').toLowerCase();
                    const ariaLabel = (el.getAttribute('aria-label') || '').toLowerCase();

                    // Strictly reject any avatar or profile picture
                    if (
                        alt.includes('profile picture') || 
                        alt.includes('profile photo') || 
                        alt.includes('user-profile-picture') || 
                        alt.includes('avatar') || 
                        ariaLabel.includes('profile picture') ||
                        ariaLabel.includes('profile photo') ||
                        src.includes('/profiles/') || 
                        src.includes('profile_pic') ||
                        src.includes('s150x150') ||
                        src.includes('s320x320')
                    ) {
                        continue;
                    }

                    // Reject circular avatar thumbnails
                    const style = window.getComputedStyle(el);
                    if ((style.borderRadius === '50%' || parseInt(style.borderRadius) >= 25) && (rect.width <= 75 || rect.height <= 75)) {
                        continue;
                    }

                    let role = null;
                    let curr = el;
                    while (curr && curr !== main) {
                        const align = window.getComputedStyle(curr).alignSelf;
                        if (align === 'flex-end') { role = 'you'; break; }
                        if (align === 'flex-start') { role = 'them'; break; }
                        curr = curr.parentElement;
                    }
                    
                    if (!role) {
                        let parent = el.parentElement;
                        let rowRect = null;
                        while (parent && parent !== main) {
                            const pRect = parent.getBoundingClientRect();
                            if (pRect.width >= 250 && pRect.width > rect.width * 1.15) {
                                rowRect = pRect;
                                break;
                            }
                            parent = parent.parentElement;
                        }
                        if (!rowRect) rowRect = main.getBoundingClientRect();
                        const leftDist = Math.abs(rect.left - rowRect.left);
                        const rightDist = Math.abs(rowRect.right - rect.right);
                        if (leftDist < rightDist * 0.85) role = 'them';
                        else if (rightDist < leftDist * 0.85) role = 'you';
                        else role = 'them';
                    }

                    // Check if this img is an emoji character rendered by host
                    const rawAlt = el.getAttribute('alt') || '';
                    const isEmojiAlt = rawAlt && /^(\p{Extended_Pictographic}|\p{Emoji_Presentation}|\p{Emoji_Modifier_Base}|\p{Emoji_Component}|\u200D|\uFE0F|\s)+$/u.test(rawAlt.trim());
                    if (isEmojiAlt) {
                        results.push({
                            role: role,
                            content: rawAlt.trim(),
                            is_media: false,
                            y_pos: rect.top
                        });
                        continue;
                    }

                    // Check if this is a reel / post link or media inside a reel / post card
                    let reelLink = el.closest('a[href*="/reel/"], a[href*="/reels/"], a[href*="/p/"]');
                    const rowBox = el.closest('div[role="row"], div[role="none"], div[style*="flex"], div[dir="auto"]') || el.parentElement;

                    if (!reelLink && rowBox) {
                        reelLink = rowBox.querySelector('a[href*="/reel/"], a[href*="/reels/"], a[href*="/p/"]');
                    }

                    if (!reelLink) {
                        let p = el.parentElement;
                        let depth = 0;
                        while (p && p !== main && depth < 5) {
                            const found = p.querySelector('a[href*="/reel/"], a[href*="/reels/"], a[href*="/p/"]');
                            if (found) {
                                reelLink = found;
                                break;
                            }
                            p = p.parentElement;
                            depth++;
                        }
                    }

                    // Check if image URL or card text indicates a Reel
                    const isClipsMedia = src.includes('clips') || src.includes('reel') || (src.includes('efg=') && (src.includes('CLIPS') || decodeURIComponent(src).includes('CLIPS')));
                    const cardText = rowBox ? (rowBox.innerText || '') : '';
                    const hasReelKeywords = cardText.includes('Watch on Instagram') || cardText.includes('Watch full reel') || cardText.includes('Reel by');
                    const isReel = Boolean(reelLink || isClipsMedia || hasReelKeywords);

                    // Prevent double-counting reel components (anchor + thumbnail)
                    if (isReel) {
                        const tagContainer = rowBox || reelLink || el;
                        if (tagContainer.hasAttribute('data-talking-reel-tagged')) continue;
                        tagContainer.setAttribute('data-talking-reel-tagged', 'true');
                    }

                    if (!el.hasAttribute('data-talking-media-id')) {
                        el.setAttribute('data-talking-media-id', 'media_' + Math.random().toString(36).substr(2, 9));
                    }
                    const selector = `[data-talking-media-id="${el.getAttribute('data-talking-media-id')}"]`;

                    let mediaType = '[Sent a photo]';
                    const isSticker = alt.includes('sticker') || ariaLabel.includes('sticker') || src.includes('sticker') || src.includes('stickers');
                    const isGif = alt.includes('gif') || ariaLabel.includes('gif') || src.includes('giphy');

                    const cleanAlt = (rawAlt && !rawAlt.toLowerCase().includes('photo') && !rawAlt.toLowerCase().includes('image')) ? rawAlt : '';

                    if (isReel) {
                        const href = reelLink ? reelLink.href : '';
                        mediaType = href ? `[Shared Instagram Reel: ${href}${cleanAlt ? ' | ' + cleanAlt : ''}]` : `[Shared Instagram Reel${cleanAlt ? ': ' + cleanAlt : ''}]`;
                    } else if (el.tagName.toLowerCase() === 'a' && el.href) {
                        const href = el.href;
                        const isPost = href.includes('/p/');
                        mediaType = `[Shared ${isPost ? 'Post' : 'Link'}: ${href}]`;
                    } else if (el.tagName.toLowerCase() === 'video') {
                        mediaType = '[Sent a reel/video]';
                    } else if (isGif) {
                        mediaType = '[Sent a GIF]';
                    } else if (isSticker) {
                        const stickerAlt = (rawAlt && !rawAlt.toLowerCase().includes('sticker')) ? rawAlt : '';
                        mediaType = stickerAlt ? `[Sent a sticker: ${stickerAlt}]` : '[Sent a sticker]';
                    } else if (alt && !alt.includes('photo') && !alt.includes('image')) {
                        mediaType = `[Sent a photo: ${el.getAttribute('alt')}]`;
                    }
                    
                    results.push({
                        role: role, 
                        content: mediaType, 
                        is_media: true, 
                        is_reel: isReel,
                        reel_url: reelLink ? reelLink.href : '',
                        media_url: el.src || (reelLink ? (reelLink.querySelector('img')?.src || '') : ''),
                        element_selector: selector,
                        y_pos: rect.top 
                    });
                }

                // Sort by vertical position (DOM order)
                results.sort((a, b) => a.y_pos - b.y_pos);
                
                // Deduplicate identical consecutive texts (mostly for nested text divs)
                let deduped = [];
                for (let r of results) {
                    if (deduped.length > 0 && !r.is_media && deduped[deduped.length - 1].content === r.content) continue;
                    if (deduped.length > 0 && r.is_media && deduped[deduped.length - 1].content === r.content && Math.abs(deduped[deduped.length - 1].y_pos - r.y_pos) < 25) continue;
                    deduped.push(r);
                }
                return deduped.slice(-limit);
            }
        """, limit)
        return messages or []
    except Exception as e:
        logger.error(f"get_recent_history error: {e}")
        return []


import base64

async def describe_media_async(page, contact_id: str, media_type: str, selector: str):
    """Takes a screenshot of the media element and sends it to the backend for description."""
    try:
        # Give it a second to load
        await asyncio.sleep(1)
        el = page.locator(selector)
        count = await el.count()
        if count == 0:
            logger.warning(f"Media element {selector} not found for screenshot.")
            return

        screenshot_bytes = await el.first.screenshot(type='jpeg', quality=80)
        image_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
        
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{BACKEND_URL}/api/instagram/describe_media",
                json={
                    "contact_id": contact_id,
                    "media_type": media_type,
                    "image_base64": image_b64,
                },
                headers=_auth_headers(),
            )
            if resp.status_code == 200:
                logger.info(f"📸 Media described: {resp.json().get('description')}")
            else:
                logger.warning(f"Failed to describe media: {resp.text}")
    except Exception as e:
        logger.error(f"Error describing media: {e}")

# ─── Send ─────────────────────────────────────────────────────────────────────
async def send_on_page(page, text: str) -> bool:
    """Type and send a message in the currently open DM."""
    if not text or not text.strip():
        return False

    try:
        await dismiss_popups(page)

        selectors = [
            'div[role="main"] div[contenteditable="true"][role="textbox"]',
            'div[role="main"] div[aria-label*="Message"][contenteditable="true"]',
            'div[role="main"] div[contenteditable="true"]',
            'div[contenteditable="true"][role="textbox"]',
            'div[aria-label*="Message"][contenteditable="true"]',
            'textarea[placeholder*="Message"]',
        ]
        input_box = None
        for sel in selectors:
            candidate = await page.query_selector(sel)
            if candidate and await candidate.is_visible():
                input_box = candidate
                break

        if not input_box:
            logger.error("Could not find DM input box.")
            return False

        # Support multi-bubble burst if text contains double-newlines
        raw_bubbles = [b.strip() for b in text.split("\n\n") if b.strip()]
        bubbles = raw_bubbles if raw_bubbles else [text.strip()]

        for idx, bubble in enumerate(bubbles):
            await dismiss_popups(page)
            await input_box.scroll_into_view_if_needed()
            await input_box.click()
            await asyncio.sleep(random.uniform(0.2, 0.4))

            # Type the bubble with human jitter, using insert_text for emojis/multibyte
            for char in bubble:
                try:
                    if ord(char) < 128:
                        await page.keyboard.type(char, delay=random.randint(25, 65))
                    else:
                        await page.keyboard.insert_text(char)
                        await asyncio.sleep(random.uniform(0.02, 0.05))
                except Exception:
                    await page.keyboard.insert_text(char)

            await asyncio.sleep(random.uniform(0.3, 0.5))
            await page.keyboard.press("Enter")
            await asyncio.sleep(random.uniform(0.5, 0.9))

            # Send button fallback if Enter did not submit
            send_btn_selectors = [
                'div[role="main"] div[role="button"]:has-text("Send")',
                'div[role="main"] button:has-text("Send")',
                'div[role="button"]:has-text("Send")',
                'button:has-text("Send")',
                'div[role="button"][tabindex="0"]:has-text("Send")',
            ]
            for btn_sel in send_btn_selectors:
                try:
                    btn = await page.query_selector(btn_sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        logger.info(f"Clicked Send button ({btn_sel})")
                        await asyncio.sleep(0.4)
                        break
                except Exception:
                    pass

            if idx < len(bubbles) - 1:
                burst_pause = random.uniform(1.2, 2.0)
                logger.info(f"Burst pause: {burst_pause:.1f}s before sending next bubble...")
                await asyncio.sleep(burst_pause)

        # Verify sent message appeared in DOM
        def norm(s): return ''.join(e for e in s.lower() if e.isalnum())
        norm_text = norm(text)

        for attempt in range(5):
            await asyncio.sleep(0.8)
            verify_msgs = await get_recent_history(page, limit=6)
            if not verify_msgs:
                continue

            success = False
            for m in verify_msgs:
                if m.get("role") == "you":
                    norm_dom = norm(m.get("content", ""))
                    if norm_dom and (norm_dom in norm_text or norm_text in norm_dom):
                        success = True
                        break

            if success:
                logger.info(f"✅ Sent and verified: {text[:60]}...")
                return True

        logger.warning("Send completed; DOM verification timed out (assuming sent).")
        return True

    except Exception as e:
        logger.error(f"Send failed: {e}")
        return False


# ─── Main Poll Loop ───────────────────────────────────────────────────────────
async def _watch_loop(contact_id: str, their_ig_username: str, mood: str, full_auto: bool = False):
    global _page_ref
    try:
        from playwright.async_api import async_playwright
        import difflib
    except ImportError as e:
        _state["error"] = f"Dependency missing: {e}"
        _state["status_text"] = "Error: dependency missing"
        return

    async with async_playwright() as pw:
        launch_kwargs = {
            "user_data_dir": str(SESSION_DIR / "chrome_data"),
            "headless": False,
            "viewport": {"width": 1280, "height": 900},
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        try:
            ctx = await pw.chromium.launch_persistent_context(channel="chrome", **launch_kwargs)
        except Exception:
            ctx = await pw.chromium.launch_persistent_context(**launch_kwargs)

        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        _page_ref = page
        try:
            await page.bring_to_front()
        except Exception:
            pass

        if not await ensure_logged_in(page, ctx):
            await ctx.close()
            return

        # Brief pause after login — let Instagram fully settle before navigating
        logger.info("Login verified. Navigating to conversation in 3 seconds...")
        _state["status_text"] = "Login verified — opening conversation..."
        await asyncio.sleep(3)

        if not await go_to_conversation(page, their_ig_username):
            await ctx.close()
            return

        _state["status_text"] = "Watching conversation"

        # Sync recent history once at startup
        logger.info("Syncing recent history from screen...")
        _state["status_text"] = "Syncing recent history..."
        recent_msgs = await get_recent_history(page, limit=20)
        if recent_msgs:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(
                        f"{BACKEND_URL}/api/instagram/sync_history",
                        json={
                            "contact_id": contact_id,
                            "messages": recent_msgs,
                        },
                        headers=_auth_headers(),
                    )
                import time
                _state["history_synced_at"] = time.time()
                logger.info(f"Synced {len(recent_msgs)} history messages.")
            except Exception as e:
                logger.warning(f"Failed to sync history to backend: {e}")

        _state["status_text"] = "Watching conversation"

        # Track seen messages as an ordered list of message dicts
        last_seen_history = list(recent_msgs) if recent_msgs else []

        consecutive_errors = 0
        poll_count = 0
        while _state["running"]:
            try:
                await dismiss_popups(page)
                recent_msgs = await get_recent_history(page, limit=20)
                consecutive_errors = 0
                poll_count += 1

                if poll_count % 5 == 0:
                    tail_summary = [f"{m.get('role')}: {m.get('content')[:30]}" for m in (recent_msgs or [])[-3:]]
                    logger.info(f"Poll #{poll_count} — {len(recent_msgs or [])} msgs in DOM. Tail: {tail_summary}")

                if recent_msgs:
                    last_sigs = [(m.get("role", ""), m.get("content", "").strip()) for m in last_seen_history]
                    curr_sigs = [(m.get("role", ""), m.get("content", "").strip()) for m in recent_msgs]

                    sm = difflib.SequenceMatcher(None, last_sigs, curr_sigs)
                    new_msgs = []
                    unsent_detected = False

                    for tag, i1, i2, j1, j2 in sm.get_opcodes():
                        if tag in ('insert', 'replace'):
                            new_msgs.extend(recent_msgs[j1:j2])
                        if tag in ('delete', 'replace'):
                            # Messages removed from DOM
                            deleted_items = last_seen_history[i1:i2]
                            for d_item in deleted_items:
                                if d_item.get("role") == "them":
                                    unsent_detected = True
                                    logger.warning(f"⚠️ Detected UNSENT message from contact: {d_item.get('content', '')[:60]}")
                                    try:
                                        async with httpx.AsyncClient(timeout=5) as client:
                                            await client.post(
                                                f"{BACKEND_URL}/api/instagram/unsend",
                                                json={
                                                    "contact_id": contact_id,
                                                    "content": d_item.get("content", ""),
                                                },
                                                headers=_auth_headers(),
                                            )
                                    except Exception as e:
                                        logger.warning(f"Failed to notify backend of unsend: {e}")

                    if unsent_detected:
                        # Abort any pending reply that was triggered by the unsent message
                        if _state.get("pending_reply"):
                            logger.info("🚫 Aborting pending reply because contact unsent message.")
                            _state["pending_reply"] = None
                        _state["status_text"] = "Contact unsent a message"

                    # Update last seen state to current
                    last_seen_history = list(recent_msgs)

                    if new_msgs:
                        # Sync new messages to backend DB
                        try:
                            async with httpx.AsyncClient(timeout=10) as client:
                                await client.post(
                                    f"{BACKEND_URL}/api/instagram/sync_history",
                                    json={
                                        "contact_id": contact_id,
                                        "messages": new_msgs,
                                    },
                                    headers=_auth_headers(),
                                )
                            import time
                            _state["history_synced_at"] = time.time()
                        except Exception as e:
                            logger.warning(f"Failed to sync history: {e}")

                        # Trigger background vision descriptions for new media
                        for m in new_msgs:
                            if m.get("is_media"):
                                asyncio.create_task(describe_media_async(page, contact_id, m["content"], m["element_selector"]))

                        you_new_msgs = [m["content"] for m in new_msgs if m["role"] == "you"]
                        them_new_msgs = [m["content"] for m in new_msgs if m["role"] == "them"]

                        if you_new_msgs:
                            # User manually replied (or auto-send just happened). Clear pending draft.
                            _state["pending_reply"] = None
                            _state["status_text"] = "Watching conversation"
                            logger.info(f"👤 Detected your reply: {you_new_msgs[-1][:80]}")

                        if them_new_msgs:
                            new_text = "\n".join(them_new_msgs)
                            _state["last_message"] = new_text
                            logger.info(f"📨 New message: {new_text[:100]}")
                            _state["status_text"] = "New msg — generating reply..."
                            _state["pending_reply"] = None

                            # Hit the backend generate endpoint
                            async with httpx.AsyncClient(timeout=60.0) as client:
                                resp = await client.post(
                                    f"{BACKEND_URL}/api/message",
                                    json={
                                        "contact_id": contact_id,
                                        "incoming_message": new_text,
                                        "mood": mood,
                                        "pro_mode": True,
                                    },
                                    headers=_auth_headers(),
                                )
                                if resp.status_code == 200:
                                    draft = resp.json().get("draft", "")
                                    _state["pending_reply"] = draft

                                    is_full_auto = bool(_state.get("full_auto", full_auto))
                                    if is_full_auto:
                                        _state["status_text"] = "Auto-sending reply..."
                                        logger.warning(
                                            f"[AUTO-SEND DISPATCH] Dispatching unattended DM for contact_id={contact_id} "
                                            f"target={their_ig_username} length={len(draft)}"
                                        )
                                        success = await send_on_page(page, draft)
                                        logger.warning(
                                            f"[AUTO-SEND RESULT] contact_id={contact_id} target={their_ig_username} "
                                            f"length={len(draft)} result={'success' if success else 'failed'}"
                                        )
                                        if success:
                                            _state["pending_reply"] = None
                                            _state["last_sent"] = draft
                                            _state["status_text"] = "Watching conversation"
                                            try:
                                                async with httpx.AsyncClient(timeout=10) as client:
                                                    await client.post(
                                                        f"{BACKEND_URL}/api/approve",
                                                        json={
                                                            "contact_id": contact_id,
                                                            "original_draft": draft,
                                                            "approved_draft": draft,
                                                        },
                                                        headers=_auth_headers(),
                                                    )
                                            except Exception as save_err:
                                                logger.warning(f"Failed to record auto-sent exchange: {save_err}")
                                        else:
                                            _state["status_text"] = "Auto-send failed. Retrying..."
                                            _state["pending_reply"] = None
                                    else:
                                        _state["status_text"] = "Draft ready — awaiting approval"
                                        logger.info(f"💬 Draft ready: {draft[:80]}")
                                else:
                                    _state["status_text"] = "Generation failed"
                                    logger.warning(f"Backend error {resp.status_code}")

                await asyncio.sleep(random.uniform(POLL_MIN, POLL_MAX))

                # Occasional micro-scroll to keep session alive
                if random.random() < 0.15:
                    await page.mouse.wheel(0, random.choice([-30, 30]))

            except Exception as e:
                consecutive_errors += 1
                logger.warning(f"Poll error ({consecutive_errors}/3): {repr(e)}")
                if consecutive_errors >= 3:
                    logger.error("Too many consecutive errors, watcher crashing.")
                    _state["status_text"] = "Watcher crashed. Please restart."
                    _state["running"] = False
                    break
                await asyncio.sleep(5)

        _page_ref = None
        await ctx.close()
        _state["status_text"] = "Stopped"
        logger.info("Watcher stopped cleanly.")


async def send_approved_reply(text: str) -> bool:
    """Called by the backend when user approves a draft. Sends on the open page."""
    global _page_ref, _loop_ref
    if _page_ref is None or _loop_ref is None:
        logger.error("No active page/loop — watcher not running.")
        return False
        
    try:
        import concurrent.futures
        future = asyncio.run_coroutine_threadsafe(send_on_page(_page_ref, text), _loop_ref)
        success = await asyncio.wrap_future(future)
        if success:
            _state["pending_reply"] = None
            _state["status_text"] = f"Watching @{_state['ig_username']}"
            # Also add to seen fingerprints to prevent re-reading as manual reply
            # (handled later in the positional fingerprint fix, but good for now)
            # We don't have access to the inner state here easily, but we can do it if needed.
        return success
    except Exception as e:
        logger.error(f"Cross-thread send failed: {e}")
        return False


# ─── Public Start ─────────────────────────────────────────────────────────────
def start_watcher(contact_id: str, their_ig_username: str, mood: str = "default", full_auto: bool = False):
    """Launch the watcher in a background thread with its own event loop."""
    import threading

    if _state["running"]:
        logger.warning("Watcher already running. Stop it first.")
        return
    _state.update({
        "running": True,
        "contact_id": contact_id,
        "ig_username": their_ig_username,
        "full_auto": bool(full_auto),
        "last_message": None,
        "last_sent": None,
        "pending_reply": None,
        "error": None,
        "status_text": "Starting Playwright...",
        "history_synced_at": 0,
    })

    def _thread():
        global _loop_ref
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _loop_ref = loop
        try:
            loop.run_until_complete(_watch_loop(contact_id, their_ig_username, mood, full_auto))
        finally:
            loop.close()
            _state["running"] = False
            _state["status_text"] = "Stopped"

    threading.Thread(target=_thread, daemon=True, name="ig_watcher").start()
    logger.info(f"Watcher started for @{their_ig_username} (contact {contact_id})")


async def set_full_auto(enabled: bool) -> dict:
    """Dynamically toggle full_auto mode on the running watcher session."""
    _state["full_auto"] = bool(enabled)
    logger.warning(f"[AUTO-SEND TOGGLE] Watcher full_auto dynamically set to {enabled}")
    dispatched = False
    if enabled and _state.get("pending_reply"):
        pending = _state["pending_reply"]
        logger.info(f"[AUTO-SEND DISPATCH] Dispatching pending draft immediately: {pending[:60]}")
        dispatched = await send_approved_reply(pending)
    return {"full_auto": _state["full_auto"], "dispatched_pending": dispatched}
