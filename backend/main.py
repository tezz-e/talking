import os
import logging
import secrets
from collections import Counter
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from pydantic import BaseModel

logger = logging.getLogger("talking.api")

from .models import (
    ContactCreate, ContactUpdate, GenerateRequest, GenerateResponse,
    ApproveRequest, IngestRequest, SteerRequest, SteerResponse, DraftVariant,
    Fact, FactCreate, CopilotDraftRequest, CopilotDraftResponse,
    DescribeMediaRequest, SyncHistoryRequest, WatcherStartRequest
)
from .database import DatabaseManager
from .memory import MemoryStore
from .llm import GeminiLLM
from .personality import PersonalityEngine
from .context import ContextAssembler
from .strategy import StrategyInterpreter
from .ingestion.instagram import InstagramParser
from .ingestion.whatsapp import WhatsAppParser
from .ingestion.telegram import TelegramParser
from .ingestion.style_extractor import StyleExtractor
from .ingestion.fact_miner import FactMiner

app = FastAPI(title="Talking API")

# Server-side API protection token (generated at startup, compared with secrets.compare_digest)
SERVER_API_TOKEN = os.getenv("TALKING_API_TOKEN") or secrets.token_hex(32)

DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "https://web.whatsapp.com",
    "https://www.instagram.com",
]

def get_allowed_origins() -> list[str]:
    """Returns the set of allowed CORS and local API origins.
    Production defaults strictly to http://localhost:8000 and http://127.0.0.1:8000.
    Additional origins can be configured via ADDITIONAL_ALLOWED_ORIGINS (e.g. test ports).
    """
    origins = list(DEFAULT_ALLOWED_ORIGINS)
    extra = os.getenv("ADDITIONAL_ALLOWED_ORIGINS", "").strip()
    if extra:
        for orig in extra.split(","):
            orig = orig.strip()
            if orig and orig not in origins:
                origins.append(orig)
    return origins

ALLOWED_ORIGINS = get_allowed_origins()

ALLOWED_HOSTS = {"localhost", "127.0.0.1", "testserver"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # 1. Host header validation (blocks DNS rebinding)
    host_header = request.headers.get("host")
    if host_header:
        host_name = host_header.split(":")[0].strip().lower()
        if host_name not in ALLOWED_HOSTS:
            return JSONResponse(
                status_code=403,
                content={"detail": f"Forbidden host: {host_header}"}
            )

    # 2. Reject requests whose Origin header is present and not in the allowed list
    origin = request.headers.get("origin")
    if origin is not None and origin not in get_allowed_origins():
        return JSONResponse(
            status_code=403,
            content={"detail": f"Forbidden origin: {origin}"}
        )

    # 3. Allow CORS preflight requests
    if request.method == "OPTIONS":
        return await call_next(request)

    # 4. Require valid X-Talking-Token on all state-changing methods
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        token = request.headers.get("x-talking-token") or ""
        if not token or not secrets.compare_digest(token, SERVER_API_TOKEN):
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid or missing X-Talking-Token"}
            )

    return await call_next(request)

@app.get("/api/auth/token")
def get_auth_token(request: Request):
    origin = request.headers.get("origin")
    if origin is not None and origin not in get_allowed_origins():
        raise HTTPException(status_code=403, detail="Forbidden origin")
    return {"token": SERVER_API_TOKEN}

# Initialize core components
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

db = DatabaseManager(DATA_DIR / "db" / "talking.db")
llm = GeminiLLM()
memory = MemoryStore(llm, DATA_DIR / "db" / "chroma")
personality = PersonalityEngine(DATA_DIR)
context_assembler = ContextAssembler(db, memory, personality, llm)
strategy_interpreter = StrategyInterpreter(llm)

# ─── Contacts ───

@app.get("/api/contacts")
def get_contacts():
    return db.list_contacts()

@app.post("/api/contacts")
def create_contact(contact: ContactCreate):
    from .models import Contact
    full_contact = Contact(**contact.model_dump())
    return db.add_contact(full_contact)

@app.put("/api/contacts/{contact_id}")
def update_contact(contact_id: str, updates: ContactUpdate):
    contact = db.update_contact(contact_id, updates.model_dump(exclude_unset=True))
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact

@app.delete("/api/contacts/{contact_id}")
def delete_contact(contact_id: str):
    if not db.delete_contact(contact_id):
        raise HTTPException(status_code=404, detail="Contact not found")
    return {"status": "deleted"}

# ─── Facts ───

