"""
Playwright End-to-End Simulation Check:
1. Intercepting/simulating an incoming message from 'them'.
2. Verifying whether duplicates are created in the DB or in the UI.
3. Getting a generated response draft.
4. Approving and sending the response.
5. Verifying whether the response or the incoming message gets duplicated.
"""

import sys
import time
import json
import sqlite3
import httpx
from pathlib import Path
from playwright.sync_api import sync_playwright

DB_PATH = Path("data/db/talking.db")
SERVER_URL = "http://127.0.0.1:8000"

def get_db_messages(contact_id: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, role, content, timestamp FROM messages WHERE contact_id = ? ORDER BY id ASC",
        (contact_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "role": r[1], "content": r[2], "timestamp": r[3]} for r in rows]

def run_simulation():
    print("=" * 60)
    print("PLAYWRIGHT SIMULATION CHECK: INTERCEPT, DRAFT, SEND")
    print("=" * 60)

    # 1. Get auth token
    with httpx.Client(timeout=10) as client:
        token_res = client.get(f"{SERVER_URL}/api/auth/token")
        token = token_res.json().get("token", "")
        headers = {"X-Talking-Token": token}

        # Pick contact Maneet
        contacts_res = client.get(f"{SERVER_URL}/api/contacts")
        contacts = contacts_res.json()
        target_contact = next((c for c in contacts if "maneet" in c["name"].lower()), contacts[0])
        contact_id = target_contact["id"]
        contact_name = target_contact["name"]

    print(f"Target Contact: {contact_name} (ID: {contact_id})")

    # Count DB messages before test
    db_before = get_db_messages(contact_id)
    print(f"DB Message count before test: {len(db_before)}")

    simulated_text = f"Yo test simulation at {int(time.time())}"
    print(f"\nSimulated incoming message: {simulated_text!r}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 850})
        page = context.new_page()

        # Step A: Load Dashboard
        print("\nStep A: Loading Dashboard...")
        page.goto(SERVER_URL, wait_until="networkidle")
        page.wait_for_selector(".app-container")
        page.select_option("#contactSelector", contact_id)
        time.sleep(1.5)

        initial_ui_msgs = page.locator("#messageHistory .message").count()
        print(f"Initial UI message count: {initial_ui_msgs}")

        # Step B: Simulate Watcher Interception Flow
        # In real life, instagram_watcher calls:
        # 1. /api/instagram/sync_history with new_msgs
        # 2. /api/message with incoming_message
        print("\nStep B: Simulating Watcher Message Interception...")
        with httpx.Client(timeout=30) as client:
            print("1. Watcher calls /api/instagram/sync_history...")
            sync_resp = client.post(
                f"{SERVER_URL}/api/instagram/sync_history",
                json={
                    "contact_id": contact_id,
                    "messages": [{"role": "them", "content": simulated_text, "is_media": False}]
                },
                headers=headers
            )
            print(f"   sync_history response: {sync_resp.status_code} - {sync_resp.json()}")

            db_after_sync = get_db_messages(contact_id)
            sync_matching = [m for m in db_after_sync if m["content"] == simulated_text]
            print(f"   DB count after sync_history: {len(db_after_sync)} (matching simulated text: {len(sync_matching)})")

            print("2. Watcher calls /api/message to generate draft...")
            msg_resp = client.post(
                f"{SERVER_URL}/api/message",
                json={
                    "contact_id": contact_id,
                    "incoming_message": simulated_text,
                    "mood": "chill",
                    "pro_mode": True
                },
                headers=headers
            )
            print(f"   /api/message response: {msg_resp.status_code}")
            draft_res = msg_resp.json()
            generated_draft = draft_res.get("draft", "")
            print(f"   Generated draft: {generated_draft!r}")

            db_after_msg = get_db_messages(contact_id)
            msg_matching = [m for m in db_after_msg if m["content"] == simulated_text]
            print(f"   DB count after /api/message: {len(db_after_msg)} (matching simulated text: {len(msg_matching)})")
            if len(msg_matching) > 1:
                print(f"   [!] BUG DETECTED: Simulated incoming message was DUPLICATED in DB! Count={len(msg_matching)}")
            else:
                print(f"   [OK] DB has exactly 1 copy of incoming message.")

        # Step C: Check UI rendering
        print("\nStep C: Checking UI for the incoming message and checking for duplicates...")
        # Simulate watcher status polling or history reload
        page.evaluate("""
            async () => {
                const history = await window._talkingApi.getHistory(window._talkingState.currentContact.id);
                window._talkingState.messages = Array.isArray(history) ? history : (history?.messages || []);
                window._talkingRenderMessages(window._talkingState.messages);
            }
        """)
        time.sleep(1.0)

        ui_matching = page.locator("#messageHistory .message").filter(has_text=simulated_text).count()
        print(f"UI rendered matches for incoming message: {ui_matching}")
        if ui_matching > 1:
            print(f"   [!] BUG DETECTED: Incoming message appears {ui_matching} times in the UI!")
        elif ui_matching == 1:
            print("   [OK] Incoming message rendered exactly ONCE in UI.")
        else:
            print("   [FAIL] Incoming message NOT rendered in UI!")

        # Step D: Put the generated draft into UI draft desk (as watcher does) and approve
        print("\nStep D: Displaying draft in UI and testing Approve & Send...")
        page.evaluate(f"""
            (draft) => {{
                window._talkingState.currentDraft = draft;
                window._talkingState.currentDraftRaw = draft;
                window.showDraft(draft, 0.92, [{{ text: draft, label: 'direct', bubbles: [draft] }}], [draft]);
            }}
        """, generated_draft)
        time.sleep(1.0)

        draft_content = page.locator("#draftContent").inner_text().strip()
        print(f"Draft desk text: {draft_content!r}")

        # Check Approve button
        approve_btn = page.locator("#approveBtn")
        print(f"Approve button visible: {approve_btn.is_visible()}, text: {approve_btn.inner_text().strip()!r}")

        # Click Approve
        print("Clicking Approve button...")
        approve_btn.click()
        time.sleep(2.0)

        # Check DB after approve
        db_after_approve = get_db_messages(contact_id)
        draft_matching_db = [m for m in db_after_approve if m["content"] == generated_draft]
        print(f"DB count after Approve: {len(db_after_approve)} (matching sent draft: {len(draft_matching_db)})")

        # Step E: Simulate what happens when the Watcher polls Instagram again after send
        print("\nStep E: Simulating Watcher polling Instagram after send...")
        # On Instagram, the newly sent draft now exists in DOM as role 'you'
        # Watcher runs get_recent_history and posts to sync_history
        with httpx.Client(timeout=10) as client:
            sync_resp2 = client.post(
                f"{SERVER_URL}/api/instagram/sync_history",
                json={
                    "contact_id": contact_id,
                    "messages": [
                        {"role": "them", "content": simulated_text, "is_media": False},
                        {"role": "you", "content": generated_draft, "is_media": False}
                    ]
                },
                headers=headers
            )
            print(f"Post-send sync_history response: {sync_resp2.status_code} - {sync_resp2.json()}")

        # Refresh UI
        page.evaluate("""
            async () => {
                const history = await window._talkingApi.getHistory(window._talkingState.currentContact.id);
                window._talkingState.messages = Array.isArray(history) ? history : (history?.messages || []);
                window._talkingRenderMessages(window._talkingState.messages);
            }
        """)
        time.sleep(1.0)

        db_final = get_db_messages(contact_id)
        draft_matching_final = [m for m in db_final if m["content"] == generated_draft]
        print(f"Final DB matches for sent draft: {len(draft_matching_final)}")
        if len(draft_matching_final) > 1:
            print(f"   [!] BUG DETECTED: Sent draft was DUPLICATED in DB! Count={len(draft_matching_final)}")
        else:
            print(f"   [OK] DB has exactly 1 copy of sent draft.")

        ui_draft_matching = page.locator("#messageHistory .message").filter(has_text=generated_draft).count()
        print(f"Final UI matches for sent draft: {ui_draft_matching}")
        if ui_draft_matching > 1:
            print(f"   [!] BUG DETECTED: Sent draft appears {ui_draft_matching} times in the UI!")
        elif ui_draft_matching == 1:
            print("   [OK] Sent draft appears exactly ONCE in UI.")
        else:
            print("   [FAIL] Sent draft NOT found in UI!")

        screenshot_path = "C:/Users/manee/.gemini/antigravity/brain/1e41d2e8-ed53-4ec2-8f04-43c83169c8ff/screenshots/simulation_check_result.png"
        page.screenshot(path=screenshot_path)
        print(f"\nScreenshot saved to {screenshot_path}")

        browser.close()

if __name__ == "__main__":
    run_simulation()
