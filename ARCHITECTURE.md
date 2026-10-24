# Architecture & System Design Documentation

This document serves as the comprehensive architectural reference for the `Talking` codebase. It outlines core design decisions, component lifecycles, data flows, database schemas, and integration points across the system.

---

## 1. System Philosophy & Objectives

`Talking` is an automated, persona-grounded texting assistant designed to produce human-sounding message drafts. Unlike general conversational models that default to formal customer-service phrasing, `Talking` enforces:
1. **Empirical style mimicry:** Statistical alignment with casing, punctuation avoidance, slang, word count, and double-texting cadence extracted from real past chat logs (`STYLE.md`).
2. **Contextual & relational grounding:** Per-contact relationship stage, inside jokes, facts, and tactical conversation goals.
3. **Semantic memory indexing:** Vector search over historical dialogue chunks via ChromaDB and Gemini embeddings (`gemini-embedding-2`).
4. **Call-and-response & lyric continuation:** Resolving inside jokes and well-known song setups without literal or preachy explanations.
5. **Human-in-the-loop review:** All drafts are reviewed, optionally edited, and approved by the user before clipboard copy or transmission. Approved edits feed back into callback overrides.

---

## 2. Directory Layout & Module Responsibilities

```text
Talking/
├── backend/
│   ├── context.py              # ContextAssembler: gathers history, memories, hints, and builds system prompt
│   ├── database.py             # DatabaseManager: SQLite CRUD for contacts, messages, facts, callback overrides
│   ├── instagram_watcher.py    # Playwright-based Instagram DM live monitor & auto-responder
│   ├── llm.py                  # GeminiLLM: google-genai SDK wrapper (generation, embeddings, multimodal OCR)
│   ├── main.py                 # FastAPI application, REST endpoints, static files mount
│   ├── memory.py               # MemoryStore: ChromaDB wrapper with bounded similarity search & in-memory fallback
│   ├── models.py               # Pydantic schemas (Contact, Message, ChatMessage, GenerateRequest, etc.)
│   ├── personality.py          # PersonalityEngine: loads SOUL/STYLE and renders complete system instructions
│   ├── strategy.py             # StrategyInterpreter: parses steering directives into convo_goal & strategy_note
│   └── ingestion/
│       ├── instagram.py        # InstagramParser: parses Meta JSON export files & handles Latin-1 mojibake
│       ├── whatsapp.py         # WhatsAppParser: parses WhatsApp exported .txt logs
│       ├── telegram.py         # TelegramParser: parses Telegram Desktop JSON exports (result.json)
│       ├── fact_miner.py       # FactMiner: extracts biographical facts & preferences from chat turns
│       ├── pii_scrubber.py     # PIIScrubber: masks credit cards, phone numbers, passwords, auth tokens
│       └── style_extractor.py  # StyleExtractor: computes empirical style metrics & generates STYLE.md
├── data/
│   ├── SOUL.template.md        # Tracked template for core persona & background context
│   ├── STYLE.template.md       # Tracked template for texting style fingerprint
│   └── db/                     # Local SQLite (talking.db) and ChromaDB storage (git-ignored)
├── extension/
│   ├── manifest.json           # Chrome MV3 Extension manifest for WhatsApp Web & Instagram Direct
│   ├── content.js              # DOM scraper, Alt+D trigger, in-page draft injector & approval reporter
│   ├── content.css             # Glassmorphic overlay styling for floating pill & draft modal
│   ├── popup.html / popup.js   # Extension toolbar status popup & shortcut reference
│   ├── talking-copilot.user.js # Standalone Tampermonkey/Violentmonkey userscript (zero install friction)
│   └── README.md               # Copilot installation guide (Userscript vs Chrome Extension)
├── frontend/
│   ├── app.js                  # Frontend client state machine, API calls, event handlers
│   ├── index.html              # Glassmorphic dashboard UI
│   └── style.css               # CSS variables, responsive layout, animations
├── tests/
│   └── test_audit_fixes.py     # Automated unit test suite verifying database, models, context & memory
├── requirements.txt            # Python dependencies
├── run.py                      # Development entrypoint (uvicorn launcher)
└── README.md                   # Public repository documentation
```

---

## 3. Core Data Flows

### A. Chat Ingestion Pipeline
1. User provides exported WhatsApp `.txt`, Instagram `.json`, or Telegram Desktop `result.json` files.
2. Parsers normalize messages into standard `ChatMessage(sender, content, timestamp: datetime, is_user, reactions, media_type)`.
3. **PII Masking:** `PIIScrubber` scans text and masks credit/debit cards (Luhn-validated), phone numbers, passwords, auth tokens, and government IDs with safe semantic placeholders.
4. Latin-1 mojibake in Instagram exports is decoded back to UTF-8.
5. **Biographical Fact Mining:** `FactMiner` parses conversational transcripts to extract persistent biographical facts and preferences about contacts and saves high-confidence facts to SQLite.
6. `StyleExtractor` samples user messages and evaluates cadence over the entire message sequence to calculate:
   - Lowercase rate, punctuation absence rate, emoji frequency, laughing markers (`haha`, `lol`, `lmao`).
   - Double-texting percentage over full conversation threads.
   - Outputs structured markdown to `data/STYLE.md`.
7. Conversations are partitioned into 50-message chronological chunks and embedded into ChromaDB via `MemoryStore.add_messages()`.

