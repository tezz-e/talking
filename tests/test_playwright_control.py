"""
Tests for Playwright Auto-Control and Unsend Logic
"""

import difflib
import unittest
from fastapi.testclient import TestClient
from backend.main import app, db, SERVER_API_TOKEN, context_assembler
from backend.models import Contact, Message
from backend.context import ContextAssembler


class TestPlaywrightControl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.auth_headers = {
            "Origin": "http://127.0.0.1:8000",
            "X-Talking-Token": SERVER_API_TOKEN,
        }
        cls.test_contact = db.add_contact(Contact(
            name="Control Test Contact",
            relationship_stage="friend",
            convo_goal="catch_up",
        ))

    @classmethod
    def tearDownClass(cls):
        try:
            db.delete_contact(cls.test_contact.id)
        except Exception:
            pass

    def test_unsend_database_and_endpoint(self):
        """Verify that an unsent message is marked in SQLite and excluded from LLM context."""
        # 1. Add a message from 'them'
        msg = db.add_message(Message(
            contact_id=self.test_contact.id,
            role="them",
            content="Hey secret message that will be unsent",
        ))
        
        # 2. Call /api/instagram/unsend
        resp = self.client.post(
            "/api/instagram/unsend",
            json={
                "contact_id": self.test_contact.id,
                "content": "Hey secret message that will be unsent"
            },
            headers=self.auth_headers
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("status"), "marked")

        # 3. Verify in DB
        recent = db.get_recent_messages(self.test_contact.id, n=5)
        matched = [m for m in recent if m.id == msg.id]
        self.assertTrue(len(matched) > 0)
        self.assertTrue(matched[0].metadata.get("is_unsent"))

        # 4. Verify ContextAssembler filters out the unsent message
        system_prompt, user_msg, _ = context_assembler.assemble(
            contact_id=self.test_contact.id,
            incoming_message="What's up",
            mood="default"
        )
        self.assertNotIn("Hey secret message that will be unsent", system_prompt)

    def test_sequence_matcher_unsend_no_replay(self):
        """Verify SequenceMatcher correctly identifies an unsend without replaying history."""
        last_seen = [
            {"role": "them", "content": "hello"},
            {"role": "you", "content": "hi there"},
            {"role": "them", "content": "quick question"},
            {"role": "them", "content": "unsent text"}
        ]
        # Contact unsends 'unsent text'
        current = [
            {"role": "them", "content": "hello"},
            {"role": "you", "content": "hi there"},
            {"role": "them", "content": "quick question"}
        ]

        last_sigs = [(m["role"], m["content"].strip()) for m in last_seen]
        curr_sigs = [(m["role"], m["content"].strip()) for m in current]

        sm = difflib.SequenceMatcher(None, last_sigs, curr_sigs)
        new_msgs = []
        unsent = []

        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag in ('insert', 'replace'):
                new_msgs.extend(current[j1:j2])
            if tag in ('delete', 'replace'):
                for d in last_seen[i1:i2]:
                    if d["role"] == "them":
                        unsent.append(d["content"])

        # ZERO new messages should be reported (no replay)
        self.assertEqual(len(new_msgs), 0)
        # Exactly 1 unsend detected
        self.assertEqual(unsent, ["unsent text"])

    def test_watcher_send_endpoint_validation(self):
        """Verify /api/watcher/send validates payload and requires auth."""
        # Missing text
        resp = self.client.post(
            "/api/watcher/send",
            json={},
            headers=self.auth_headers
        )
        self.assertEqual(resp.status_code, 400)

        # Unauthenticated request
        resp_unauth = self.client.post(
            "/api/watcher/send",
            json={"text": "hello"}
        )
        self.assertEqual(resp_unauth.status_code, 403)


if __name__ == "__main__":
    unittest.main()