@app.get("/api/contacts/{contact_id}/facts", response_model=list[Fact])
def get_contact_facts(contact_id: str):
    return db.get_facts(contact_id)

@app.post("/api/contacts/{contact_id}/facts", response_model=Fact)
def add_contact_fact(contact_id: str, req: FactCreate):
    contact = db.get_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    fact = Fact(
        contact_id=contact_id,
        category=req.category,
        fact=req.fact,
        source="manual",
        confidence=req.confidence or 0.9,
    )
    return db.add_fact(fact)

@app.delete("/api/facts/{fact_id}")
def delete_fact(fact_id: int):
    if not db.delete_fact(fact_id):
        raise HTTPException(status_code=404, detail="Fact not found")
    return {"status": "deleted"}

# ─── History ───

@app.get("/api/history/{contact_id}")
def get_history(contact_id: str, limit: int = 50):
    return db.get_messages(contact_id, limit=limit)

# ─── Stats ───

@app.get("/api/stats")
def get_stats():
    return {
        "total_memories": memory.get_collection_count(),
        "total_contacts": len(db.list_contacts()),
    }

# ─── Strategy & Steering ───

@app.post("/api/contacts/{contact_id}/steer", response_model=SteerResponse)
def steer_contact(contact_id: str, req: SteerRequest):
    contact = db.get_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    res = strategy_interpreter.interpret(contact, req.instruction)
    updated_contact = db.update_contact(contact_id, res.get("updated_fields", {}))
    return SteerResponse(
        updated_fields=res.get("updated_fields", {}),
        summary=res.get("summary", ""),
        contact=updated_contact or contact,
    )

# ─── Messaging ───

