"""
Script to mirror Arnav's full conversational context, memory, dossier,
callback overrides, and history onto Maneet (Tez) for the demo.
"""

import json
import sqlite3
import time
import sys
import os
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

from backend.main import memory, db

DB_PATH = Path("data/db/talking.db")
ARNAV_ID = "227995a0-4ab7-4e50-8179-3b8113a5b267"
MANEET_ID = "a38db0e1-592b-46ae-bbb8-db0ae36de0e5"

def run_mirroring():
    print("=" * 60)
    print("MIRRORING CONTEXT FROM ARNAV -> MANEET (TEZ)")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Update Contact Dossier
    print("\n1. Updating Contact Dossier for Maneet...")
    cursor.execute("SELECT * FROM contacts WHERE id = ?", (ARNAV_ID,))
    arnav_row = dict(cursor.fetchone())

    interests = ["robotics", "cricket", "football", "basketball", "table tennis", "math", "physics", "uk rap"]
    jokes = ["how she left him", "no one loves u", "cench", "uk rap", "miami beach", "sprinter"]

    cursor.execute("""
        UPDATE contacts
        SET relationship_stage = ?,
            how_you_know = ?,
            their_interests = ?,
            inside_jokes = ?,
            notes = ?,
            convo_goal = ?,
            my_impression = ?,
            strategy_note = ?,
            updated_at = datetime('now')
        WHERE id = ?
    """, (
        "best_friend",
        "long time friend & creative collaborator",
        json.dumps(interests),
        json.dumps(jokes),
        "he has mood swings; deep shared lore and inside jokes across UK rap, basketball, and tech",
        "just_vibing",
        "witty, dry, teases about music taste, close friend banter",
        "tease about music taste (UK rap / Dave / Central Cee), match dry energy, keep replies concise and effortless",
        MANEET_ID
    ))
    conn.commit()
    print("   [OK] Contact Dossier updated.")

    # 2. Mirror Callback Overrides
    print("\n2. Mirroring Callback Overrides...")
    cursor.execute("SELECT * FROM callback_overrides WHERE contact_id = ?", (ARNAV_ID,))
    arnav_overrides = [dict(r) for r in cursor.fetchall()]

    # Also add useful variants
    overrides_to_add = list(arnav_overrides)
    extra_variants = [
        {
            "trigger_text": "she dont listen to uk rap",
            "trigger_norm": "she dont listen to uk rap",
            "response_text": "if it aint dave or cench",
            "source": "demo_seed"
        },
        {
            "trigger_text": "she don't listen to uk rap",
            "trigger_norm": "she dont listen to uk rap",
            "response_text": "if it aint dave or cench",
            "source": "demo_seed"
        },
        {
            "trigger_text": "who is that",
            "trigger_norm": "who is that",
            "response_text": "told her my name is cench",
            "source": "demo_seed"
        }
    ]

    added_overrides = 0
    for ov in overrides_to_add:
        # Check if already exists for Maneet
        cursor.execute(
            "SELECT id FROM callback_overrides WHERE contact_id = ? AND trigger_norm = ?",
            (MANEET_ID, ov["trigger_norm"])
        )
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO callback_overrides (contact_id, trigger_text, trigger_norm, response_text, source, uses)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                MANEET_ID,
                ov["trigger_text"],
                ov["trigger_norm"],
                ov["response_text"],
                ov.get("source", "mirrored_seed"),
                ov.get("uses", 1)
            ))
            added_overrides += 1

    for ev in extra_variants:
        cursor.execute(
            "SELECT id FROM callback_overrides WHERE contact_id = ? AND trigger_norm = ?",
            (MANEET_ID, ev["trigger_norm"])
        )
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO callback_overrides (contact_id, trigger_text, trigger_norm, response_text, source, uses)
                VALUES (?, ?, ?, ?, ?, 1)
            """, (
                MANEET_ID,
                ev["trigger_text"],
                ev["trigger_norm"],
                ev["response_text"],
                ev["source"]
            ))
            added_overrides += 1

    conn.commit()
    print(f"   [OK] Added {added_overrides} callback overrides for Maneet.")

    # 3. Mirror ChromaDB Vector Memories
    print("\n3. Mirroring ChromaDB Vector Memories...")
    col = memory._collection
    arnav_vectors = col.get(where={"contact_id": ARNAV_ID}, include=["documents", "metadatas", "embeddings"])
    
    total_arnav_chunks = len(arnav_vectors["ids"])
    print(f"   Retrieved {total_arnav_chunks} vector chunks from Arnav.")

    # Check how many already exist for Maneet
    maneet_existing = col.get(where={"contact_id": MANEET_ID})
    existing_ids = set(maneet_existing["ids"])
    print(f"   Maneet currently has {len(existing_ids)} vector chunks.")

    new_ids = []
    new_docs = []
    new_metas = []
    new_embeddings = []

    for i in range(total_arnav_chunks):
        orig_id = arnav_vectors["ids"][i]
        cloned_id = f"maneet_mirror_{orig_id}"
        if cloned_id in existing_ids:
            continue

        doc = arnav_vectors["documents"][i]
        meta = dict(arnav_vectors["metadatas"][i] or {})
        meta["contact_id"] = MANEET_ID
        meta["mirrored_from"] = ARNAV_ID

        new_ids.append(cloned_id)
        new_docs.append(doc)
        new_metas.append(meta)
        if arnav_vectors["embeddings"] is not None:
            new_embeddings.append(arnav_vectors["embeddings"][i])

    if new_ids:
        # Add in batches of 50
        batch_size = 50
        for b in range(0, len(new_ids), batch_size):
            end = min(b + batch_size, len(new_ids))
            kwargs = {
                "ids": new_ids[b:end],
                "documents": new_docs[b:end],
                "metadatas": new_metas[b:end],
            }
            if new_embeddings:
                kwargs["embeddings"] = new_embeddings[b:end]
            col.add(**kwargs)
        print(f"   [OK] Successfully cloned {len(new_ids)} vector chunks to Maneet!")
    else:
        print("   [OK] All vector chunks already mirrored.")

    # 4. Mirror Key Conversation Lore into Message History
    print("\n4. Backfilling Key Conversation Lore into Messages History...")
    cursor.execute("""
        SELECT role, content, ai_draft, was_edited, timestamp, metadata
        FROM messages
        WHERE contact_id = ?
        ORDER BY id ASC
    """, (ARNAV_ID,))
    arnav_msgs = [dict(r) for r in cursor.fetchall()]
    print(f"   Found {len(arnav_msgs)} message records from Arnav.")

    cursor.execute("SELECT content FROM messages WHERE contact_id = ?", (MANEET_ID,))
    existing_maneet_contents = {r["content"].strip() for r in cursor.fetchall()}

    added_msgs = 0
    for m in arnav_msgs:
        content_clean = m["content"].strip()
        if content_clean in existing_maneet_contents:
            continue
        cursor.execute("""
            INSERT INTO messages (contact_id, role, content, ai_draft, was_edited, timestamp, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            MANEET_ID,
            m["role"],
            m["content"],
            m["ai_draft"],
            m["was_edited"],
            m["timestamp"],
            m["metadata"]
        ))
        existing_maneet_contents.add(content_clean)
        added_msgs += 1

    conn.commit()
    print(f"   [OK] Added {added_msgs} historic messages to Maneet.")

    conn.close()

    print("\n" + "=" * 60)
    print("MIRRORING COMPLETE! Verifying RAG Context Assembly...")
    print("=" * 60)

    from backend.main import context_assembler
    sys_prompt, user_msg, memories = context_assembler.assemble(
        contact_id=MANEET_ID,
        incoming_message="she dont listen to uk rap",
        mood="chill"
    )
    print(f"1. RAG Memories retrieved: {len(memories)}")
    for i, m in enumerate(memories[:3]):
        print(f"   Memory {i+1}: {m[:75]}...")

    callback_direct = context_assembler.get_learned_callback_reply(
        contact_id=MANEET_ID,
        incoming_message="she dont listen to uk rap"
    )
    print(f"2. Callback direct reply for 'she dont listen to uk rap': {callback_direct!r}")

    callback_direct2 = context_assembler.get_learned_callback_reply(
        contact_id=MANEET_ID,
        incoming_message="wagwan"
    )
    print(f"3. Callback direct reply for 'wagwan': {callback_direct2!r}")

    print("\n[SUCCESS] Maneet / Tez is now fully loaded with Arnav's context!")

if __name__ == "__main__":
    run_mirroring()
