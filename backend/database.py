"""
Talking — SQLite Database Manager

Handles all persistent storage: contacts, messages, and facts.
Uses SQLite with JSON serialization for list fields and
context-managed connections for thread safety.
"""

import sqlite3
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from backend.models import Contact, Message, Fact, RelationshipStage


# ─── Default DB path ─────────────────────────────────────────────────────────

_DEFAULT_DB_DIR = Path(__file__).resolve().parent.parent / "data" / "db"
_DEFAULT_DB_PATH = _DEFAULT_DB_DIR / "talking.db"


_ALLOWED_CONTACT_COLUMNS = frozenset({
    "name",
    "relationship_stage",
    "how_you_know",
    "their_interests",
    "inside_jokes",
    "style_notes",
    "notes",
    "convo_goal",
    "my_impression",
    "strategy_note",
    "updated_at",
})


class DatabaseManager:
    """
    Thread-safe SQLite database manager for the Talking backend.

    Stores contacts, messages, and extracted facts.
    List fields (their_interests, inside_jokes) are JSON-serialized.
    """

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    # ── Connection helpers ────────────────────────────────────────────────

    @contextmanager
    def _connection(self):
        """Yield a thread-safe SQLite connection with row factory."""
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
        conn.execute("PRAGMA foreign_keys=ON;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_tables(self):
        """Create tables if they don't exist."""
        with self._connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS contacts (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    relationship_stage TEXT DEFAULT 'acquaintance',
                    how_you_know TEXT DEFAULT '',
                    their_interests TEXT DEFAULT '[]',
                    inside_jokes TEXT DEFAULT '[]',
                    style_notes TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    convo_goal TEXT DEFAULT 'just_vibing',
                    my_impression TEXT DEFAULT '',
                    strategy_note TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contact_id TEXT REFERENCES contacts(id),
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    ai_draft TEXT,
                    was_edited BOOLEAN DEFAULT 0,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contact_id TEXT REFERENCES contacts(id),
                    category TEXT NOT NULL,
                    fact TEXT NOT NULL,
                    source TEXT DEFAULT '',
                    confidence REAL DEFAULT 0.8,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS callback_overrides (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contact_id TEXT REFERENCES contacts(id),
                    trigger_text TEXT NOT NULL,
                    trigger_norm TEXT NOT NULL,
                    response_text TEXT NOT NULL,
                    source TEXT DEFAULT 'approved_edit',
                    uses INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_callback_overrides_contact
                    ON callback_overrides(contact_id);

                CREATE INDEX IF NOT EXISTS idx_messages_contact_timestamp
                    ON messages(contact_id, timestamp DESC, id DESC);

                CREATE INDEX IF NOT EXISTS idx_messages_role
                    ON messages(role, timestamp DESC);

                CREATE INDEX IF NOT EXISTS idx_facts_contact
                    ON facts(contact_id);
                """
            )

            # Auto-migrate any missing columns on existing contacts table
            cols = [r["name"] for r in conn.execute("PRAGMA table_info(contacts)").fetchall()]
            if "convo_goal" not in cols:
                conn.execute("ALTER TABLE contacts ADD COLUMN convo_goal TEXT DEFAULT 'just_vibing'")
            if "my_impression" not in cols:
                conn.execute("ALTER TABLE contacts ADD COLUMN my_impression TEXT DEFAULT ''")
            if "strategy_note" not in cols:
                conn.execute("ALTER TABLE contacts ADD COLUMN strategy_note TEXT DEFAULT ''")

    # ── Row → Model helpers ───────────────────────────────────────────────

    @staticmethod
    def _row_to_contact(row: sqlite3.Row) -> Contact:
        """Convert a database row into a Contact model."""
        d = dict(row)
        d["their_interests"] = json.loads(d.get("their_interests", "[]"))
        d["inside_jokes"] = json.loads(d.get("inside_jokes", "[]"))
        d["relationship_stage"] = RelationshipStage(d.get("relationship_stage", "acquaintance"))
        d["convo_goal"] = d.get("convo_goal") or "just_vibing"
        d["my_impression"] = d.get("my_impression") or ""
        d["strategy_note"] = d.get("strategy_note") or ""
        return Contact(**d)

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> Message:
        """Convert a database row into a Message model."""
        d = dict(row)
        d["was_edited"] = bool(d.get("was_edited", 0))
        d["metadata"] = json.loads(d.get("metadata", "{}"))
        return Message(**d)

    @staticmethod
    def _row_to_fact(row: sqlite3.Row) -> Fact:
        """Convert a database row into a Fact model."""
        return Fact(**dict(row))

    # ══════════════════════════════════════════════════════════════════════
    #  CONTACTS CRUD
    # ══════════════════════════════════════════════════════════════════════

    def add_contact(self, contact: Contact) -> Contact:
        """Insert a new contact and return it."""
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO contacts
                    (id, name, relationship_stage, how_you_know,
                     their_interests, inside_jokes, style_notes, notes,
                     convo_goal, my_impression, strategy_note,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    contact.id,
                    contact.name,
                    contact.relationship_stage.value,
                    contact.how_you_know,
                    json.dumps(contact.their_interests),
                    json.dumps(contact.inside_jokes),
                    contact.style_notes,
                    contact.notes,
                    getattr(contact, "convo_goal", "just_vibing"),
                    getattr(contact, "my_impression", ""),
                    getattr(contact, "strategy_note", ""),
                    contact.created_at.isoformat(sep=" "),
                    contact.updated_at.isoformat(sep=" "),
                ),
            )
        return contact

    def get_contact(self, contact_id: str) -> Optional[Contact]:
        """Fetch a single contact by ID, or None."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM contacts WHERE id = ?", (contact_id,)
            ).fetchone()
        return self._row_to_contact(row) if row else None

    def update_contact(self, contact_id: str, updates: Dict[str, Any]) -> Optional[Contact]:
        """
        Partially update a contact.

        `updates` should be a dict of field→value. List fields will be
        JSON-serialized automatically.
        """
        # Whitelist columns to guard against unknown LLM output keys and SQL injection
        updates = {k: v for k, v in updates.items() if k in _ALLOWED_CONTACT_COLUMNS}
        if not updates:
            return self.get_contact(contact_id)

        # JSON-serialize list fields
        for key in ("their_interests", "inside_jokes"):
            if key in updates and isinstance(updates[key], list):
                updates[key] = json.dumps(updates[key])

        # Serialize enum
        if "relationship_stage" in updates:
            val = updates["relationship_stage"]
            if isinstance(val, RelationshipStage):
                updates["relationship_stage"] = val.value

        updates["updated_at"] = datetime.utcnow().isoformat(sep=" ")

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [contact_id]

        with self._connection() as conn:
            conn.execute(
                f"UPDATE contacts SET {set_clause} WHERE id = ?", values
            )
        return self.get_contact(contact_id)

    def list_contacts(self) -> List[Contact]:
        """Return all contacts, ordered by most recently updated."""
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM contacts ORDER BY updated_at DESC"
            ).fetchall()
        return [self._row_to_contact(r) for r in rows]

    def delete_contact(self, contact_id: str) -> bool:
        """Delete a contact and all its messages / facts. Returns True if found."""
        with self._connection() as conn:
            conn.execute("DELETE FROM messages WHERE contact_id = ?", (contact_id,))
            conn.execute("DELETE FROM facts WHERE contact_id = ?", (contact_id,))
            cursor = conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
        return cursor.rowcount > 0

    # ══════════════════════════════════════════════════════════════════════
    #  MESSAGES CRUD
    # ══════════════════════════════════════════════════════════════════════

    def add_message(self, message: Message) -> Message:
        """Insert a message and return it with its assigned ID."""
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO messages
                    (contact_id, role, content, ai_draft, was_edited, timestamp, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.contact_id,
                    message.role,
                    message.content,
                    message.ai_draft,
                    int(message.was_edited),
                    message.timestamp.isoformat(sep=" "),
                    json.dumps(message.metadata or {}),
                ),
            )
            message.id = cursor.lastrowid
        return message

    def add_messages_batch(self, messages: list[Message]) -> list[Message]:
        """Insert multiple messages in a single transaction for maximum write throughput."""
        if not messages:
            return []
        with self._connection() as conn:
            params = [
                (
                    m.contact_id,
                    m.role,
                    m.content,
                    m.ai_draft,
                    int(m.was_edited),
                    m.timestamp.isoformat(sep=" "),
                    json.dumps(m.metadata or {}),
                )
                for m in messages
            ]
            conn.executemany(
                """
                INSERT INTO messages
                    (contact_id, role, content, ai_draft, was_edited, timestamp, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                params,
            )
        return messages

    def get_recent_user_messages(
        self,
        contact_id: Optional[str] = None,
        n: int = 5,
    ) -> List[str]:
        """
        Fetch the user's latest outgoing approved messages (`role='you'`).
        Used for dynamic few-shot style mimicry in LLM generation.
        """
        with self._connection() as conn:
            if contact_id:
                rows = conn.execute(
                    """
                    SELECT content FROM messages
                    WHERE contact_id = ? AND role = 'you'
                    ORDER BY timestamp DESC, id DESC
                    LIMIT ?
                    """,
                    (contact_id, n),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT content FROM messages
                    WHERE role = 'you'
                    ORDER BY timestamp DESC, id DESC
                    LIMIT ?
                    """,
                    (n,),
                ).fetchall()
        return [r["content"] for r in rows if r["content"].strip()]

    def get_messages(
        self,
        contact_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Message]:
        """Get the latest messages for a contact in chronological order."""
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM (
                    SELECT * FROM messages
                    WHERE contact_id = ?
                    ORDER BY timestamp DESC, id DESC
                    LIMIT ? OFFSET ?
                ) sub
                ORDER BY timestamp ASC, id ASC
                """,
                (contact_id, limit, offset),
            ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def get_recent_messages(self, contact_id: str, n: int = 15) -> List[Message]:
        """Get the last N messages for a contact (returned oldest-first)."""
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM (
                    SELECT * FROM messages
                    WHERE contact_id = ?
                    ORDER BY timestamp DESC, id DESC
                    LIMIT ?
                ) sub
                ORDER BY timestamp ASC, id ASC
                """,
                (contact_id, n),
            ).fetchall()
        return [self._row_to_message(r) for r in rows]

    # ══════════════════════════════════════════════════════════════════════
    #  FACTS CRUD
    # ══════════════════════════════════════════════════════════════════════

    def add_fact(self, fact: Fact) -> Fact:
        """Insert a fact and return it with its assigned ID."""
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO facts (contact_id, category, fact, source, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    fact.contact_id,
                    fact.category,
                    fact.fact,
                    fact.source,
                    fact.confidence,
                    fact.created_at.isoformat(sep=" "),
                ),
            )
            fact.id = cursor.lastrowid
        return fact

    def get_facts(self, contact_id: str) -> List[Fact]:
        """Get all facts about a contact."""
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM facts WHERE contact_id = ? ORDER BY created_at DESC",
                (contact_id,),
            ).fetchall()
        return [self._row_to_fact(r) for r in rows]

    def delete_fact(self, fact_id: int) -> bool:
        """Delete a fact by its database ID. Returns True if deleted."""
        with self._connection() as conn:
            cursor = conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
            return cursor.rowcount > 0

    def search_facts(
        self,
        contact_id: Optional[str] = None,
        category: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> List[Fact]:
        """
        Search facts with optional filters.

        Args:
            contact_id: Filter by contact.
            category:   Filter by fact category.
            keyword:    Full-text search within the fact text.
        """
        clauses: list[str] = []
        params: list[Any] = []

        if contact_id:
            clauses.append("contact_id = ?")
            params.append(contact_id)
        if category:
            clauses.append("category = ?")
            params.append(category)
        if keyword:
            clauses.append("fact LIKE ?")
            params.append(f"%{keyword}%")

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        with self._connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM facts {where} ORDER BY confidence DESC, created_at DESC",
                params,
            ).fetchall()
        return [self._row_to_fact(r) for r in rows]

    # ═══════════════════════════════════════════════════════════════════════
    #  CALLBACK OVERRIDES
    # ═══════════════════════════════════════════════════════════════════════

    @staticmethod
    def normalize_callback_text(text: str) -> str:
        """Normalize callback trigger text for matching."""
        import re

        text = text.lower().replace("ain't", "aint").replace("don't", "dont")
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def add_callback_override(
        self,
        contact_id: str,
        trigger_text: str,
        response_text: str,
        source: str = "approved_edit",
    ) -> None:
        """Store or reinforce a user-approved callback response."""
        trigger_norm = self.normalize_callback_text(trigger_text)
        response_text = response_text.strip()
        if not trigger_norm or not response_text:
            return

        with self._connection() as conn:
            existing = conn.execute(
                """
                SELECT id FROM callback_overrides
                WHERE contact_id = ? AND trigger_norm = ? AND response_text = ?
                """,
                (contact_id, trigger_norm, response_text),
            ).fetchone()

            if existing:
                conn.execute(
                    """
                    UPDATE callback_overrides
                    SET uses = uses + 1, updated_at = ?
                    WHERE id = ?
                    """,
                    (datetime.utcnow().isoformat(sep=" "), existing["id"]),
                )
                return

            conn.execute(
                """
                INSERT INTO callback_overrides
                    (contact_id, trigger_text, trigger_norm, response_text, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    contact_id,
                    trigger_text,
                    trigger_norm,
                    response_text,
                    source,
                    datetime.utcnow().isoformat(sep=" "),
                    datetime.utcnow().isoformat(sep=" "),
                ),
            )

    def list_callback_overrides(self, contact_id: str) -> list[dict]:
        """Return callback overrides for a contact."""
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM callback_overrides
                WHERE contact_id = ?
                ORDER BY uses DESC, updated_at DESC
                """,
                (contact_id,),
            ).fetchall()
        return [dict(row) for row in rows]