@app.post("/api/message", response_model=GenerateResponse)
def handle_message(req: GenerateRequest):
    contact = db.get_contact(req.contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    
    # If a steering directive was provided, parse and apply it immediately
    if req.steering_directive and req.steering_directive.strip():
        strat_res = strategy_interpreter.interpret(contact, req.steering_directive.strip())
        db.update_contact(req.contact_id, strat_res.get("updated_fields", {}))
        contact = db.get_contact(req.contact_id)

    from .models import Message
    # Save the incoming message
    db.add_message(Message(
        contact_id=req.contact_id,
        role='them',
        content=req.incoming_message,
        metadata={"mood": req.mood.value if req.mood else "default"}
    ))

    direct_reply = context_assembler.get_learned_callback_reply(
        req.contact_id,
        req.incoming_message,
    )
    if direct_reply:
        return GenerateResponse(
            draft=direct_reply,
            confidence=0.95,
            retrieved_memories=[]
        )
    
    # Assemble context and generate
    sys_prompt, user_msg, retrieved = context_assembler.assemble(
        contact_id=req.contact_id,
        incoming_message=req.incoming_message,
        mood=req.mood.value if req.mood else "default"
    )
    
    if req.pro_mode:
        user_msg = (
            f"{user_msg}\n\n"
            "[PRO MODE ACTIVE: Analyze conversational subtext and tone deeply. "
            "Formulate options advancing the active goal.]"
        )

    variants: list[DraftVariant] = []
    draft = ""
    bubbles: list[str] = []
    try:
        variant_dict = llm.generate_variants(
            sys_prompt,
            user_msg,
            temperature=0.6 if req.pro_mode else 0.75,
        )
        for label in ("chill", "direct", "banter"):
            val = variant_dict.get(label, {})
            if isinstance(val, dict):
                text = str(val.get("text", "")).strip()
                v_bubbles = [str(b).strip() for b in val.get("bubbles", []) if str(b).strip()]
            else:
                text = str(val).strip()
                v_bubbles = [text] if text else []
            if text:
                variants.append(DraftVariant(label=label, text=text, bubbles=v_bubbles))

        # Select initial draft according to mood
        active_variant = None
        if req.mood and req.mood.value in ("chill", "dry"):
            active_variant = next((v for v in variants if v.label == "chill"), None)
        elif req.mood and req.mood.value in ("flirty", "funny"):
            active_variant = next((v for v in variants if v.label == "banter"), None)

        if not active_variant:
            active_variant = next((v for v in variants if v.label == "direct"), None) or (variants[0] if variants else None)

        if active_variant:
            draft = active_variant.text
            bubbles = active_variant.bubbles
    except Exception as exc:
        draft = llm.generate(sys_prompt, user_msg, temperature=0.6 if req.pro_mode else 0.8)
        bubbles = [draft.strip()] if draft.strip() else []

    if not draft and variants:
        draft = variants[0].text
        bubbles = variants[0].bubbles

    if not bubbles and draft:
        bubbles = [draft]

    confidence = 0.92 if req.pro_mode else 0.85
    
    return GenerateResponse(
        draft=draft,
        bubbles=bubbles,
        confidence=confidence,
        retrieved_memories=retrieved,
        variants=variants,
    )

@app.post("/api/copilot/draft", response_model=CopilotDraftResponse)
def handle_copilot_draft(req: CopilotDraftRequest):
    """Entry point for the in-page browser copilot. Automatically links or creates contact."""
    contact_name = req.contact_name.strip()
    if not contact_name:
        contact_name = "Friend"

    contacts = db.list_contacts()
    contact = next(
        (c for c in contacts if c.name.strip().lower() == contact_name.lower()),
        None
    )
    if not contact:
        from .models import Contact
        contact = db.add_contact(Contact(name=contact_name))

    gen_req = GenerateRequest(
        contact_id=contact.id,
        incoming_message=req.incoming_message,
        mood=req.mood,
        pro_mode=req.pro_mode,
        steering_directive=req.steering_directive,
    )
    gen_res = handle_message(gen_req)

    return CopilotDraftResponse(
        contact_id=contact.id,
        contact_name=contact.name,
        draft=gen_res.draft,
        bubbles=gen_res.bubbles,
        variants=gen_res.variants,
        confidence=gen_res.confidence,
        retrieved_memories=gen_res.retrieved_memories,
    )

@app.post("/api/regenerate", response_model=GenerateResponse)
def handle_regenerate(req: GenerateRequest):
    contact = db.get_contact(req.contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    if req.steering_directive and req.steering_directive.strip():
        strat_res = strategy_interpreter.interpret(contact, req.steering_directive.strip())
        db.update_contact(req.contact_id, strat_res.get("updated_fields", {}))
        contact = db.get_contact(req.contact_id)

    direct_reply = context_assembler.get_learned_callback_reply(
        req.contact_id,
        req.incoming_message,
    )
    if direct_reply:
        return GenerateResponse(
            draft=direct_reply,
            confidence=0.95,
            retrieved_memories=[]
        )
    
    sys_prompt, user_msg, retrieved = context_assembler.assemble(
        contact_id=req.contact_id,
        incoming_message=req.incoming_message,
        mood=req.mood.value if req.mood else "default"
    )
    
    if req.pro_mode:
        user_msg = (
            f"{user_msg}\n\n"
            "[PRO MODE ACTIVE: Formulate alternative high-precision replies advancing the active goal.]"
        )

    variants: list[DraftVariant] = []
    draft = ""
    bubbles: list[str] = []
    try:
        variant_dict = llm.generate_variants(
            sys_prompt,
            user_msg,
            temperature=0.75 if req.pro_mode else 0.9,
        )
        for label in ("chill", "direct", "banter"):
            val = variant_dict.get(label, {})
            if isinstance(val, dict):
                text = str(val.get("text", "")).strip()
                v_bubbles = [str(b).strip() for b in val.get("bubbles", []) if str(b).strip()]
            else:
                text = str(val).strip()
                v_bubbles = [text] if text else []
            if text:
                variants.append(DraftVariant(label=label, text=text, bubbles=v_bubbles))

        active_variant = None
        if req.mood and req.mood.value in ("chill", "dry"):
            active_variant = next((v for v in variants if v.label == "chill"), None)
        elif req.mood and req.mood.value in ("flirty", "funny"):
            active_variant = next((v for v in variants if v.label == "banter"), None)

        if not active_variant:
            active_variant = next((v for v in variants if v.label == "direct"), None) or (variants[0] if variants else None)

        if active_variant:
            draft = active_variant.text
            bubbles = active_variant.bubbles
    except Exception:
        draft = llm.generate(sys_prompt, user_msg, temperature=0.9)
        bubbles = [draft.strip()] if draft.strip() else []

    if not draft and variants:
        draft = variants[0].text
        bubbles = variants[0].bubbles

    if not bubbles and draft:
        bubbles = [draft]

    confidence = 0.92 if req.pro_mode else 0.85
    
    return GenerateResponse(
        draft=draft,
        bubbles=bubbles,
        confidence=confidence,
        retrieved_memories=retrieved,
        variants=variants,
    )

@app.post("/api/approve")
def handle_approve(req: ApproveRequest):
    was_edited = (req.original_draft != req.final_message)
    # We fetch the last incoming message for saving the exchange to Chroma
    recent = db.get_recent_messages(req.contact_id, n=6)
    
    from .models import Message
    # Save to db
    db.add_message(Message(
        contact_id=req.contact_id,
        role='you',
        content=req.final_message,
        ai_draft=req.original_draft,
        was_edited=was_edited
    ))
    
    their_msg = "Unknown"
    for m in reversed(recent):
        if m.role == 'them':
            their_msg = m.content
            break
            
    if their_msg != "Unknown" and was_edited:
        db.add_callback_override(
            contact_id=req.contact_id,
            trigger_text=their_msg,
            response_text=req.final_message,
        )
            
    # Save exchange to vector memory
    context_assembler.save_exchange(
        contact_id=req.contact_id,
        their_message=their_msg,
        your_response=req.final_message,
        ai_draft=req.original_draft,
        was_edited=was_edited,
        save_to_db=False,
    )
    return {"status": "approved"}

# ─── Image OCR & Voice Transcription ───

@app.post("/api/extract-text")
async def extract_text(file: UploadFile = File(...)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image.")
    try:
        import asyncio
        image_bytes = await file.read()
        text = await asyncio.to_thread(llm.extract_text_from_image, image_bytes, file.content_type)
        return {"extracted_text": text.strip()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class TranscribeVoiceRequest(BaseModel):
    contact_id: str | None = None
    audio_base64: str
    mime_type: str = "audio/ogg"

@app.post("/api/whatsapp/transcribe_voice")
def transcribe_whatsapp_voice(req: TranscribeVoiceRequest):
    import base64
    try:
        raw_b64 = req.audio_base64
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]
        audio_bytes = base64.b64decode(raw_b64)
        transcript = llm.transcribe_audio(audio_bytes, mime_type=req.mime_type)
        return {"status": "ok", "transcription": transcript}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

# ─── Instagram Watcher & Media Vision ───

@app.post("/api/instagram/describe_media")
def describe_instagram_media(req: DescribeMediaRequest):
    import base64
    contact = db.get_contact(req.contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    try:
        raw_b64 = req.image_base64
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]
        image_bytes = base64.b64decode(raw_b64)
        description = llm.describe_image(image_bytes)
        formatted_content = f"{req.media_type}: {description}"
        thumbnail_uri = f"data:image/jpeg;base64,{raw_b64}"

        # Check for a recent un-described media message to update, preventing duplicates
        recent_msgs = db.get_recent_messages(req.contact_id, n=10)
        target_msg = None
        for m in reversed(recent_msgs):
            if (
                m.content.strip() == req.media_type.strip()
                or (m.metadata and m.metadata.get("is_media") and not m.metadata.get("description"))
                or (req.media_type in m.content and not m.metadata.get("description"))
            ):
                target_msg = m
                break

        if target_msg:
            updated_meta = dict(target_msg.metadata or {})
            updated_meta["is_media"] = True
            updated_meta["description"] = description
            updated_meta["thumbnail"] = thumbnail_uri
            db.update_message(target_msg.id, content=formatted_content, metadata=updated_meta)
        else:
            from .models import Message
            db.add_message(Message(
                contact_id=req.contact_id,
                role="them",
                content=formatted_content,
                metadata={"is_media": True, "description": description, "thumbnail": thumbnail_uri}
            ))

        return {
            "status": "ok",
            "description": description,
            "formatted_content": formatted_content
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/api/instagram/sync_history")
def sync_instagram_history(req: SyncHistoryRequest):
    contact = db.get_contact(req.contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    from .models import Message
    recent_db_msgs = db.get_recent_messages(req.contact_id, n=30)
    recent_signatures = {(m.role, m.content.strip()) for m in recent_db_msgs}

    new_messages = []
    for m in req.messages:
        content = str(m.get("content", "")).strip()
        if not content:
            continue
        raw_role = str(m.get("role", "them")).lower()
        role = "you" if raw_role in ("you", "me", "assistant") else "them"

        sig = (role, content)
        if sig not in recent_signatures:
            meta = {"source": "ig_sync"}
            if m.get("is_media"):
                meta["is_media"] = True
                if m.get("media_url"):
                    meta["media_url"] = m.get("media_url")
            new_messages.append(Message(
                contact_id=req.contact_id,
                role=role,
                content=content,
                metadata=meta
            ))
            recent_signatures.add(sig)

    if new_messages:
        db.add_messages_batch(new_messages)

    return {"status": "synced", "count": len(new_messages)}

@app.post("/api/watcher/start")
def start_instagram_watcher(req: WatcherStartRequest):
    contact = db.get_contact(req.contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    if req.full_auto:
        allow_full_auto = os.getenv("ALLOW_FULL_AUTO", "0").strip()
        if allow_full_auto != "1":
            raise HTTPException(
                status_code=403,
                detail="Full auto-send is disabled server-side. Set ALLOW_FULL_AUTO=1 to enable."
            )
        if not req.confirm_full_auto:
            raise HTTPException(
                status_code=403,
                detail="Full auto-send requires explicit confirmation with confirm_full_auto: true."
            )
        logger.warning(
            f"[AUTO-SEND ENABLED] Watcher session starting with full_auto=True for contact_id={req.contact_id} "
            f"target={req.instagram_url} confirmed=True"
        )

    from .instagram_watcher import start_watcher, get_state
    current_state = get_state()
    if current_state.get("running"):
        return {"status": "already_running", "state": current_state}

    start_watcher(
        contact_id=req.contact_id,
        their_ig_username=req.instagram_url,
        mood=req.mood or "default",
        full_auto=req.full_auto
    )
    return {"status": "started", "state": get_state()}

@app.post("/api/watcher/stop")
def stop_instagram_watcher():
    from .instagram_watcher import stop_watcher, get_state
    stop_watcher()
    return {"status": "stopping", "state": get_state()}

@app.get("/api/watcher/status")
def get_instagram_watcher_status():
    from .instagram_watcher import get_state
    return get_state()

@app.post("/api/watcher/send")
async def send_watcher_reply(payload: dict):
    text = payload.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="Missing reply text")
    from .instagram_watcher import send_approved_reply
    success = await send_approved_reply(text)
    return {"status": "sent" if success else "failed"}

# ─── Ingestion ───

ingestion_status = {
    "status": "idle", 
    "progress": 0, 
    "message": ""
}

@app.get("/api/ingest/status")
async def get_ingest_status():
    return ingestion_status

def run_ingestion(source: str, contact_name: str, path: str):
    """Background task for ingestion."""
    global ingestion_status
    from .models import ChatMessage
    messages = []
    
    try:
        ingestion_status["status"] = "running"
        ingestion_status["progress"] = 10
        ingestion_status["message"] = f"Parsing {source} export..."
        
        if source == 'instagram':
            parser = InstagramParser(path, contact_name)
            conversations = parser.parse_all()
        elif source == 'whatsapp':
            parser = WhatsAppParser(contact_name)
            if os.path.isfile(path):
                msgs = parser.parse_file(path)
                other_senders = [m.sender for m in msgs if not m.is_user]
                them_name = Counter(other_senders).most_common(1)[0][0] if other_senders else "Unknown"
                conversations = {them_name: msgs}
            else:
                conversations = parser.parse_folder(path)
        elif source == 'telegram':
            parser = TelegramParser(contact_name)
            if os.path.isfile(path):
                conversations = parser.parse_file(path)
            else:
                conversations = parser.parse_folder(path)
        
        for msgs in conversations.values():
            messages.extend(msgs)
            
        # Sort all by time
        ingestion_status["progress"] = 30
        ingestion_status["message"] = "Sorting messages..."
        messages.sort(key=lambda x: x.timestamp)
        
        user_msgs = [m for m in messages if m.is_user]
        if user_msgs:
            ingestion_status["progress"] = 40
            ingestion_status["message"] = "Extracting texting fingerprint..."
            # Sample max 500 messages — more than enough for accurate style stats
            import random
            sample = random.sample(user_msgs, min(500, len(user_msgs)))
            print(f"[INGEST] Extracting style from {len(sample)} sampled messages (of {len(user_msgs)} total)...")
            extractor = StyleExtractor(llm)
            extractor.extract_and_save(sample, str(DATA_DIR / "STYLE.md"), all_messages=messages)
            print("[INGEST] Style extraction complete.")
            
        print("[INGEST] Starting semantic memory embedding...")
        ingestion_status["progress"] = 60
        ingestion_status["message"] = "Building semantic memories for contacts..."
        
        from .models import Contact, ContactCreate
        existing_contacts = db.list_contacts()
        
        # Collect all chunks across all conversations first
        all_chunks = []
        for them_name, msgs in conversations.items():
            if not msgs:
                continue
            
            other_senders = [m.sender for m in msgs if not m.is_user]
            true_name = Counter(other_senders).most_common(1)[0][0] if other_senders else them_name
            
            contact = next((c for c in existing_contacts if c.name == true_name), None)
            if not contact:
                contact = Contact(**ContactCreate(name=true_name).model_dump())
                db.add_contact(contact)
                existing_contacts.append(contact)
                
            # Group messages into larger chunks of 50 to minimise API calls
            chunk_size = 50
            msgs.sort(key=lambda x: x.timestamp)
            for i in range(0, len(msgs), chunk_size):
                batch = msgs[i:i+chunk_size]
                text_block = "\n".join([f"{m.sender}: {m.content}" for m in batch])
                all_chunks.append({
                    "text": text_block,
                    "contact_id": contact.id,
                    "timestamp": batch[-1].timestamp.isoformat(sep=" "),
                    "is_user": batch[-1].is_user
                })

            # Mine factual knowledge about contact from chat turns
            try:
                miner = FactMiner(llm)
                mined = miner.mine_facts(msgs, contact.id, contact_name=true_name)
                existing_facts = {f.fact.lower().strip() for f in db.get_facts(contact.id)}
                for f in mined:
                    if f.fact.lower().strip() not in existing_facts and f.confidence >= 0.7:
                        db.add_fact(f)
                        existing_facts.add(f.fact.lower().strip())
                if mined:
                    print(f"[INGEST] Mined {len(mined)} facts for {true_name}")
            except Exception as exc:
                print(f"[INGEST] Fact mining notice for {true_name}: {exc}")
        
        # Embed all chunks with live progress updates (60% → 95%)
        def _progress(done, total):
            pct = 60 + int((done / total) * 35) if total else 95
            ingestion_status["progress"] = pct
            ingestion_status["message"] = f"Embedding memories... {done}/{total} chunks"
            print(f"[INGEST] Embedding progress: {done}/{total}")
        
        print(f"[INGEST] Starting embedding of {len(all_chunks)} total chunks...")
        memory.add_messages(all_chunks, progress_callback=_progress)
        print("[INGEST] Embedding complete!")
        
        ingestion_status["status"] = "completed"
        ingestion_status["progress"] = 100
        ingestion_status["message"] = "Ingestion complete!"
        print("[INGEST] ✅ Ingestion finished successfully!")
            
    except Exception as e:
        ingestion_status["status"] = "error"
        ingestion_status["message"] = f"Ingestion failed: {e}"
        import traceback
        print(f"[INGEST] ❌ Ingestion failed: {e}")
        traceback.print_exc()

@app.post("/api/ingest")
def handle_ingest(req: IngestRequest):
    import threading
    
    path = req.path
    if not path:
        path = str(DATA_DIR / "exports" / req.source)
        
    if not os.path.exists(path):
        raise HTTPException(status_code=400, detail=f"Path not found: {path}")
    
    # Run in a real thread so time.sleep() doesn't block the event loop
    t = threading.Thread(
        target=run_ingestion,
        args=(req.source, req.contact_name, path),
        daemon=True,
    )
    t.start()
    return {"status": "started", "message": "Ingestion running in background"}

# ─── SOUL / STYLE ───

class SoulContent(BaseModel):
    content: str

@app.get("/api/soul")
def get_soul():
    path = DATA_DIR / "SOUL.md"
    if not path.exists():
        path = DATA_DIR / "SOUL.template.md"
    if not path.exists():
        return {"content": ""}
    with open(path, 'r', encoding='utf-8') as f:
        return {"content": f.read()}

@app.put("/api/soul")
def update_soul(payload: SoulContent):
    path = DATA_DIR / "SOUL.md"
    with open(path, 'w', encoding='utf-8') as f:
        f.write(payload.content)
    # Reload personality engine
    personality.load()
    return {"status": "saved"}

@app.get("/api/style")
def get_style():
    path = DATA_DIR / "STYLE.md"
    if not path.exists():
        path = DATA_DIR / "STYLE.template.md"
    if not path.exists():
        return {"content": ""}
    with open(path, 'r', encoding='utf-8') as f:
        return {"content": f.read()}

# ─── Static Files & Frontend ───

frontend_dir = BASE_DIR / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

@app.get("/")
def serve_index():
    index_file = frontend_dir / "index.html"
    content = index_file.read_text(encoding="utf-8")
    token_meta = f'<meta name="talking-token" content="{SERVER_API_TOKEN}" />'
    if "<head>" in content:
        content = content.replace("<head>", f"<head>\n  {token_meta}", 1)
    return HTMLResponse(content=content, media_type="text/html")
