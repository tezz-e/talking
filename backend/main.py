import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from .models import (
    ContactCreate, ContactUpdate, GenerateRequest, GenerateResponse,
    ApproveRequest, IngestRequest
)
from .database import DatabaseManager
from .memory import MemoryStore
from .llm import GeminiLLM
from .personality import PersonalityEngine
from .context import ContextAssembler
from .ingestion.instagram import InstagramParser
from .ingestion.whatsapp import WhatsAppParser
from .ingestion.style_extractor import StyleExtractor

app = FastAPI(title="Talking API")

# Initialize core components
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

db = DatabaseManager(DATA_DIR / "db" / "talking.db")
llm = GeminiLLM()
memory = MemoryStore(llm, DATA_DIR / "db" / "chroma")
personality = PersonalityEngine(DATA_DIR)
context_assembler = ContextAssembler(db, memory, personality, llm)

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

# ─── History ───

@app.get("/api/history/{contact_id}")
def get_history(contact_id: str, limit: int = 50):
    # db.get_messages() already returns oldest→newest, which is what
    # the UI wants (it renders top-to-bottom and auto-scrolls to bottom).
    # Do NOT reverse here — that was flipping the order to newest-first.
    return db.get_messages(contact_id, limit=limit)

# ─── Messaging ───

@app.post("/api/message", response_model=GenerateResponse)
def handle_message(req: GenerateRequest):
    contact = db.get_contact(req.contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    
    from .models import Message
    # Save the incoming message
    db.add_message(Message(
        contact_id=req.contact_id,
        role='them',
        content=req.incoming_message,
        metadata={"mood": req.mood.value if req.mood else "default"}
    ))

    if not req.feedback:
        direct_reply = context_assembler.get_learned_callback_reply(
            req.contact_id,
            req.incoming_message,
        )
        if direct_reply:
            return GenerateResponse(
                draft=direct_reply,
                confidence=0.95,
                retrieved_memories=[],
                model_provider="system"
            )

        lyric_reply = context_assembler.get_verified_lyric_reply(
            req.contact_id,
            req.incoming_message,
        )
        if lyric_reply:
            return GenerateResponse(
                draft=lyric_reply,
                confidence=0.93,
                retrieved_memories=[],
                model_provider="system"
            )
    
    # Assemble context and generate
    sys_prompt, user_msg, retrieved, history_list = context_assembler.assemble(
        contact_id=req.contact_id,
        incoming_message=req.incoming_message,
        mood=req.mood.value if req.mood else "default",
        feedback=req.feedback
    )
    
    draft = llm.generate_chat(
        system_instruction=sys_prompt,
        history=history_list,
        new_message=user_msg,
        provider_mode=req.provider_mode
    )
    
    return GenerateResponse(
        draft=draft,
        confidence=0.85, # hardcoded for now, could implement confidence scoring later
        retrieved_memories=retrieved,
        model_provider=llm.last_provider_used
    )

@app.post("/api/regenerate", response_model=GenerateResponse)
def handle_regenerate(req: GenerateRequest):
    contact = db.get_contact(req.contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    if not req.feedback:
        direct_reply = context_assembler.get_learned_callback_reply(
            req.contact_id,
            req.incoming_message,
        )
        if direct_reply:
            return GenerateResponse(
                draft=direct_reply,
                confidence=0.95,
                retrieved_memories=[],
                model_provider="system"
            )

        lyric_reply = context_assembler.get_verified_lyric_reply(
            req.contact_id,
            req.incoming_message,
        )
        if lyric_reply:
            return GenerateResponse(
                draft=lyric_reply,
                confidence=0.93,
                retrieved_memories=[],
                model_provider="system"
            )
    
    sys_prompt, user_msg, retrieved, history_list = context_assembler.assemble(
        contact_id=req.contact_id,
        incoming_message=req.incoming_message,
        mood=req.mood.value if req.mood else "default",
        feedback=req.feedback
    )
    
    # Slightly higher temperature for regeneration for variety
    draft = llm.generate_chat(
        system_instruction=sys_prompt,
        history=history_list,
        new_message=user_msg,
        temperature=0.9,
        provider_mode=req.provider_mode
    )
    
    return GenerateResponse(
        draft=draft,
        confidence=0.85,
        retrieved_memories=retrieved,
        model_provider=llm.last_provider_used
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
        was_edited=was_edited
    )
    return {"status": "approved"}

# ─── Image OCR ───

@app.post("/api/extract-text")
async def extract_text(file: UploadFile = File(...)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image.")
    try:
        image_bytes = await file.read()
        text = llm.extract_text_from_image(image_bytes, file.content_type)
        return {"extracted_text": text.strip()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
                other_senders = set(m.sender for m in msgs if not m.is_user)
                them_name = list(other_senders)[0] if other_senders else "Unknown"
                conversations = {them_name: msgs}
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
            extractor.extract_and_save(sample, str(DATA_DIR / "STYLE.md"))
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
            
            other_senders = set(m.sender for m in msgs if not m.is_user)
            true_name = list(other_senders)[0] if other_senders else them_name
            
            contact = next((c for c in existing_contacts if c.name == true_name), None)
            if not contact:
                contact = Contact(**ContactCreate(name=true_name).dict())
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
        return {"content": ""}
    with open(path, 'r', encoding='utf-8') as f:
        return {"content": f.read()}



# ─── Static Files & Frontend ───


frontend_dir = BASE_DIR / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

@app.get("/")
def serve_index():
    return FileResponse(str(frontend_dir / "index.html"))
