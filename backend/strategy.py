import json
import logging
from backend.models import Contact
from backend.database import DatabaseManager

logger = logging.getLogger(__name__)

class StrategyInterpreter:
    def __init__(self, llm_engine):
        self.llm = llm_engine

    def interpret(self, contact: Contact, instruction: str) -> dict:
        """
        Takes a natural language instruction from the user and infers which
        contact fields to update (convo_goal, my_impression, strategy_note).
        Returns a dictionary of updates and a summary message.
        """
        system_prompt = (
            "You are a conversation strategy engine for an AI texting assistant. "
            "The user is giving you a directive on how to steer a conversation. "
            "Your job is to parse their instruction into structured updates for the contact's profile.\n\n"
            "You can update these fields:\n"
            "- convo_goal: one of ['get_to_know', 'just_vibing', 'make_plans', 'romantic', 'keep_warm']\n"
            "- my_impression: Free text describing what the user thinks of this person right now.\n"
            "- strategy_note: Free text directive injected directly into the next AI draft prompt. Use this for specific in-the-moment instructions.\n\n"
            "Current state:\n"
            f"Goal: {contact.convo_goal}\n"
            f"Impression: {contact.my_impression}\n\n"
            "Output strictly valid JSON with keys: 'updated_fields' (dict) and 'summary' (a brief plain-English confirmation of what you changed, e.g. 'Switched goal to romantic, added note to be flirtier'). "
            "Only include fields in 'updated_fields' that actually need to change based on the user's instruction. Always set 'strategy_note' if the user gives a specific tactical instruction."
        )

        try:
            from google.genai import types
            response = self.llm.client.models.generate_content(
                model=self.llm.model,
                contents=instruction,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.0,
                    response_mime_type="application/json",
                ),
            )
            cleaned_json = self.llm._clean_json_text(response.text)
            data = json.loads(cleaned_json)
            
            # Ensure strategy_note is set if not explicitly cleared, 
            # because the instruction itself is often a strategy note
            updated_fields = data.get("updated_fields", {})
            if "strategy_note" not in updated_fields:
                updated_fields["strategy_note"] = instruction

            return {
                "updated_fields": updated_fields,
                "summary": data.get("summary", f"Applied directive: {instruction}")
            }
        except Exception as e:
            logger.error(f"Strategy interpretation failed: {e}")
            return {
                "updated_fields": {"strategy_note": instruction},
                "summary": "Added as a direct strategy note."
            }
