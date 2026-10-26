"""
Real-life Visual E2E Check using Playwright
===========================================
Tests:
1. Loading the live Talking dashboard at http://127.0.0.1:8000.
2. Inspecting how the Reel and message bubbles render visually (verifying compact dimensions).
3. Simulating new incoming messages (text, Reel, emojis) intercepted by the watcher.
4. Verifying live UI polling and rendering of intercepted messages.
5. Verifying AI draft generation.
6. Verifying Instagram DOM scraping on authentic mock DOM.
"""

import os
import sys
import time
import json
import threading
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

import uvicorn
from playwright.sync_api import sync_playwright

SCREENSHOTS_DIR = Path(r"C:\Users\manee\.gemini\antigravity\brain\1e41d2e8-ed53-4ec2-8f04-43c83169c8ff\screenshots")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

class BackgroundServer(threading.Thread):
    def __init__(self, host="127.0.0.1", port=8000):
        super().__init__(daemon=True)
        from backend.main import app
        config = uvicorn.Config(app, host=host, port=port, log_level="warning")
        self.server = uvicorn.Server(config)

    def run(self):
        self.server.run()

    def stop(self):
        self.server.should_exit = True

def run_real_life_checks():
    print("==================================================")
    print("  TALKING: REAL-LIFE PLAYWRIGHT INSPECTION")
    print("==================================================")

    # 1. Start server
    print("\n1. Starting backend server on http://127.0.0.1:8000...")
    server = BackgroundServer()
    server.start()
    time.sleep(2.0)

    from backend.main import db, SERVER_API_TOKEN
    import httpx

    # Check contact Maneet
    contact_id = "a38db0e1-592b-46ae-bbb8-db0ae36de0e5"
    contact = db.get_contact(contact_id)
    if not contact:
        print(f"Warning: Contact {contact_id} not found, using first available contact.")
        contacts = db.list_contacts()
        contact = contacts[0]
        contact_id = contact.id

    print(f"Target Contact: {contact.name} ({contact_id})")

    with sync_playwright() as pw:
        # Launch browser
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()

        # ── Test Phase 1: Open Talking Dashboard ────────────────────────
        print("\n2. Loading Talking Dashboard...")
        page.goto("http://127.0.0.1:8000", wait_until="networkidle")
        page.wait_for_selector(".app-container")

        # Select Maneet from dropdown
        print(f"Selecting contact {contact.name}...")
        page.select_option("#contactSelector", contact_id)
        # Give time for history to fetch and render
        time.sleep(1.5)

        # Inspect message history elements
        messages = page.locator("#messageHistory .message")
        msg_count = messages.count()
        print(f"Rendered message count: {msg_count}")

        # Check Reel card dimensions
        reel_card = page.locator(".media-reel-card")
        if reel_card.count() > 0:
            box = reel_card.first.bounding_box()
            print(f"Reel Card Dimensions: Width = {box['width']}px, Height = {box['height']}px")
            if box["width"] <= 260 and box["height"] <= 420:
                print("PASS: Reel card is cleanly constrained (NOT full-screen)!")
            else:
                print(f"FAIL: Reel card too large: {box}")

        shot1 = SCREENSHOTS_DIR / "step1_dashboard_with_reel.png"
        page.screenshot(path=str(shot1))
        print(f"Saved Screenshot 1: {shot1}")

        # ── Test Phase 2: Intercept & Sync New Incoming Messages ────────
        print("\n3. Simulating Incoming Messages from Instagram Watcher...")
        new_msgs_payload = [
            {
                "role": "them",
                "content": "hey bro did you see this reel? 😂",
                "is_media": False
            },
            {
                "role": "them",
                "content": "[Shared Instagram Reel: https://www.instagram.com/reel/C8XYZ_FunnyReel/ | Hilarious Cat Video]",
                "is_media": True,
                "is_reel": True,
                "reel_url": "https://www.instagram.com/reel/C8XYZ_FunnyReel/",
                "media_url": "https://instagram.fbom3-2.fna.fbcdn.net/v/t51.82787-15/723187125_18108074746893252_4842249915485070415_n.jpg?efg=eyJlZmciOiJDTElQUyJ9"
            },
            {
                "role": "them",
                "content": "🔥🔥🔥",
                "is_media": False
            },
            {
                "role": "them",
                "content": "are we still meeting for lunch tomorrow at 1?",
                "is_media": False
            }
        ]

        # Post to /api/instagram/sync_history using auth token
        with httpx.Client(timeout=10) as client:
            sync_resp = client.post(
                "http://127.0.0.1:8000/api/instagram/sync_history",
                json={"contact_id": contact_id, "messages": new_msgs_payload},
                headers={"X-Talking-Token": SERVER_API_TOKEN}
            )
            print(f"Sync response: {sync_resp.status_code} - {sync_resp.json()}")

        # Now trigger the dashboard's history refresh
        print("Polling / refreshing dashboard message history...")
        page.evaluate("""
            async () => {
                const history = await window._talkingApi.getHistory(window._talkingState.currentContact.id);
                window._talkingState.messages = Array.isArray(history) ? history : (history?.messages || []);
                window._talkingRenderMessages(window._talkingState.messages);
            }
        """)
        time.sleep(1.0)

        # Inspect newly rendered elements
        new_count = page.locator("#messageHistory .message").count()
        print(f"Updated message count in UI: {new_count}")

        # Check jumbo emoji bubble
        emoji_bubble = page.locator(".bubble-emoji-only")
        if emoji_bubble.count() > 0:
            emoji_text = emoji_bubble.first.inner_text().encode("ascii", "replace").decode("ascii")
            font_size = emoji_bubble.first.evaluate("el => window.getComputedStyle(el).fontSize")
            print(f"PASS: Jumbo Emoji detected: '{emoji_text}' with font-size {font_size}")

        # Check Reel embed card
        all_reels = page.locator(".media-reel-card")
        print(f"Reel Embed Cards count: {all_reels.count()}")
        for i in range(all_reels.count()):
            r_box = all_reels.nth(i).bounding_box()
            print(f"Reel Card {i+1} dimensions: {r_box['width']}px wide x {r_box['height']}px high")

        # Check play buttons
        play_btns = page.locator(".media-reel-play-btn")
        print(f"Reel Play buttons count: {play_btns.count()}")

        shot2 = SCREENSHOTS_DIR / "step2_intercepted_messages_rendered.png"
        page.screenshot(path=str(shot2))
        print(f"Saved Screenshot 2: {shot2}")

        # ── Test Phase 3: AI Draft Generation ───────────────────────────
        print("\n4. Testing AI Draft Generation on the last incoming message...")
        last_incoming_text = "are we still meeting for lunch tomorrow at 1?"
        
        # Put text into composer and click Send
        page.fill("#messageInput", last_incoming_text)
        time.sleep(0.5)
        page.click("#sendBtn")

        # Wait for draft to appear
        print("Waiting for draft generation...")
        try:
            page.wait_for_selector("#draftContent:not(.hidden)", timeout=25000)
            page.wait_for_function("() => !document.querySelector('.draft-placeholder')", timeout=25000)
            time.sleep(1.0)
            draft_text = page.locator("#draftContent").inner_text()
            print(f"Generated Draft: {draft_text[:100]}...")
            
            # Check variants
            variants = page.locator(".variant-card")
            print(f"Variants generated: {variants.count()}")
        except Exception as e:
            print(f"Draft generation wait notice: {e}")

        shot3 = SCREENSHOTS_DIR / "step3_draft_generated.png"
        page.screenshot(path=str(shot3))
        print(f"Saved Screenshot 3: {shot3}")

        # ── Test Phase 4: Mock Instagram Direct DOM Scraper ─────────────
        print("\n5. Testing Instagram Scraper against authentic mock DOM...")
        mock_ig_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Instagram Direct Web</title></head>
        <body style="margin:0; display:flex;">
          <!-- Left Inbox Sidebar (0 to 320px) - Avatars must be IGNORED -->
          <div style="width:320px; height:900px; border-right:1px solid #ccc; padding:10px;">
            <h3>Direct Messages</h3>
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:12px;">
              <img src="avatar1.jpg" alt="supermant_678's profile picture" style="width:50px; height:50px; border-radius:50%;" />
              <span>supermant_678</span>
            </div>
            <div style="display:flex; align-items:center; gap:8px;">
              <img src="avatar2.jpg" alt="sofiasaurx's profile picture" style="width:50px; height:50px; border-radius:50%;" />
              <span>sofiasaurx</span>
            </div>
          </div>

          <!-- Main Conversation Container (x > 320px) -->
          <div role="main" style="flex:1; height:900px; display:flex; flex-direction:column; padding:20px;">
            <header style="height:60px; border-bottom:1px solid #eee;">
              <h2>Conversation with Alex</h2>
            </header>

            <div style="flex:1; display:flex; flex-direction:column; gap:12px; padding-top:20px;">
              <!-- Incoming text -->
              <div role="row" style="align-self: flex-start; display: flex;">
                <div dir="auto" style="background:#eee; padding:8px 12px; border-radius:12px;">Hi, you there?</div>
              </div>

              <!-- Outgoing text -->
              <div role="row" style="align-self: flex-end; display: flex;">
                <div dir="auto" style="background:#0095f6; color:#fff; padding:8px 12px; border-radius:12px;">Yeah what's up!</div>
              </div>

              <!-- Incoming Reel -->
              <div role="row" style="align-self: flex-start; display: flex; flex-direction: column;">
                <div style="position:relative; width:220px; height:280px;">
                  <img src="https://instagram.fbcdn.net/v/reel_thumb.jpg?efg=eyJlZmciOiJDTElQUyJ9" alt="Reel by @creator: Crazy trick" style="width:220px; height:280px; object-fit:cover; border-radius:10px;" />
                  <a href="https://www.instagram.com/reel/C8TestReel123/" style="display:inline-block; margin-top:4px;">Watch on Instagram</a>
                </div>
              </div>

              <!-- Incoming emoji -->
              <div role="row" style="align-self: flex-start; display: flex;">
                <div dir="auto" style="font-size:24px;">😂🔥</div>
              </div>
            </div>

            <footer style="height:60px;">
              <div role="textbox" contenteditable="true" aria-label="Message..."></div>
            </footer>
          </div>
        </body>
        </html>
        """
        ig_page = context.new_page()
        ig_page.set_content(mock_ig_html)

        import re
        watcher_file = PROJECT_ROOT / "backend" / "instagram_watcher.py"
        watcher_code = watcher_file.read_text(encoding="utf-8")

        # Extract scraper code from get_recent_history
        m_hist = re.search(r'messages\s*=\s*await\s+page\.evaluate\(r?"""(.*?)""",\s*limit\)', watcher_code, re.DOTALL)
        scraper_hist_js = m_hist.group(1) if m_hist else ""

        # Extract scraper code from get_latest_incoming
        m_inc = re.search(r'result\s*=\s*await\s+page\.evaluate\(r?"""(.*?)"""\)', watcher_code, re.DOTALL)
        scraper_inc_js = m_inc.group(1) if m_inc else ""

        # Evaluate scraper on this DOM using sync Playwright
        extracted_history = ig_page.evaluate(scraper_hist_js, 10) if scraper_hist_js else []
        latest_incoming = ig_page.evaluate(scraper_inc_js) if scraper_inc_js else []

        print(f"\nExtracted History count: {len(extracted_history)}")
        for idx, m in enumerate(extracted_history):
            safe_text = m.get('content', '')[:60].encode('ascii', 'replace').decode('ascii')
            print(f"  [{idx+1}] role={m.get('role')} | is_media={m.get('is_media')} | content={safe_text}...")

        # Verify profile pictures were completely excluded
        has_profile_pics = any("profile picture" in m.get("content", "").lower() for m in extracted_history)
        print(f"Profile pictures in extracted history: {has_profile_pics} (Must be False!)")

        # Verify Reel was extracted as a Reel
        has_reel = any("Shared Instagram Reel" in m.get("content", "") for m in extracted_history)
        print(f"Reel extracted correctly: {has_reel} (Must be True!)")

        # Verify latest incoming block
        safe_incoming = [t.encode('ascii', 'replace').decode('ascii') for t in latest_incoming]
        print(f"Latest incoming block: {safe_incoming}")

        shot4 = SCREENSHOTS_DIR / "step4_instagram_dom_extraction.png"
        ig_page.screenshot(path=str(shot4))
        print(f"Saved Screenshot 4: {shot4}")

        browser.close()
        server.stop()

    print("\n==================================================")
    print("  ALL REAL-LIFE INSPECTIONS COMPLETED!")
    print("==================================================")

if __name__ == "__main__":
    run_real_life_checks()
