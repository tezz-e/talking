"""
Unit tests validating bug fixes identified during the codebase audit:
1. Contact model and database schema migration (convo_goal, my_impression, strategy_note)
2. Message pagination order (latest messages chronologically)
3. Duplicate message cleanup & save_exchange deduplication
4. ChatMessage timestamp datetime enforcement & reactions flexibility
5. Ingestion double-texting rate calculation over conversation threads
6. Context memory_query deduplication
7. MemoryStore search bounding n_results to matching count
8. Personality system prompt integration of strategic directives
"""

import unittest
import tempfile
import shutil
import json
from pathlib import Path
from datetime import datetime, timedelta

from backend.models import Contact, ContactCreate, ContactUpdate, Message, ChatMessage, RelationshipStage
from backend.database import DatabaseManager
from backend.ingestion.style_extractor import StyleExtractor
from backend.personality import PersonalityEngine
from backend.context import ContextAssembler


class TestDatabaseAndModels(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.db"
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_contact_fields_and_persistence(self):
        contact = Contact(
            name="Alice",
            convo_goal="make_plans",
            my_impression="Very cool person",
            strategy_note="Ask about weekend concert",
        )
        saved = self.db.add_contact(contact)
        self.assertEqual(saved.convo_goal, "make_plans")
        self.assertEqual(saved.my_impression, "Very cool person")
        self.assertEqual(saved.strategy_note, "Ask about weekend concert")

        retrieved = self.db.get_contact(saved.id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.convo_goal, "make_plans")
        self.assertEqual(retrieved.my_impression, "Very cool person")
        self.assertEqual(retrieved.strategy_note, "Ask about weekend concert")

        # Test partial update
        updated = self.db.update_contact(saved.id, {"convo_goal": "romantic"})
        self.assertEqual(updated.convo_goal, "romantic")
        self.assertEqual(updated.my_impression, "Very cool person")

    def test_messages_chronological_latest_order(self):
        contact = self.db.add_contact(Contact(name="Bob"))
        base_time = datetime(2026, 1, 1, 12, 0, 0)

        # Insert 60 messages spaced 1 minute apart
        for i in range(60):
            msg = Message(
                contact_id=contact.id,
                role="them" if i % 2 == 0 else "you",
                content=f"msg_{i}",
                timestamp=base_time + timedelta(minutes=i),
            )
            self.db.add_message(msg)

        # Query limit 5: should return msg_55 through msg_59 in chronological order
        recent_5 = self.db.get_messages(contact.id, limit=5)
        self.assertEqual(len(recent_5), 5)
        self.assertEqual(recent_5[0].content, "msg_55")
        self.assertEqual(recent_5[-1].content, "msg_59")
        # Ensure strictly ascending timestamp
        for i in range(len(recent_5) - 1):
            self.assertLess(recent_5[i].timestamp, recent_5[i + 1].timestamp)


class TestIngestionAndStyle(unittest.TestCase):
    def test_chat_message_schema(self):
        dt = datetime.now()
        msg = ChatMessage(
            sender="Me",
            content="hey",
            timestamp=dt,
            is_user=True,
            reactions=[{"reaction": "❤️", "actor": "friend"}],
        )
        self.assertEqual(msg.timestamp, dt)
        self.assertEqual(len(msg.reactions), 1)

    def test_double_texting_rate_with_thread(self):
        extractor = StyleExtractor(llm=None)
        now = datetime.now()

        # Thread: Them, User, User, Them, User, User, User (7 total)
        # User messages:
        # msg 1: User (prev was Them) -> not consecutive
        # msg 2: User (prev was User) -> consecutive (1)
        # msg 4: User (prev was Them) -> not consecutive
        # msg 5: User (prev was User) -> consecutive (2)
        # msg 6: User (prev was User) -> consecutive (3)
        # Total user messages in thread = 5. Consecutive = 3. Rate = 3 / 5 = 60.0%
        thread = [
            ChatMessage(sender="Them", content="hi", timestamp=now, is_user=False),
            ChatMessage(sender="Me", content="hey", timestamp=now, is_user=True),
            ChatMessage(sender="Me", content="u there?", timestamp=now, is_user=True),
            ChatMessage(sender="Them", content="yeah", timestamp=now, is_user=False),
            ChatMessage(sender="Me", content="ok cool", timestamp=now, is_user=True),
            ChatMessage(sender="Me", content="just checking", timestamp=now, is_user=True),
            ChatMessage(sender="Me", content="wyd", timestamp=now, is_user=True),
        ]
        user_msgs = [m for m in thread if m.is_user]
        stats = extractor.analyze(user_msgs, all_messages=thread)
        self.assertEqual(stats["double_texting_rate"], 60.0)


class TestContextAndPersonality(unittest.TestCase):
    def test_personality_includes_strategy(self):
        temp_dir = tempfile.mkdtemp()
        try:
            soul_path = Path(temp_dir) / "SOUL.md"
            style_path = Path(temp_dir) / "STYLE.md"
            soul_path.write_text("Test Soul", encoding="utf-8")
            style_path.write_text("Test Style", encoding="utf-8")

            personality = PersonalityEngine(data_dir=temp_dir)
            contact = {
                "name": "Alex",
                "relationship_stage": "crush",
                "convo_goal": "flirt",
                "my_impression": "Super smart",
                "strategy_note": "Tease them about pineapple pizza",
            }
            prompt = personality.build_system_prompt(
                contact=contact,
                relationship_stage="crush",
            )
            self.assertIn("Goal for this conversation: flirt", prompt)
            self.assertIn("Your impression of them: Super smart", prompt)
            self.assertIn("TACTICAL STRATEGY DIRECTIVE: Tease them about pineapple pizza", prompt)
        finally:
            shutil.rmtree(temp_dir)

    def test_lyric_hint_parsing_without_grounding(self):
        # High confidence lyric completion should be accepted even if grounded=False
        confidence, continuation = ContextAssembler._parse_lyric_hint(
            '{"confidence": 0.88, "continuation": "i was in the club with the homies"}'
        )
        self.assertGreaterEqual(confidence, 0.74)
        self.assertEqual(continuation, "i was in the club with the homies")

    def test_save_exchange_deduplication(self):
        temp_dir = tempfile.mkdtemp()
        try:
            db_path = Path(temp_dir) / "test.db"
            db = DatabaseManager(db_path)
            contact = db.add_contact(Contact(name="Charlie"))

            class MockMemory:
                def __init__(self):
                    self.saved = []
                def add_messages(self, msgs, **kwargs):
                    self.saved.extend(msgs)

            mock_memory = MockMemory()
            context = ContextAssembler(db=db, memory=mock_memory, personality=None, llm=None)

            # Call save_exchange with save_to_db=False (default)
            context.save_exchange(
                contact_id=contact.id,
                their_message="hello",
                your_response="world",
                save_to_db=False,
            )

            # Relational database should have 0 messages (no duplicate insertion)
            self.assertEqual(len(db.get_messages(contact.id)), 0)
            # Vector memory should have 1 item
            self.assertEqual(len(mock_memory.saved), 1)

            # When save_to_db=True is passed, it saves to DB
            context.save_exchange(
                contact_id=contact.id,
                their_message="hello2",
                your_response="world2",
                save_to_db=True,
            )
            self.assertEqual(len(db.get_messages(contact.id)), 2)
        finally:
            shutil.rmtree(temp_dir)

    def test_pro_mode_and_steering_models(self):
        from backend.models import GenerateRequest, SteerRequest, SteerResponse

        # GenerateRequest accepts pro_mode and steering_directive
        req = GenerateRequest(
            contact_id="test-contact",
            incoming_message="what u up to",
            pro_mode=True,
            steering_directive="steer towards getting coffee this saturday",
        )
        self.assertTrue(req.pro_mode)
        self.assertEqual(req.steering_directive, "steer towards getting coffee this saturday")

        # SteerRequest and SteerResponse models validate properly
        steer_req = SteerRequest(instruction="be more playful")
        self.assertEqual(steer_req.instruction, "be more playful")

        contact = Contact(name="Sam", convo_goal="make_plans")
        steer_res = SteerResponse(
            updated_fields={"strategy_note": "be more playful"},
            summary="Directive applied",
            contact=contact,
        )
        self.assertEqual(steer_res.updated_fields["strategy_note"], "be more playful")
        self.assertEqual(steer_res.contact.name, "Sam")

    def test_pii_scrubber(self):
        from backend.ingestion.pii_scrubber import PIIScrubber

        # Credit card test
        sample_cc = "my visa is 4111 1111 1111 1111 bro"
        scrubbed_cc = PIIScrubber.scrub(sample_cc)
        self.assertIn("[CREDIT_CARD]", scrubbed_cc)
        self.assertNotIn("4111 1111 1111 1111", scrubbed_cc)

        # Secrets / password test
        sample_pwd = "wifi password: Secret123! and token AIzaSyD-1234567890abcdefghijklmnopqrstuv"
        scrubbed_pwd = PIIScrubber.scrub(sample_pwd)
        self.assertIn("[PASSWORD]", scrubbed_pwd)
        self.assertIn("[API_KEY]", scrubbed_pwd)
        self.assertNotIn("Secret123!", scrubbed_pwd)

        # Phone number test
        sample_phone = "call me at +1 555-234-5678 or 9876543210"
        scrubbed_phone = PIIScrubber.scrub(sample_phone)
        self.assertIn("[PHONE_NUMBER]", scrubbed_phone)
        self.assertNotIn("555-234-5678", scrubbed_phone)

    def test_draft_variants_model(self):
        from backend.models import GenerateResponse, DraftVariant

        res = GenerateResponse(
            draft="yeah fr im down",
            confidence=0.92,
            retrieved_memories=["m1"],
            variants=[
                DraftVariant(label="chill", text="bet"),
                DraftVariant(label="direct", text="yeah fr im down"),
                DraftVariant(label="banter", text="only if you pay"),
            ],
        )
        self.assertEqual(len(res.variants), 3)
        self.assertEqual(res.variants[0].label, "chill")
        self.assertEqual(res.variants[0].text, "bet")

class TestMilestoneFeatures(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.db"
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_facts_crud_and_deletion(self):
        from backend.models import Fact, FactCreate

        contact = self.db.add_contact(Contact(name="Elena"))
        fact1 = Fact(
            contact_id=contact.id,
            category="preference",
            fact="Prefers oat milk lattes",
            confidence=0.9,
        )
        saved = self.db.add_fact(fact1)
        self.assertGreater(saved.id, 0)
        self.assertEqual(saved.fact, "Prefers oat milk lattes")

        fact2 = Fact(
            contact_id=contact.id,
            category="work",
            fact="Senior Designer at Acme",
            confidence=0.95,
        )
        self.db.add_fact(fact2)

        facts = self.db.get_facts(contact.id)
        self.assertEqual(len(facts), 2)

        # Test deletion
        deleted = self.db.delete_fact(saved.id)
        self.assertTrue(deleted)
        remaining = self.db.get_facts(contact.id)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].fact, "Senior Designer at Acme")

        # Deleting non-existent returns False
        self.assertFalse(self.db.delete_fact(99999))

    def test_telegram_parser(self):
        from backend.ingestion.telegram import TelegramParser

        fake_export = {
            "name": "Alex",
            "type": "personal_chat",
            "id": 12345,
            "messages": [
                {
                    "id": 1,
                    "type": "message",
                    "date": "2026-03-01T10:00:00",
                    "from": "Alex",
                    "text": "Call me at +1 555-019-2831 tomorrow",
                },
                {
                    "id": 2,
                    "type": "message",
                    "date": "2026-03-01T10:01:00",
                    "from": "MyUser",
                    "text": [
                        "Sounds good! Check ",
                        {"type": "link", "text": "https://example.com"},
                        " for details",
                    ],
                },
                {
                    "id": 3,
                    "type": "service",
                    "date": "2026-03-01T10:02:00",
                    "text": "Alex pinned a message",
                },
            ],
        }

        export_path = Path(self.temp_dir) / "result.json"
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(fake_export, f)

        parser = TelegramParser(user_name="MyUser")
        convs = parser.parse_file(str(export_path))
        self.assertIn("Alex", convs)
        msgs = convs["Alex"]
        self.assertEqual(len(msgs), 2)  # Service message skipped

        # First message from Alex, incoming, PII scrubbed
        self.assertFalse(msgs[0].is_user)
        self.assertEqual(msgs[0].sender, "Alex")
        self.assertIn("[PHONE_NUMBER]", msgs[0].content)
        self.assertNotIn("+1 555-019-2831", msgs[0].content)

        # Second message from user, outgoing, entity text merged
        self.assertTrue(msgs[1].is_user)
        self.assertEqual(msgs[1].content, "Sounds good! Check https://example.com for details")

    def test_fact_miner_parsing(self):
        from backend.ingestion.fact_miner import FactMiner
        from backend.models import ChatMessage

        # Mock LLM that returns JSON
        class MockLLM:
            model = "test-model"
            class client:
                class models:
                    @staticmethod
                    def generate_content(*args, **kwargs):
                        class Response:
                            text = json.dumps([
                                {"category": "preference", "fact": "Loves hiking in nature", "confidence": 0.95},
                                {"category": "pet", "fact": "Has a golden retriever named Sam", "confidence": 0.9},
                            ])
                        return Response()

        miner = FactMiner(MockLLM())
        msgs = [
            ChatMessage(sender="Alice", content="I really love hiking in nature every weekend", timestamp=datetime.utcnow(), is_user=False),
            ChatMessage(sender="Me", content="nice do you have any pets?", timestamp=datetime.utcnow(), is_user=True),
            ChatMessage(sender="Alice", content="yes a golden retriever named Sam!", timestamp=datetime.utcnow(), is_user=False),
            ChatMessage(sender="Me", content="thats awesome", timestamp=datetime.utcnow(), is_user=True),
        ]
        mined = miner.mine_facts(msgs, "contact-123", "Alice")
        self.assertEqual(len(mined), 2)
        self.assertEqual(mined[0].category, "preference")
        self.assertEqual(mined[0].fact, "Loves hiking in nature")
        self.assertEqual(mined[1].category, "pet")
        self.assertEqual(mined[1].fact, "Has a golden retriever named Sam")

    def test_fact_api_endpoints(self):
        from fastapi.testclient import TestClient
        from backend.main import app, SERVER_API_TOKEN

        client = TestClient(app, headers={"X-Talking-Token": SERVER_API_TOKEN})

        # 1. Create a test contact
        create_res = client.post("/api/contacts", json={"name": "API Test Contact"})
        self.assertEqual(create_res.status_code, 200)
        contact_id = create_res.json()["id"]

        # 2. Add a fact
        add_res = client.post(
            f"/api/contacts/{contact_id}/facts",
            json={"category": "work", "fact": "Works remotely as a UX researcher", "confidence": 0.9},
        )
        self.assertEqual(add_res.status_code, 200)
        fact_id = add_res.json()["id"]
        self.assertEqual(add_res.json()["category"], "work")

        # 3. Get facts
        get_res = client.get(f"/api/contacts/{contact_id}/facts")
        self.assertEqual(get_res.status_code, 200)
        facts = get_res.json()
        self.assertTrue(any(f["id"] == fact_id for f in facts))

        # 4. Delete fact
        del_res = client.delete(f"/api/facts/{fact_id}")
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json()["status"], "deleted")

        # 5. Cleanup test contact
        client.delete(f"/api/contacts/{contact_id}")

    def test_copilot_draft_endpoint(self):
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        from backend.main import app, db, SERVER_API_TOKEN

        mock_variants = {
            "chill": {"text": "hey chill", "bubbles": ["hey chill"]},
            "direct": {"text": "hey direct", "bubbles": ["hey direct"]},
            "banter": {"text": "hey banter", "bubbles": ["hey banter"]}
        }
        with patch("backend.main.llm.generate_variants", return_value=mock_variants):
            client = TestClient(app, headers={"X-Talking-Token": SERVER_API_TOKEN})

            copilot_res = client.post(
                "/api/copilot/draft",
                json={
                    "contact_name": "Copilot Friend",
                    "incoming_message": "hey what are you doing tonight",
                    "mood": "chill",
                    "pro_mode": False,
                },
            )
            self.assertEqual(copilot_res.status_code, 200)
            data = copilot_res.json()
            self.assertIn("draft", data)
            self.assertIn("variants", data)
            self.assertEqual(data["contact_name"], "Copilot Friend")
            contact_id = data["contact_id"]

            # Ensure contact exists in DB
            contact = db.get_contact(contact_id)
            self.assertIsNotNone(contact)
            self.assertEqual(contact.name, "Copilot Friend")

            # Cleanup
            db.delete_contact(contact_id)


