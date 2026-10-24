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

    # ── Test 7: WhatsApp Active Swipe-to-Reply Bar ────────────────────
    def test_whatsapp_active_swipe_reply(self):
        """
        Tests that when a user swipes a message on WhatsApp Web,
        the active reply bar rendered in the footer is prioritized over the chat history.
        """
        mock_wa_swipe_html = """
        <!DOCTYPE html>
        <html>
        <head><title>WhatsApp Web</title></head>
        <body>
          <div id="app">
            <header><span dir="auto" title="Alex">Alex</span></header>
            <div class="conversation">
              <!-- Regular older incoming message -->
              <div class="message-in">
                <div class="selectable-text">Hey how are you doing?</div>
              </div>
            </div>
            <footer>
              <!-- Active swipe-to-reply bar preview -->
              <div data-testid="quoted-message">
                <div data-testid="quoted-mention">Alex</div>
                <span dir="auto">Are you free Saturday for lunch?</span>
                <button data-testid="cancel-reply">X</button>
              </div>
              <div role="textbox" contenteditable="true"></div>
            </footer>
          </div>
        </body>
        </html>
        """
        self.page.set_content(mock_wa_swipe_html)
        content_js_path = Path(__file__).parent.parent / "extension" / "content.js"
        js_code = content_js_path.read_text(encoding="utf-8")

        result = self.page.evaluate(f"""
        () => {{
            window.__MOCK_PLATFORM__ = 'whatsapp';
            {js_code}
            return window._talkingCopilot.getLastIncomingMessage();
        }}
        """)

        self.assertIn("Replying to Alex", result)
        self.assertIn("Are you free Saturday for lunch?", result)

    # ── Test 8: Instagram Direct Active Swipe-to-Reply Banner ──────────
    def test_instagram_active_swipe_reply(self):
        """
        Tests that when a user swipes a message on Instagram Direct,
        the active reply banner in the footer is detected and prioritized.
        """
        mock_ig_swipe_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Instagram Direct</title></head>
        <body>
          <div role="main">
            <header><h2>Alex</h2></header>
            <div class="message-thread">
              <div style="align-self: flex-start;">
                <div dir="auto">Old message that should not override active reply</div>
              </div>
            </div>
            <footer>
              <div style="display: flex; flex-direction: column;">
                <div><span>Replying to Alex</span></div>
                <div><span>What time are you coming over?</span></div>
              </div>
              <div role="textbox" contenteditable="true" aria-label="Message..."></div>
            </footer>
          </div>
        </body>
        </html>
        """
        self.page.set_content(mock_ig_swipe_html)
        content_js_path = Path(__file__).parent.parent / "extension" / "content.js"
        js_code = content_js_path.read_text(encoding="utf-8")

        result = self.page.evaluate(f"""
        () => {{
            window.__MOCK_PLATFORM__ = 'instagram';
            {js_code}
            return window._talkingCopilot.getLastIncomingMessage();
        }}
        """)

        self.assertIn("Replying to Alex", result)
        self.assertIn("What time are you coming over?", result)

    # ── Test 9: WhatsApp Incoming Quoted Bubble ────────────────────────
    def test_whatsapp_incoming_quoted_bubble(self):
        """
        Tests that when an incoming message bubble on WhatsApp Web quotes a previous message,
        both the reply text and the quoted context are parsed.
        """
        mock_wa_quote_bubble_html = """
        <!DOCTYPE html>
        <html>
        <head><title>WhatsApp Web</title></head>
        <body>
          <div id="app">
            <header><span dir="auto" title="Alex">Alex</span></header>
            <div class="conversation">
              <div class="message-in">
                <!-- Quoted preview inside incoming bubble -->
                <div data-testid="quoted-message">
                  <span class="quoted-mention">You</span>
                  <span>That restaurant was way too loud</span>
                </div>
                <!-- Actual reply text -->
                <div class="selectable-text">Haha totally agreed, could barely hear you</div>
              </div>
            </div>
            <footer>
              <div role="textbox" contenteditable="true"></div>
            </footer>
          </div>
        </body>
        </html>
        """
        self.page.set_content(mock_wa_quote_bubble_html)
        content_js_path = Path(__file__).parent.parent / "extension" / "content.js"
        js_code = content_js_path.read_text(encoding="utf-8")

        result = self.page.evaluate(f"""
        () => {{
            window.__MOCK_PLATFORM__ = 'whatsapp';
            {js_code}
            return window._talkingCopilot.getLastIncomingMessage();
        }}
        """)

        self.assertIn("Haha totally agreed, could barely hear you", result)
        self.assertIn("Replying to", result)
        self.assertIn("That restaurant was way too loud", result)

    # ── Test 10: Instagram Incoming Quoted Bubble ──────────────────────
    def test_instagram_incoming_quoted_bubble(self):
        """
        Tests that when an incoming message bubble on Instagram Direct contains a quoted reply,
        the copilot extracts both the response text and the quoted message preview.
        """
        mock_ig_quote_bubble_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Instagram Direct</title></head>
        <body>
          <div role="main">
            <header><h2>Alex</h2></header>
            <div class="message-thread" style="display:flex; flex-direction:column; gap:8px;">
              <div role="row" style="align-self: flex-start; display: flex; flex-direction: column;">
                <!-- Quoted parent container -->
                <div style="border-left: 2px solid grey; padding-left: 6px;" aria-label="replied to your message">
                  Movie night at 8pm?
                </div>
                <!-- Reply text -->
                <div dir="auto">Count me in! I will bring snacks</div>
              </div>
            </div>
            <footer>
              <div role="textbox" contenteditable="true"></div>
            </footer>
          </div>
        </body>
        </html>
        """
        self.page.set_content(mock_ig_quote_bubble_html)
        content_js_path = Path(__file__).parent.parent / "extension" / "content.js"
        js_code = content_js_path.read_text(encoding="utf-8")

        result = self.page.evaluate(f"""
        () => {{
            window.__MOCK_PLATFORM__ = 'instagram';
            {js_code}
            return window._talkingCopilot.getLastIncomingMessage();
        }}
        """)

        self.assertIn("Count me in! I will bring snacks", result)
        self.assertIn("Replying to", result)
        self.assertIn("Movie night at 8pm?", result)

    # ── Test 11: In-Page Copilot Multi-Bubble Burst Rendering ─────────
    def test_in_page_copilot_multi_bubble_bursts(self):
        """
        Verifies that when a draft has multiple bubbles,
        the copilot modal renders the .tk-bubbles-stack with individual bubble chips
        and clicking a bubble item inserts only that bubble into the chat input.
        """
        mock_chat_html = """
        <!DOCTYPE html>
        <html>
        <head><title>WhatsApp Web</title></head>
        <body>
          <div id="app">
            <header><span dir="auto" title="Alex">Alex</span></header>
            <div class="conversation">
              <div class="message-in"><div class="selectable-text">Did you see the new venue?</div></div>
            </div>
            <footer>
              <div id="chatInput" role="textbox" contenteditable="true"></div>
            </footer>
          </div>
        </body>
        </html>
        """
        self.page.set_content(mock_chat_html)
        content_js_path = Path(__file__).parent.parent / "extension" / "content.js"
        js_code = content_js_path.read_text(encoding="utf-8")

        # Mock fetch to return multi-bubble draft and trigger generation
        self.page.evaluate(f"""
        () => {{
            window.__MOCK_PLATFORM__ = 'whatsapp';
            {js_code}
            window.fetch = async (url) => {{
                if (url.includes('/api/copilot/draft')) {{
                    return {{
                        ok: true,
                        json: async () => ({{
                            contact_id: 'test_c',
                            contact_name: 'Alex',
                            draft: "wait really\\ni thought that was closed mondays haha",
                            bubbles: ["wait really", "i thought that was closed mondays haha"],
                            variants: [
                                {{
                                    label: 'chill',
                                    text: "wait really\\ni thought that was closed mondays haha",
                                    bubbles: ["wait really", "i thought that was closed mondays haha"]
                                }}
                            ]
                        }})
                    }};
                }}
                return {{ ok: true, json: async () => ({{}}) }};
            }};
            window._talkingCopilot.triggerDraftGeneration();
        }}
        """)

        # Wait for modal and bubbles stack
        self.page.wait_for_selector("#tk-bubbles-stack", state="visible")
        bubble_items = self.page.locator(".tk-bubble-item")
        self.assertEqual(bubble_items.count(), 2)

        # First bubble text
        self.assertIn("wait really", bubble_items.first.text_content())

        # Click the second bubble to insert just that bubble
        bubble_items.nth(1).click()

        # Check inserted text in the input
        input_text = self.page.locator("#chatInput").text_content().strip()
        self.assertEqual(input_text, "i thought that was closed mondays haha")


if __name__ == "__main__":
    unittest.main()
