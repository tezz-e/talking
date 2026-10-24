"""
Talking — Playwright End-to-End & In-Page Copilot Tests
======================================================
Tests the full frontend UI dashboard, the in-page copilot DOM interactions,
and multimodal Reel and Image detection in simulated Instagram Direct & WhatsApp Web.
"""

import threading
import time
import unittest
import base64
from pathlib import Path
import uvicorn
from playwright.sync_api import sync_playwright

from backend.main import app, db
from backend.models import Contact

TEST_PORT = 8199
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"


class ServerThread(threading.Thread):
    def __init__(self, host="127.0.0.1", port=TEST_PORT):
        super().__init__(daemon=True)
        config = uvicorn.Config(app, host=host, port=port, log_level="error")
        self.server = uvicorn.Server(config)

    def run(self):
        self.server.run()

    def stop(self):
        self.server.should_exit = True


class TestPlaywrightE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 1. Start server in daemon thread
        cls.server_thread = ServerThread()
        cls.server_thread.start()
        time.sleep(1.8)

        # 2. Launch Playwright headless Chromium
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

        # 3. Create a reliable test contact in DB
        cls.test_contact = db.add_contact(Contact(
            name="Playwright Test User",
            relationship_stage="friend",
            convo_goal="make_plans",
            my_impression="Tech reviewer",
            strategy_note="Ask about weekend demo",
        ))

    @classmethod
    def tearDownClass(cls):
        # Cleanup test contact
        try:
            db.delete_contact(cls.test_contact.id)
        except Exception:
            pass
        cls.browser.close()
        cls.playwright.stop()
        cls.server_thread.stop()

    def setUp(self):
        self.page = self.browser.new_page()

    def tearDown(self):
        self.page.close()

    # ── Test 1: Dashboard UI Structure & Interactions ──────────────────
    def test_dashboard_ui_elements(self):
        """Verifies dashboard loading, mood selection, and Pro Mode toggle."""
        self.page.goto(BASE_URL)
        self.page.wait_for_selector(".app-container")

        # Title check
        self.assertIn("Talking", self.page.title())
        self.assertIn("AI Texting Autopilot", self.page.title())

        # Mood chip selection
        chill_chip = self.page.locator('.mood-chip[data-mood="chill"]')
        self.assertTrue(chill_chip.is_visible())
        chill_chip.click()
        self.assertTrue("active" in (chill_chip.get_attribute("class") or ""))

        flirty_chip = self.page.locator('.mood-chip[data-mood="flirty"]')
        flirty_chip.click()
        self.assertTrue("active" in (flirty_chip.get_attribute("class") or ""))
        self.assertFalse("active" in (chill_chip.get_attribute("class") or ""))

        # Pro Mode toggle
        pro_btn = self.page.locator("#proModeBtn")
        self.assertTrue(pro_btn.is_visible())
        initial_active = "active" in (pro_btn.get_attribute("class") or "")
        pro_btn.click()
        self.assertEqual("active" in (pro_btn.get_attribute("class") or ""), not initial_active)
        # Toggle back
        pro_btn.click()

    # ── Test 2: Known Facts Inspector (Add & Delete) ────────────────────
    def test_facts_ui_add_and_delete(self):
        """Tests adding and deleting a fact through the sidebar drawer."""
        self.page.goto(BASE_URL)
        self.page.wait_for_selector("#contactSelector")

        # Select test contact
        self.page.select_option("#contactSelector", self.test_contact.id)
        self.page.wait_for_timeout(400)

        # Toggle new fact row
        self.page.click("#addFactToggleBtn")
        new_fact_row = self.page.locator("#newFactRow")
        self.assertTrue(new_fact_row.is_visible())

        # Fill fact details
        self.page.select_option("#newFactCategory", "work")
        self.page.fill("#newFactInput", "Founding Engineer at Antigravity AI")
        self.page.click("#saveNewFactBtn")

        # Wait for the fact item to render in the list
        self.page.wait_for_selector(".fact-item")
        fact_texts = self.page.locator(".fact-text").all_text_contents()
        self.assertTrue(any("Founding Engineer at Antigravity AI" in t for t in fact_texts))

        # Check badge styling
        badge = self.page.locator(".fact-cat-work").first
        self.assertTrue(badge.is_visible())
        self.assertEqual(badge.text_content().strip().lower(), "work")

        # Delete the fact
        del_btn = self.page.locator(".fact-item .fact-delete-btn").first
        del_btn.click()
        self.page.wait_for_timeout(300)

        # Confirm removal
        remaining_facts = self.page.locator(".fact-text").all_text_contents()
        self.assertFalse(any("Founding Engineer at Antigravity AI" in t for t in remaining_facts))

    # ── Test 3: Instagram Direct Media & Reel Detection ────────────────
    def test_instagram_reel_and_image_detection(self):
        """
        Simulates an Instagram Direct DOM with a shared Reel and an image.
        Verifies that the copilot script accurately extracts the Reel URL and image alt text.
        """
        mock_ig_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Instagram Direct</title></head>
        <body>
          <div role="main">
            <header>
              <h2>Alex</h2>
            </header>
            <div class="message-thread" style="display:flex; flex-direction:column; gap:8px;">
              <!-- Outgoing message from user -->
              <div style="align-self: flex-end; display: flex; justify-content: flex-end;">
                <div dir="auto">hey did you see that video</div>
              </div>

              <!-- Incoming Reel from Alex -->
              <div class="reel-bubble" style="align-self: flex-start; display: flex; justify-content: flex-start;">
                <a href="https://www.instagram.com/reel/C8XYZ_FunnyReel/">
                  <img src="thumb.jpg" alt="Reel by @comedycentral: Hilarious cat jumping into cereal box" width="220" height="220" />
                  <span>Watch on Instagram</span>
                </a>
              </div>
            </div>
            <footer>
              <div role="textbox" contenteditable="true" aria-label="Message..."></div>
            </footer>
          </div>
        </body>
        </html>
        """
        self.page.set_content(mock_ig_html)

        content_js_path = Path(__file__).parent.parent / "extension" / "content.js"
        js_code = content_js_path.read_text(encoding="utf-8")

        result = self.page.evaluate(f"""
        () => {{
            window.__MOCK_PLATFORM__ = 'instagram';
            {js_code}
            return window._talkingCopilot.getLastIncomingMessage();
        }}
        """)

        self.assertIn("Shared Instagram Reel", result)
        self.assertIn("https://www.instagram.com/reel/C8XYZ_FunnyReel/", result)
        self.assertIn("comedycentral", result)

    # ── Test 4: Instagram Image / Photo Detection ──────────────────────
    def test_instagram_photo_detection(self):
        """Verifies that incoming photos with alt-text are detected in Instagram Direct."""
        mock_ig_photo_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Instagram Direct</title></head>
        <body>
          <div role="main">
            <header>
              <span>Jordan</span>
            </header>
            <div class="message-thread" style="display:flex; flex-direction:column; gap:8px;">
              <div style="align-self: flex-start;">
                <img src="vacation.jpg" alt="May be an image of beach, sunset, and ocean" width="200" height="200" />
              </div>
            </div>
            <footer>
              <div role="textbox" contenteditable="true"></div>
            </footer>
          </div>
        </body>
        </html>
        """
        self.page.set_content(mock_ig_photo_html)
        content_js_path = Path(__file__).parent.parent / "extension" / "content.js"
        js_code = content_js_path.read_text(encoding="utf-8")

        result = self.page.evaluate(f"""
        () => {{
            window.__MOCK_PLATFORM__ = 'instagram';
            {js_code}
            return window._talkingCopilot.getLastIncomingMessage();
        }}
        """)

        self.assertIn("[Sent a photo: May be an image of beach, sunset, and ocean]", result)

    # ── Test 5: WhatsApp Web Media & Caption Detection ────────────────
    def test_whatsapp_media_detection(self):
        """Verifies WhatsApp Web image, caption, and voice message detection."""
        mock_wa_html = """
        <!DOCTYPE html>
        <html>
        <head><title>WhatsApp Web</title></head>
        <body>
          <div id="app">
            <header>
              <span dir="auto" title="Maya">Maya</span>
            </header>
            <div class="conversation">
              <div class="message-in">
                <img src="blob:image" alt="Concert tickets" width="180" height="180" />
                <div class="selectable-text">Look what arrived in mail today!</div>
              </div>
            </div>
            <footer>
              <div role="textbox" contenteditable="true"></div>
            </footer>
          </div>
        </body>
        </html>
        """
        self.page.set_content(mock_wa_html)
        content_js_path = Path(__file__).parent.parent / "extension" / "content.js"
        js_code = content_js_path.read_text(encoding="utf-8")

        result = self.page.evaluate(f"""
        () => {{
            window.__MOCK_PLATFORM__ = 'whatsapp';
            {js_code}
            return window._talkingCopilot.getLastIncomingMessage();
        }}
        """)

        self.assertIn("[Photo: Concert tickets]", result)
        self.assertIn("Look what arrived in mail today!", result)

    # ── Test 6: In-Page Text Insertion via document.execCommand ────────
    def test_in_page_chat_text_insertion(self):
        """Tests that text insertion reliably populates editable chat div elements."""
        mock_chat_html = """
        <!DOCTYPE html>
        <html>
        <body>
          <footer>
            <div id="targetInput" role="textbox" contenteditable="true"></div>
          </footer>
        </body>
        </html>
        """
        self.page.set_content(mock_chat_html)
        input_el = self.page.locator("#targetInput")

        # Focus and execute insertion command
        self.page.evaluate("""
        () => {
            const el = document.getElementById('targetInput');
            el.focus();
            document.execCommand('insertText', false, 'Yeah for sure, sounds good!');
        }
        """)

        inserted_text = input_el.text_content().strip()
        self.assertEqual(inserted_text, "Yeah for sure, sounds good!")


if __name__ == "__main__":
    unittest.main()