class TestPerformanceAndRobustness(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp_dir.name) / "test.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_clean_json_sanitizer(self):
        """Verifies that model output with fences, preambles, and trailing commas parses robustly."""
        from backend.llm import GeminiLLM
        import json

        # Preambles + markdown fences + trailing commas
        raw_output = """Here are the three distinct reply options you requested:
```json
{
  "chill": "all good",
  "direct": "sounds great, let's meet at 7",
  "banter": "only if you buy the first round 💀",
}
```
Hope this helps!"""

        cleaned = GeminiLLM._clean_json_text(raw_output)
        data = json.loads(cleaned)
        self.assertEqual(data["chill"], "all good")
        self.assertEqual(data["direct"], "sounds great, let's meet at 7")
        self.assertEqual(data["banter"], "only if you buy the first round 💀")

    def test_db_batch_insert_and_indexes(self):
        """Verifies single-transaction batch message insertions and index creation."""
        from backend.models import Contact, Message
        from datetime import datetime

        contact = self.db.add_contact(Contact(name="Batch Contact"))
        messages = [
            Message(
                contact_id=contact.id,
                role="you" if i % 2 == 0 else "them",
                content=f"Message {i}",
                timestamp=datetime.now(),
            )
            for i in range(20)
        ]

        self.db.add_messages_batch(messages)
        saved = self.db.get_messages(contact.id, limit=50)
        self.assertEqual(len(saved), 20)

        # Check indexes exist
        with self.db._connection() as conn:
            indexes = [r["name"] for r in conn.execute("PRAGMA index_list('messages')").fetchall()]
            self.assertIn("idx_messages_contact_timestamp", indexes)

    def test_recent_user_messages_extraction(self):
        """Verifies extraction of user outgoing texts for dynamic few-shot style mimicry."""
        from backend.models import Contact, Message
        from datetime import datetime

        contact = self.db.add_contact(Contact(name="Style Contact"))
        self.db.add_message(Message(contact_id=contact.id, role="you", content="nah was too tired haha"))
        self.db.add_message(Message(contact_id=contact.id, role="them", content="how was your day"))
        self.db.add_message(Message(contact_id=contact.id, role="you", content="yeah should be down!"))

        user_msgs = self.db.get_recent_user_messages(contact_id=contact.id, n=5)
        self.assertEqual(len(user_msgs), 2)
        self.assertIn("nah was too tired haha", user_msgs)
        self.assertIn("yeah should be down!", user_msgs)

    def test_multi_bubble_variant_parsing(self):
        """Verifies that generate_variants handles lists of bubbles as well as multi-line strings."""
        from unittest.mock import MagicMock
        from backend.llm import GeminiLLM
        import json

        llm = GeminiLLM.__new__(GeminiLLM)
        llm.model = "test-model"
        llm.client = MagicMock()

        # Mock API returning multi-bubble array JSON
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "chill": ["wait really", "i thought that was closed monday"],
            "direct": ["yeah for sure", "let's do 7pm"],
            "banter": "bold of you to assume i can cook // order thai instead? 💀",
        })
        llm.client.models.generate_content.return_value = mock_response

        variants = llm.generate_variants("sys_instruction", "user_msg")

        # Verify chill variant has 2 split bubbles and text joined by newline
        self.assertEqual(variants["chill"]["bubbles"], ["wait really", "i thought that was closed monday"])
        self.assertEqual(variants["chill"]["text"], "wait really\ni thought that was closed monday")

        # Verify direct variant has 2 bubbles
        self.assertEqual(variants["direct"]["bubbles"], ["yeah for sure", "let's do 7pm"])

        # Verify banter parsed // delimiter into 2 bubbles
        self.assertEqual(len(variants["banter"]["bubbles"]), 2)
        self.assertIn("bold of you to assume i can cook", variants["banter"]["bubbles"])

    def test_multi_bubble_copilot_endpoint(self):
        """Verifies that /api/copilot/draft returns the bubbles array."""
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        from backend.main import app, db, SERVER_API_TOKEN

        mock_variants = {
            "chill": {"text": "hey there", "bubbles": ["hey there"]},
            "direct": {"text": "yes I am", "bubbles": ["yes I am"]},
            "banter": {"text": "maybe, what's up?", "bubbles": ["maybe,", "what's up?"]}
        }
        with patch("backend.main.llm.generate_variants", return_value=mock_variants):
            client = TestClient(app, headers={"X-Talking-Token": SERVER_API_TOKEN})
            res = client.post(
                "/api/copilot/draft",
                json={
                    "contact_name": "Bubble Friend",
                    "incoming_message": "are you free this weekend?",
                    "mood": "chill",
                },
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertIn("bubbles", data)
            self.assertIsInstance(data["bubbles"], list)
            self.assertIn("variants", data)
            for v in data["variants"]:
                self.assertIn("bubbles", v)
                self.assertIsInstance(v["bubbles"], list)

            # Cleanup
            db.delete_contact(data["contact_id"])

    def test_watcher_endpoints(self):
        """Verifies start, status, and stop endpoints for Playwright Instagram watcher."""
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        from backend.main import app, db, SERVER_API_TOKEN
        from backend.models import Contact

        test_c = db.add_contact(Contact(name="Watcher Test Contact"))
        client = TestClient(app, headers={"X-Talking-Token": SERVER_API_TOKEN})

        # Status check
        res = client.get("/api/watcher/status")
        self.assertEqual(res.status_code, 200)
        self.assertIn("running", res.json())

        # Start watcher with mock
        with patch("backend.instagram_watcher.start_watcher") as mock_start:
            start_res = client.post("/api/watcher/start", json={
                "contact_id": test_c.id,
                "instagram_url": "https://www.instagram.com/direct/t/123456789/",
                "mood": "chill",
                "full_auto": False
            })
            self.assertEqual(start_res.status_code, 200)
            mock_start.assert_called_once()

        # Stop watcher with mock
        with patch("backend.instagram_watcher.stop_watcher") as mock_stop:
            stop_res = client.post("/api/watcher/stop")
            self.assertEqual(stop_res.status_code, 200)
            mock_stop.assert_called_once()

        # Cleanup
        db.delete_contact(test_c.id)

    def test_update_message_and_media_handling(self):
        """Verifies database message updating and media/thumbnail metadata preservation."""
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        import base64
        from backend.main import app, db, SERVER_API_TOKEN, llm
        from backend.models import Contact, Message

        contact = db.add_contact(Contact(name="Media Test Contact"))
        client = TestClient(app, headers={"X-Talking-Token": SERVER_API_TOKEN})

        # 1. Add initial un-described media placeholder message
        msg = db.add_message(Message(
            contact_id=contact.id,
            role="them",
            content="[Sent a photo]",
            metadata={"is_media": True, "media_url": "https://example.com/photo.jpg"}
        ))
        self.assertGreater(msg.id, 0)

        # 2. Test describe_media endpoint updates the placeholder in-place without duplicating
        fake_b64 = base64.b64encode(b"fake_jpeg_bytes").decode("utf-8")
        with patch.object(llm, "describe_image", return_value="A fluffy white cat lounging on a sofa"):
            resp = client.post("/api/instagram/describe_media", json={
                "contact_id": contact.id,
                "media_type": "[Sent a photo]",
                "image_base64": fake_b64,
            })
            self.assertEqual(resp.status_code, 200)

        # Verify still only 1 message, updated with vision description and thumbnail URI
        messages_after = db.get_recent_messages(contact.id, n=10)
        self.assertEqual(len(messages_after), 1)
        self.assertEqual(messages_after[0].id, msg.id)
        self.assertIn("A fluffy white cat lounging on a sofa", messages_after[0].content)
        self.assertTrue(messages_after[0].metadata.get("thumbnail").startswith("data:image/jpeg;base64,"))

        # 3. Direct test of update_message
        success = db.update_message(
            msg.id,
            content="[Sent a photo]: Updated description",
            metadata={"is_media": True, "description": "Updated description"}
        )
        self.assertTrue(success)
        re_fetched = db.get_recent_messages(contact.id, n=5)
        self.assertEqual(re_fetched[0].content, "[Sent a photo]: Updated description")

        # Cleanup
        db.delete_contact(contact.id)


if __name__ == "__main__":
    unittest.main()
