import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def log(msg):
    print(msg)
    with open("progress.txt", "a") as f:
        f.write(msg + "\n")
        f.flush()

if os.path.exists("progress.txt"):
    os.remove("progress.txt")

log("Step 1: Importing packages...")
import chromadb
from google import genai
from google.genai import types
log("Import complete.")

log("Step 2: Initializing DatabaseManager...")
from backend.database import DatabaseManager
db = DatabaseManager("data/db/talking.db")
log("DatabaseManager complete.")

log("Step 3: Initializing GeminiLLM...")
from backend.llm import GeminiLLM
llm = GeminiLLM()
log("GeminiLLM complete.")

log("Step 4: Creating PersistentClient...")
from chromadb.config import Settings
client = chromadb.PersistentClient(
    path="data/db/chroma",
    settings=Settings(anonymized_telemetry=False)
)
log("PersistentClient complete.")

log("Step 5: Initializing GeminiEmbeddingFunction...")
from backend.memory import GeminiEmbeddingFunction
embedding_fn = GeminiEmbeddingFunction(llm)
log("GeminiEmbeddingFunction complete.")

log("Step 6: Getting or creating collection...")
collection = client.get_or_create_collection(
    name="chat_history",
    embedding_function=embedding_fn,
    metadata={"hnsw:space": "cosine"},
)
log("Collection get_or_create complete.")

log("Step 7: Getting collection count...")
count = collection.count()
log(f"Collection count: {count}")
