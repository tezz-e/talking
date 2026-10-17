import sys
from dotenv import load_dotenv

load_dotenv()
from backend.llm import GeminiLLM

print("Initializing GeminiLLM...")
llm = GeminiLLM()

print("Testing embed()...")
try:
    res1 = llm.embed("Hello world")
    print("embed() successful, length:", len(res1))
except Exception as e:
    print("embed() failed:", e)

print("Testing embed_batch()...")
try:
    res2 = llm.embed_batch(["Hello world", "Test string"])
    print("embed_batch() successful, length:", len(res2))
except Exception as e:
    print("embed_batch() failed:", e)
