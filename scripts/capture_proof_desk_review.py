"""
Proof Desk UI Review Capture Script
Captures before/after screenshots into docs/ui-review/ across all states:
empty, drafting, 2-bubble draft, steered with marks, note row open, sidebar, pill, modal in both Light and Dark modes.
"""

import os
import sys
import time
import shutil
import threading
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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


OUT_DIR = Path("docs/ui-review")
OUT_DIR.mkdir(parents=True, exist_ok=True)

ARTIFACT_DIR = Path(r"C:\Users\manee\.gemini\antigravity\brain\1e41d2e8-ed53-4ec2-8f04-43c83169c8ff\screenshots")
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

CONTENT_JS_PATH = Path("extension/content.js").resolve()
CONTENT_JS = CONTENT_JS_PATH.read_text(encoding="utf-8")

def save_screen(page, name):
    target_path = OUT_DIR / name
    page.screenshot(path=str(target_path), full_page=False)
    # Also copy to artifact dir
    artifact_path = ARTIFACT_DIR / name
    shutil.copyfile(target_path, artifact_path)
    print(f"Captured: {target_path.name}")

def main():
    server = ServerThread()
    server.start()
    time.sleep(1.8)

    # Ensure a test contact exists for rendering
    test_contact = db.add_contact(Contact(
        name="Elena Rostova",
        relationship_stage="close_friend",
        convo_goal="make_plans",
        my_impression="Curator & print designer",
        strategy_note="Check timing for art gallery opening",
        their_interests=["typography", "analog synths", "coffee", "printmaking"],
        inside_jokes=["Never ask about the blue ink disaster", "Only order flat whites"],
        notes="Met at editorial design conference. Busy on Monday mornings."
    ))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 860}, device_scale_factor=2)
        page = context.new_page()

        # =====================================================================
        # 1. LIGHT MODE DASHBOARD CAPTURES
        # =====================================================================
        page.goto(BASE_URL)
        page.wait_for_selector(".app-container")
        page.evaluate("() => applyTheme('light')")
        page.wait_for_timeout(300)

        # 1.1 Empty State (Light)
        save_screen(page, "light_1_empty.png")

        # 1.2 Drafting / Generating State (Light)
        page.evaluate("() => setLoading(true)")
        page.wait_for_timeout(200)
        save_screen(page, "light_2_drafting.png")
        page.evaluate("() => setLoading(false)")

        # 1.3 2-Bubble Draft State (Light)
        page.evaluate("""
        () => {
            window.showDraft(
                "wait really\\ni thought that was closed mondays haha",
                0.94,
                [
                    {
                        label: 'chill',
                        text: "wait really\\ni thought that was closed mondays haha",
                        bubbles: ["wait really", "i thought that was closed mondays haha"]
                    },
                    {
                        label: 'direct',
                        text: "I checked their schedule and they reopen Tuesday at 10am.",
                        bubbles: ["I checked their schedule and they reopen Tuesday at 10am."]
                    },
                    {
                        label: 'banter',
                        text: "You really tried to go on their only day off? Classic 😂",
                        bubbles: ["You really tried to go on their only day off? Classic 😂"]
                    }
                ],
                ["wait really", "i thought that was closed mondays haha"]
            );
        }
        """)
        page.wait_for_timeout(300)
        save_screen(page, "light_3_2bubble_draft.png")

        # 1.4 Steered With Revision Marks (Light)
        page.evaluate("""
        () => {
            state.previousDraft = "wait really i thought that was closed mondays haha";
            state.showMarks = true;
            if (dom.marksToggleBtn) dom.marksToggleBtn.classList.add('active');
            window.showDraft(
                "wait really i heard they reopen tomorrow morning at 10am haha",
                0.96,
                [
                    {
                        label: 'chill',
                        text: "wait really i heard they reopen tomorrow morning at 10am haha",
                        bubbles: ["wait really", "i heard they reopen tomorrow morning at 10am haha"]
                    }
                ],
                ["wait really", "i heard they reopen tomorrow morning at 10am haha"]
            );
        }
        """)
        page.wait_for_timeout(300)
        save_screen(page, "light_4_steered_with_marks.png")

        # 1.5 Note Row Open (Light)
        page.evaluate("""
        () => {
            if (dom.marginNoteRow) dom.marginNoteRow.classList.remove('hidden');
            if (dom.noteToggleBtn) dom.noteToggleBtn.classList.add('active');
            if (dom.steeringInput) dom.steeringInput.value = "Tease them about always forgetting operating hours";
        }
        """)
        page.wait_for_timeout(200)
        save_screen(page, "light_5_note_row_open.png")

        # 1.6 Sidebar Focus (Light)
        page.evaluate("""
        () => {
            const side = document.querySelector('.sidebar');
            if (side) side.scrollTop = 0;
        }
        """)
        page.wait_for_timeout(200)
        save_screen(page, "light_6_sidebar.png")

        # =====================================================================
        # 2. DARK MODE DASHBOARD CAPTURES
        # =====================================================================
        page.evaluate("() => applyTheme('dark')")
        page.wait_for_timeout(300)

        # 2.5 Note Row Open (Dark)
        save_screen(page, "dark_5_note_row_open.png")

        # 2.4 Steered With Marks (Dark)
        page.evaluate("""
        () => {
            if (dom.marginNoteRow) dom.marginNoteRow.classList.add('hidden');
            if (dom.noteToggleBtn) dom.noteToggleBtn.classList.remove('active');
        }
        """)
        page.wait_for_timeout(200)
        save_screen(page, "dark_4_steered_with_marks.png")

        # 2.3 2-Bubble Draft (Dark)
        page.evaluate("""
        () => {
            state.showMarks = false;
            if (dom.marksToggleBtn) dom.marksToggleBtn.classList.remove('active');
            window.showDraft(
                "wait really\\ni thought that was closed mondays haha",
                0.94,
                [
                    {
                        label: 'chill',
                        text: "wait really\\ni thought that was closed mondays haha",
                        bubbles: ["wait really", "i thought that was closed mondays haha"]
                    },
                    {
                        label: 'direct',
                        text: "I checked their schedule and they reopen Tuesday at 10am.",
                        bubbles: ["I checked their schedule and they reopen Tuesday at 10am."]
                    },
                    {
                        label: 'banter',
                        text: "You really tried to go on their only day off? Classic 😂",
                        bubbles: ["You really tried to go on their only day off? Classic 😂"]
                    }
                ],
                ["wait really", "i thought that was closed mondays haha"]
            );
        }
        """)
        page.wait_for_timeout(300)
        save_screen(page, "dark_3_2bubble_draft.png")

        # 2.2 Drafting (Dark)
        page.evaluate("() => setLoading(true)")
        page.wait_for_timeout(200)
        save_screen(page, "dark_2_drafting.png")
        page.evaluate("() => setLoading(false)")

        # 2.1 Empty (Dark)
        page.evaluate("() => resetDraftState()")
        page.wait_for_timeout(200)
        save_screen(page, "dark_1_empty.png")

        # 2.6 Sidebar Focus (Dark)
        save_screen(page, "dark_6_sidebar.png")

        # =====================================================================
        # 3. WHATSAPP WEB HARNESS (LIGHT & DARK PILL & MODAL)
        # =====================================================================
        wa_harness_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <title>WhatsApp Web</title>
          <style>
            body {{
              margin: 0;
              background-color: #eae6df;
              color: #111b21;
              font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
              display: flex;
              flex-direction: column;
              height: 100vh;
            }}
            body.dark {{
              background-color: #0c1317;
              color: #e9edef;
            }}
            header {{
              height: 59px;
              background: #f0f2f5;
              border-bottom: 1px solid rgba(11,20,26,.08);
              display: flex;
              align-items: center;
              padding: 0 16px;
              font-weight: 500;
            }}
            body.dark header {{
              background: #202c33;
              border-bottom: 1px solid rgba(134,150,160,.15);
            }}
            .chat-area {{
              flex: 1;
              padding: 20px 40px;
              display: flex;
              flex-direction: column;
              gap: 12px;
              overflow-y: auto;
            }}
            .wa-msg {{
              max-width: 65%;
              padding: 8px 12px;
              border-radius: 8px;
              font-size: 14.2px;
              line-height: 19px;
            }}
            .wa-in {{
              background: #ffffff;
              align-self: flex-start;
              border-top-left-radius: 0;
            }}
            body.dark .wa-in {{
              background: #202c33;
            }}
            .wa-out {{
              background: #d9fdd3;
              align-self: flex-end;
              border-top-right-radius: 0;
            }}
            body.dark .wa-out {{
              background: #005c4b;
            }}
            footer {{
              height: 62px;
              background: #f0f2f5;
              display: flex;
              align-items: center;
              padding: 0 16px;
              gap: 12px;
            }}
            body.dark footer {{
              background: #202c33;
            }}
            .wa-input {{
              flex: 1;
              background: #ffffff;
              border-radius: 8px;
              padding: 9px 12px;
              outline: none;
              font-size: 15px;
            }}
            body.dark .wa-input {{
              background: #2a3942;
              color: #d1d7db;
            }}
          </style>
        </head>
        <body>
          <header>
            <span dir="auto" title="Maya Lin">Maya Lin</span>
          </header>
          <div class="chat-area">
            <div class="wa-msg wa-in">
              <span class="selectable-text">Hey are we still on for the gallery opening on Saturday?</span>
            </div>
            <div class="wa-msg wa-out">
              <span>Yeah definitely! What time does it kick off?</span>
            </div>
            <div class="wa-msg wa-in">
              <span class="selectable-text">Doors open at 7pm, let me know if you want to grab coffee beforehand</span>
            </div>
          </div>
          <footer>
            <div class="wa-input" role="textbox" contenteditable="true" placeholder="Type a message"></div>
          </footer>
        </body>
        </html>
        """

        # 3.1 WhatsApp Light - Pill
        page.set_content(wa_harness_html)
        page.evaluate(f"""
        () => {{
            window.__MOCK_PLATFORM__ = 'whatsapp';
            {CONTENT_JS}
        }}
        """)
        page.wait_for_timeout(300)
        save_screen(page, "light_7_pill.png")

        # 3.2 WhatsApp Light - Modal
        page.evaluate("""
        () => {
            window._talkingCopilot.openCopilotModal('Maya Lin', 'Doors open at 7pm, let me know if you want to grab coffee beforehand', false, {
                contact_id: 'test_maya',
                draft: "definitely down for coffee first! how does 5:30 work for you?",
                bubbles: ["definitely down for coffee first!", "how does 5:30 work for you?"],
                variants: [
                    {
                        label: 'chill',
                        text: "down for coffee! 5:30?",
                        bubbles: ["down for coffee!", "5:30?"]
                    },
                    {
                        label: 'direct',
                        text: "Definitely down for coffee first! How does 5:30 work for you?",
                        bubbles: ["Definitely down for coffee first!", "How does 5:30 work for you?"]
                    },
                    {
                        label: 'banter',
                        text: "Only if you admit your coffee taste is questionable haha",
                        bubbles: ["Only if you admit your coffee taste is questionable haha"]
                    }
                ]
            });
        }
        """)
        page.wait_for_timeout(300)
        save_screen(page, "light_8_modal.png")

        # 3.3 WhatsApp Dark - Pill & Modal
        page.evaluate("""
        () => {
            document.body.classList.add('dark');
            const host = document.getElementById('talking-copilot-host');
            if (host) host.setAttribute('data-theme', 'dark');
        }
        """)
        page.wait_for_timeout(200)
        save_screen(page, "dark_8_modal.png")

        # Dark Pill
        page.evaluate("""
        () => {
            window._talkingCopilot.closeCopilotModal();
        }
        """)
        page.wait_for_timeout(200)
        save_screen(page, "dark_7_pill.png")

        browser.close()
        try:
            db.delete_contact(test_contact.id)
        except Exception:
            pass
        server.stop()
        print("All 16 Proof Desk UI Review screenshots captured successfully!")

if __name__ == "__main__":
    main()
