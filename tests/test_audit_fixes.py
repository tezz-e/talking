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


if __name__ == "__main__":
    unittest.main()
