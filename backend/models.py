"""
Talking — Pydantic v2 Data Models

Defines all request/response schemas and domain models for the
AI texting autopilot backend.
"""

from pydantic import BaseModel, Field, field_serializer
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from enum import Enum
import uuid


# ─── Enums ────────────────────────────────────────────────────────────────────

class RelationshipStage(str, Enum):
    """How close you are with a contact."""
    STRANGER = "stranger"
    ACQUAINTANCE = "acquaintance"
    CASUAL = "casual"
    FRIEND = "friend"
    CLOSE_FRIEND = "close_friend"
    BEST_FRIEND = "best_friend"
    CLOSE = "close"
    INTEREST = "interest"
    CRUSH = "crush"
    PARTNER = "partner"
    EX = "ex"
    FAMILY = "family"
    COLLEAGUE = "colleague"


class Mood(str, Enum):
    """Tone modifier for generated replies."""
    DEFAULT = "default"
    CHILL = "chill"
    FLIRTY = "flirty"
    DEEP = "deep"
    FUNNY = "funny"
    DRY = "dry"


# ─── Domain Models ────────────────────────────────────────────────────────────

class Message(BaseModel):
    """A single message in a conversation thread."""
    id: int = Field(default=0, description="Auto-incremented DB id")
    contact_id: str = Field(..., description="FK to the contact")
    role: str = Field(..., pattern=r"^(them|you)$", description="'them' or 'you'")
    content: str = Field(..., description="Message body text")
    ai_draft: Optional[str] = Field(default=None, description="Original AI-generated draft (if any)")
    was_edited: bool = Field(default=False, description="Whether the user edited the AI draft")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

    @field_serializer("timestamp")
    def _serialize_timestamp(self, dt: datetime, _info):
        # Timestamps are stored as naive UTC (datetime.utcnow()). Without an
        # explicit offset, the frontend's `new Date(dateStr)` parses the
        # string as LOCAL time instead of UTC, which for UTC+5:30 makes
        # messages look ~5.5 hours in the future (so diffs read as "hours
        # ago" for messages sent seconds ago). Stamp it as UTC explicitly.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()


class Contact(BaseModel):
    """A person the user communicates with."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique contact id")
    name: str = Field(..., description="Display name")
    relationship_stage: RelationshipStage = Field(default=RelationshipStage.ACQUAINTANCE)
    how_you_know: str = Field(default="", description="Context on how you met")
    their_interests: List[str] = Field(default_factory=list, description="Things they're into")
    inside_jokes: List[str] = Field(default_factory=list, description="Shared humor references")
    style_notes: str = Field(default="", description="How they text — tone, emoji usage, etc.")
    notes: str = Field(default="", description="Free-form notes about this person")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Fact(BaseModel):
    """An extracted fact about a contact (from chats or user input)."""
    id: int = Field(default=0, description="Auto-incremented DB id")
    contact_id: str = Field(..., description="FK to the contact")
    category: str = Field(..., description="Category of fact, e.g. 'preference', 'life_event'")
    fact: str = Field(..., description="The actual fact text")
    source: str = Field(default="", description="Where this fact came from")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="How confident we are")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChatMessage(BaseModel):
    """A parsed message from an imported chat export (Instagram / WhatsApp)."""
    sender: str = Field(..., description="Name of the person who sent the message")
    content: str = Field(..., description="Message body")
    timestamp: datetime = Field(..., description="When the message was sent")
    is_user: bool = Field(default=False, description="True if this message is from the user")
    reactions: Optional[List[str]] = Field(default=None, description="Emoji reactions on this message")
    media_type: Optional[str] = Field(default=None, description="'image', 'video', 'audio', or None")


# ─── API Request / Response Models ────────────────────────────────────────────

class GenerateRequest(BaseModel):
    """Request to generate an AI draft reply."""
    contact_id: str = Field(..., description="Which contact this is for")
    incoming_message: str = Field(..., description="The message they sent you")
    mood: Optional[Mood] = Field(default=Mood.DEFAULT, description="Desired tone")
    provider_mode: Optional[str] = Field(default="auto", description="Desired API provider mode ('auto', 'gemini', 'groq')")
    feedback: Optional[str] = Field(default=None, description="Correction / instructions for regeneration")




class GenerateResponse(BaseModel):
    """AI-generated draft reply."""
    draft: str = Field(..., description="The generated reply text")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Model confidence")
    retrieved_memories: List[str] = Field(default_factory=list, description="Memories used for context")
    model_provider: Optional[str] = Field(default="gemini", description="Which model provider was used ('gemini', 'groq', or 'system')")



class ApproveRequest(BaseModel):
    """User approves (or edits) a draft before sending."""
    contact_id: str = Field(..., description="Which contact this is for")
    original_draft: str = Field(..., description="The AI's original draft")
    final_message: str = Field(..., description="What the user actually sends (may be edited)")


class ContactCreate(BaseModel):
    """Schema for creating a new contact."""
    name: str = Field(..., description="Display name")
    relationship_stage: RelationshipStage = Field(default=RelationshipStage.ACQUAINTANCE)
    how_you_know: str = Field(default="")
    their_interests: List[str] = Field(default_factory=list)
    inside_jokes: List[str] = Field(default_factory=list)
    style_notes: str = Field(default="")
    notes: str = Field(default="")


class ContactUpdate(BaseModel):
    """Schema for updating an existing contact — all fields optional."""
    name: Optional[str] = None
    relationship_stage: Optional[RelationshipStage] = None
    how_you_know: Optional[str] = None
    their_interests: Optional[List[str]] = None
    inside_jokes: Optional[List[str]] = None
    style_notes: Optional[str] = None
    notes: Optional[str] = None


class IngestRequest(BaseModel):
    """Request to ingest a chat export."""
    source: str = Field(..., pattern=r"^(instagram|whatsapp)$", description="'instagram' or 'whatsapp'")
    contact_name: str = Field(..., description="Your display name in the export")
    path: Optional[str] = Field(default=None, description="Path to the export file/folder")
