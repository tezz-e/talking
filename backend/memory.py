"""
Talking — ChromaDB Vector Memory Store

Persistent semantic search over chat history using ChromaDB
with Gemini embeddings for retrieval-augmented generation.
"""

import json
import logging
import math
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Optional, Any
import time

try:
    import chromadb
    from chromadb.config import Settings
    from chromadb.api.types import EmbeddingFunction, Documents, Embeddings
except Exception as exc:
    chromadb = None
    EmbeddingFunction = object
    Documents = list[str]
    Embeddings = list[list[float]]
    _CHROMA_IMPORT_ERROR = exc
    _EmbeddingFunctionBase = object
else:
    _CHROMA_IMPORT_ERROR = None
    _EmbeddingFunctionBase = EmbeddingFunction[Documents]

logger = logging.getLogger(__name__)

# ─── Default storage path ────────────────────────────────────────────────────

_DEFAULT_CHROMA_DIR = Path(__file__).resolve().parent.parent / "data" / "db" / "chroma"
_COLLECTION_NAME = "chat_history"


class GeminiEmbeddingFunction(_EmbeddingFunctionBase):
    """
    ChromaDB-compatible embedding function that delegates to GeminiLLM.embed_batch().
    """

    def __init__(self, llm):
        """
        Args:
            llm: A GeminiLLM instance with .embed() and .embed_batch() methods.
        """
        self._llm = llm

    def __call__(self, input: Documents) -> Embeddings:
        """Embed a list of documents using Gemini.
        
        This is used by ChromaDB for query-time embedding (single queries).
        For bulk ingestion, add_messages() handles batching directly.
        """
        if not input:
            return []
        # For single queries (1-2 docs), just embed directly
        return self._llm.embed_batch(input)