### B. Message Draft Generation Pipeline
1. An incoming message arrives at `/api/message` (or `/api/regenerate`).
2. The incoming message is logged to SQLite (`role='them'`).
3. **Fast-path callback check:** `context_assembler.get_learned_callback_reply()` checks SQLite `callback_overrides`. If a match exists with high confidence, it returns immediately (skipping LLM generation).
4. **Context assembly:**
   - Loads contact profile (`convo_goal`, `my_impression`, `strategy_note`, `relationship_stage`).
   - Fetches the last 15 messages from SQLite.
   - Performs bounded semantic search in ChromaDB (`n_results` capped to matching contact chunk count).
   - Evaluates potential song lyrics or cultural callbacks via `_resolve_known_lyric_hints()` using Gemini Google Search grounding.
   - Injects facts from SQLite `facts`.
   - Compiles the final prompt via `PersonalityEngine.build_system_prompt()`.
5. **3-Energy Generation:** Gemini generates 3 calibrated options in a single call via `generate_variants`:
   - `Chill`: Low-effort, short (1-6 words), casual, minimal punctuation.
   - `Direct`: Natural, clear, moving the conversation forward.
   - `Banter`: Playful, witty, light teasing, or inside-joke / callback energy.
6. The UI displays the primary draft with 1-click selectable chips for instant vibe switching.

### C. Approval & Reinforcement Loop
1. User reviews the draft in the UI.
2. User can edit the text inline or click *Approve & Copy*.
3. `/api/approve`:
   - Saves the final message to SQLite (`role='you'`).
   - If the user modified the AI draft (`was_edited = True`), stores a `callback_override` mapping `their_msg -> final_message` for that contact.
   - Persists the complete exchange (`Them: ... \n You: ...`) into ChromaDB vector memory via `save_exchange(save_to_db=False)`.

---

## 4. Database Schema (SQLite: `data/db/talking.db`)

* `contacts`:
  - `id` (TEXT PRIMARY KEY)
  - `name` (TEXT NOT NULL)
  - `relationship_stage` (TEXT DEFAULT 'acquaintance')
  - `how_you_know` (TEXT DEFAULT '')
  - `their_interests` (TEXT JSON DEFAULT '[]')
  - `inside_jokes` (TEXT JSON DEFAULT '[]')
  - `style_notes` (TEXT DEFAULT '')
  - `notes` (TEXT DEFAULT '')
  - `convo_goal` (TEXT DEFAULT 'just_vibing')
  - `my_impression` (TEXT DEFAULT '')
  - `strategy_note` (TEXT DEFAULT '')
  - `created_at`, `updated_at` (TIMESTAMP)

* `messages`:
  - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
  - `contact_id` (TEXT NOT NULL, FK to contacts)
  - `role` (TEXT NOT NULL: `'them'` or `'you'`)
  - `content` (TEXT NOT NULL)
  - `ai_draft` (TEXT)
  - `was_edited` (BOOLEAN DEFAULT 0)
  - `timestamp` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
  - `metadata` (TEXT JSON)

* `facts`:
  - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
  - `contact_id` (TEXT NOT NULL, FK to contacts)
  - `category` (TEXT NOT NULL)
  - `fact` (TEXT NOT NULL)
  - `source` (TEXT)
  - `confidence` (FLOAT DEFAULT 1.0)
  - `created_at` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP)

* `callback_overrides`:
  - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
  - `contact_id` (TEXT NOT NULL, FK to contacts)
  - `trigger_text` (TEXT NOT NULL)
  - `trigger_normalized` (TEXT NOT NULL)
  - `response_text` (TEXT NOT NULL)
  - `confidence` (FLOAT DEFAULT 0.95)
  - `usage_count` (INTEGER DEFAULT 1)
  - `source` (TEXT DEFAULT 'approved_edit')
  - `created_at`, `updated_at` (TIMESTAMP)

---

## 5. Strategy & Pro Mode Mechanics

* **Module:** [`backend/strategy.py`](file:///D:/Talking/backend/strategy.py) (`StrategyInterpreter`)
* **Role:** Translates high-level natural language steering directives into structured state updates:
  - Updates `convo_goal` to steer the relational trajectory (`get_to_know`, `just_vibing`, `make_plans`, `romantic`, `keep_warm`).
  - Sets `strategy_note` to guide in-the-moment reply generation (e.g. *"tease them about their music taste"*).
* **Injection:** Read during `ContextAssembler.assemble()` and formatted into the system prompt's `CURRENT CONVERSATION` block by `PersonalityEngine.build_system_prompt()`.

---

## 6. In-Page Chat Copilot (WhatsApp Web & Instagram Direct)

* **Architecture:** Injects into WhatsApp Web and Instagram Direct as either a standalone userscript (`extension/talking-copilot.user.js` via Tampermonkey/Violentmonkey) or a Chrome MV3 Extension (`extension/manifest.json`).
* **Trigger:** Pressing `Alt+D` or clicking the floating `⚡ Draft` pill detects the current chat header and latest incoming message turn.
* **Backend Endpoint:** Calls `POST /api/copilot/draft`, which automatically gets or creates the contact in SQLite, runs RAG context assembly, and returns 3 calibrated energy drafts (`🧊 Chill`, `🎯 Direct`, `🔥 Banter`).
* **Insertion & Learning:** Clicking `Insert (Enter)` inserts the chosen reply directly into the site's rich-text input (`document.execCommand('insertText')`) and sends `POST /api/approve` back to Talking so the system continuously learns the user's conversational voice.

---

## 7. Privacy & Git Boundaries

Under no circumstances should personal conversation records or private credentials be tracked in git:
- Strictly excluded: `.env`, `data/db/`, `data/exports/`, `data/ig_session/`.
- All personal `.md` notes (`data/*.md`, `data/SOUL.md`, `data/STYLE.md`, `data/VIT_*.md`) are ignored by `.gitignore`.
- Only tracked templates are committed: `data/SOUL.template.md` and `data/STYLE.template.md`. Fallbacks in `backend/personality.py` and `backend/main.py` gracefully load templates when personal files are absent.