class SQLiteVectorStore:
    """Small persistent vector store used when Chroma/ONNX is unavailable."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vectors (
                    id TEXT PRIMARY KEY,
                    document TEXT NOT NULL,
                    embedding TEXT NOT NULL,
                    contact_id TEXT DEFAULT '',
                    timestamp TEXT DEFAULT '',
                    is_user INTEGER DEFAULT 0
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_vectors_contact ON vectors(contact_id)"
            )

    @staticmethod
    def _cosine_distance(a: list[float], b: list[float]) -> float:
        dot = 0.0
        norm_a = 0.0
        norm_b = 0.0
        for x, y in zip(a, b):
            dot += x * y
            norm_a += x * x
            norm_b += y * y
        if not norm_a or not norm_b:
            return 1.0
        return 1.0 - (dot / (math.sqrt(norm_a) * math.sqrt(norm_b)))

    def add(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> None:
        rows = []
        for vector_id, document, metadata, embedding in zip(
            ids, documents, metadatas, embeddings
        ):
            rows.append(
                (
                    vector_id,
                    document,
                    json.dumps(embedding),
                    metadata.get("contact_id", ""),
                    str(metadata.get("timestamp", "")),
                    int(bool(metadata.get("is_user", False))),
                )
            )

        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO vectors
                    (id, document, embedding, contact_id, timestamp, is_user)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def query(
        self,
        query_embedding: list[float],
        query_text: str = "",
        contact_id: Optional[str] = None,
        n_results: int = 5,
    ) -> list[dict]:
        sql = "SELECT * FROM vectors"
        params: list[Any] = []
        if contact_id:
            sql += " WHERE contact_id = ?"
            params.append(contact_id)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        query_terms = self._tokenize(query_text)
        scored = []
        for row in rows:
            embedding = json.loads(row["embedding"])
            distance = self._cosine_distance(query_embedding, embedding)
            hybrid_distance = distance
            if query_terms:
                doc_terms = self._tokenize(row["document"])
                overlap = len(query_terms & doc_terms)
                coverage = overlap / max(len(query_terms), 1)
                hybrid_distance -= min(0.25, coverage * 0.18)
                if query_text and query_text.lower() in row["document"].lower():
                    hybrid_distance -= 0.2
            scored.append(
                {
                    "text": row["document"],
                    "metadata": {
                        "contact_id": row["contact_id"],
                        "timestamp": row["timestamp"],
                        "is_user": bool(row["is_user"]),
                    },
                    "distance": max(0.0, hybrid_distance),
                }
            )

        scored.sort(key=lambda item: item["distance"])
        return scored[:n_results]

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9']+", text.lower())
            if len(token) > 2
        }

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM vectors").fetchone()
        return int(row["count"]) if row else 0

    def get(self, where: Optional[dict[str, Any]] = None) -> dict[str, list[str]]:
        sql = "SELECT id FROM vectors"
        params: list[Any] = []
        if where and where.get("contact_id"):
            sql += " WHERE contact_id = ?"
            params.append(where["contact_id"])
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return {"ids": [row["id"] for row in rows]}

    def delete(self, where: Optional[dict[str, Any]] = None) -> None:
        sql = "DELETE FROM vectors"
        params: list[Any] = []
        if where and where.get("contact_id"):
            sql += " WHERE contact_id = ?"
            params.append(where["contact_id"])
        with self._connect() as conn:
            conn.execute(sql, params)


class MemoryStore:
    """
    Semantic memory layer backed by ChromaDB.

    Stores chunked chat messages with metadata (contact_id, timestamp,
    is_user) and supports filtered similarity search for RAG context.
    """

    def __init__(self, llm, chroma_dir: str | Path | None = None):
        """
        Args:
            llm:        A GeminiLLM instance for embedding.
            chroma_dir: Directory for persistent ChromaDB storage.
        """
        self.chroma_dir = Path(chroma_dir) if chroma_dir else _DEFAULT_CHROMA_DIR
        self.chroma_dir.mkdir(parents=True, exist_ok=True)

        self._llm = llm
        self._embedding_fn = GeminiEmbeddingFunction(llm)
        self._using_chroma = chromadb is not None

        if self._using_chroma:
            self._client = chromadb.PersistentClient(
                path=str(self.chroma_dir),
                settings=Settings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=_COLLECTION_NAME,
                embedding_function=self._embedding_fn,
                metadata={"hnsw:space": "cosine"},
            )
        else:
            logger.info(
                "Using SQLite vector memory fallback because ChromaDB/ONNX did not load."
            )
            self._client = None
            self._collection = SQLiteVectorStore(
                self.chroma_dir / "fallback_vectors.sqlite3"
            )
        logger.info(
            "MemoryStore initialized — %d vectors in collection '%s'",
            self._collection.count(),
            _COLLECTION_NAME,
        )

    # ── Public API ────────────────────────────────────────────────────────

    def add_messages(
        self,
        chunks: list[dict],
        progress_callback=None,
    ) -> int:
        """
        Add message chunks to the vector store with rate-limit-safe pacing.

        Embeds in micro-batches of 5 with 5-second delays between calls
        to stay safely within Gemini free-tier limits (15 RPM, 1000 RPD,
        30K TPM).  Pre-computed embeddings are passed directly to ChromaDB
        so it never triggers its own auto-embedding.

        Each chunk dict should contain:
            text        (str):  The message / exchange text.
            contact_id  (str):  FK to the contact.
            timestamp   (str):  ISO-8601 timestamp string.
            is_user     (bool): True if this is the user's message.

        Args:
            progress_callback: Optional callable(done, total) for progress.

        Returns:
            Number of chunks added.
        """
        if not chunks:
            return 0

        EMBED_BATCH = 30   # texts per API call
        DELAY_SECS  = 30   # seconds between API calls

        total = len(chunks)
        added = 0

        for i in range(0, total, EMBED_BATCH):
            batch = chunks[i : i + EMBED_BATCH]

            batch_ids = [str(uuid.uuid4()) for _ in batch]
            batch_docs = [c["text"] for c in batch]
            batch_meta = [
                {
                    "contact_id": c.get("contact_id", ""),
                    "timestamp": str(c.get("timestamp", "")),
                    "is_user": c.get("is_user", False),
                }
                for c in batch
            ]

            # Embed this micro-batch (uses _retry internally)
            print(f"[MEMORY] Calling embed_batch for batch {i//EMBED_BATCH + 1}...")
            embeddings = self._embedding_fn._llm.embed_batch(batch_docs)
            print(f"[MEMORY] Completed embed_batch for batch {i//EMBED_BATCH + 1}. Got {len(embeddings)} vectors.")

            # Store with pre-computed embeddings so Chroma never auto-embeds.
            store_name = "ChromaDB collection" if self._using_chroma else "SQLite vector store"
            print(f"[MEMORY] Writing to {store_name}...")
            self._collection.add(
                ids=batch_ids,
                documents=batch_docs,
                metadatas=batch_meta,
                embeddings=embeddings,
            )
            print(f"[MEMORY] {store_name} write complete.")

            added += len(batch)
            if progress_callback:
                progress_callback(added, total)

            logger.info(
                "Embedded batch %d/%d (%d chunks done)",
                (i // EMBED_BATCH) + 1,
                (total + EMBED_BATCH - 1) // EMBED_BATCH,
                added,
            )

            # Pace — skip delay after the last batch
            if i + EMBED_BATCH < total:
                time.sleep(DELAY_SECS)

        logger.info("Added %d chunks to memory store.", added)
        return added

    def search(
        self,
        query: str,
        contact_id: Optional[str] = None,
        n_results: int = 5,
    ) -> list[dict]:
        """
        Semantic similarity search over stored messages.

        Args:
            query:      The search query text.
            contact_id: Optional filter — only search within this contact's messages.
            n_results:  Maximum number of results to return.

        Returns:
            List of dicts: {text, metadata, distance}.
        """
        # Guard against empty collection
        if self._collection.count() == 0:
            return []

        if self._using_chroma:
            target_n = n_results
            if contact_id:
                kwargs["where"] = {"contact_id": contact_id}
                try:
                    matching_items = self._collection.get(where={"contact_id": contact_id})
                    matching_count = len(matching_items.get("ids", [])) if matching_items else 0
                    if matching_count == 0:
                        return []
                    target_n = min(n_results, matching_count)
                except Exception as e:
                    logger.warning("Failed counting contact chunks: %s", e)
            else:
                target_n = min(n_results, self._collection.count() or 1)

            kwargs["n_results"] = max(1, target_n)

            try:
                results = self._collection.query(**kwargs)
            except Exception as e:
                logger.warning(
                    "Chroma query failed with kwargs %s: %s; retrying with n_results=1",
                    kwargs,
                    e,
                )
                try:
                    kwargs["n_results"] = 1
                    results = self._collection.query(**kwargs)
                except Exception as inner_e:
                    logger.error("Chroma query retry failed: %s", inner_e)
                    return []

            output = []
            if results and results.get("documents"):
                docs = results["documents"][0]
                metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
                dists = results["distances"][0] if results.get("distances") else [0.0] * len(docs)

                for doc, meta, dist in zip(docs, metas, dists):
                    output.append(
                        {
                            "text": doc,
                            "metadata": meta,
                            "distance": dist,
                        }
                    )

            return output

        query_embedding = self._llm.embed(query)
        return self._collection.query(
            query_embedding=query_embedding,
            query_text=query,
            contact_id=contact_id,
            n_results=n_results,
        )

    def get_collection_count(self) -> int:
        """Return the number of vectors in the collection."""
        return self._collection.count()

    def clear_contact(self, contact_id: str) -> int:
        """
        Delete all vectors associated with a contact.

        Args:
            contact_id: The contact whose memories should be cleared.

        Returns:
            Number of records that existed before deletion (approximate).
        """
        # Get IDs to delete
        existing = self._collection.get(
            where={"contact_id": contact_id},
        )

        count = len(existing["ids"]) if existing and existing.get("ids") else 0

        if count > 0:
            self._collection.delete(
                where={"contact_id": contact_id},
            )
            logger.info("Cleared %d vectors for contact %s", count, contact_id)

        return count
