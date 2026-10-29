"""
Triage Agent for Resolve Support Desk.
Implements zero-tool principle: extracts entities, classifies category, urgency,
and language, without accessing backend databases.
"""

import re
import json
from typing import Dict, Any, List, Optional
from openai import AzureOpenAI

from src.config import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_CHAT_DEPLOYMENT,
)

TRIAGE_SYSTEM_PROMPT = """You are the specialized Triage Agent for NorthPeak Resolve Support Desk.
Your job is to parse incoming customer support tickets and extract structured metadata.

STRICT INSTRUCTIONS:
1. Zero-Tool Principle: You have NO database access. Extract only from the provided text.
2. Detect order_id if present in format O-#### (e.g., O-1001, O-0870). If not mentioned, set order_id to null.
3. Classify primary_category into exactly one of: "billing", "delivery", "product", "other".
4. Determine urgency:
   - "critical": Safety hazards, product recalls, bodily injury, explicit legal or regulatory threats.
   - "high": Chargeback threats, orders delayed > 5 business days, severe customer distress.
   - "medium": Standard return/refund requests, item replacements, delivery status inquiries.
   - "low": General product care, inquiries on operating hours or store policies.
5. Detect customer language: "en" (English) or "nl" (Dutch).
6. Estimate triage_confidence between 0.0 and 1.0 based on clarity of the customer's request.
7. List all intents_detected (e.g., ["return_request", "damaged_item", "billing_inquiry"]).

You must return a single valid JSON object with EXACTLY this structure:
{
  "order_id": "O-1001" or null,
  "primary_category": "product",
  "secondary_category": null,
  "urgency": "medium",
  "language": "en",
  "confidence": 0.95,
  "intents_detected": ["return_request"]
}
"""


def _detect_order_id_regex(text: str) -> Optional[str]:
    """Fallback regex to find O-#### order identifiers."""
    match = re.search(r"\b(O-\d{3,5})\b", text, re.IGNORECASE)
    return match.group(1).upper() if match else None


def _detect_language_heuristic(text: str) -> str:
    """Detect Dutch vs English using common stopwords and support vocabulary."""
    dutch_markers = [
        r"\bhallo\b", r"\bbedankt\b", r"\bbestelling\b", r"\bretour\b",
        r"\bterugbetaling\b", r"\bgraag\b", r"\bniet\b", r"\bontvangen\b",
        r"\bbezorging\b", r"\bpakket\b", r"\bbeschadigd\b", r"\bkapot\b",
        r"\bwaarom\b", r"\bik wil\b", r"\bgeen\b", r"\bvertraging\b",
        r"\blevering\b", r"\bgoederen\b", r"\bwanneer\b", r"\bklacht\b"
    ]
    text_lower = text.lower()
    dutch_count = sum(1 for m in dutch_markers if re.search(m, text_lower))
    return "nl" if dutch_count >= 2 else "en"


def _fallback_triage(ticket_text: str, sender_email: Optional[str] = None) -> Dict[str, Any]:
    """
    Deterministic rule-based fallback when LLM is unavailable or offline.
    Guarantees reliable unit testing and offline execution.
    """
    text_lower = ticket_text.lower()
    order_id = _detect_order_id_regex(ticket_text)
    language = _detect_language_heuristic(ticket_text)

    # 1. Urgency Detection
    if any(k in text_lower for k in ["fire", "hazard", "injury", "hospital", "lawyer", "legal", "sue", "police"]):
        urgency = "critical"
    elif any(k in text_lower for k in ["chargeback", "fraud", "unacceptable", "dispute", "5 days late", "stolen"]):
        urgency = "high"
    elif any(k in text_lower for k in ["return", "refund", "exchange", "replacement", "damaged", "broken"]):
        urgency = "medium"
    else:
        urgency = "low"

    # 2. Category & Intent Detection
    intents = []
    # Product return/damage/exchange issues take precedence over general shipping words
    if any(k in text_lower for k in ["return", "refund", "damaged", "broken", "size", "fit", "replacement", "exchange", "ruilen", "omruilen", "retour", "retourneren", "beschadigd", "kapot"]):
        primary_category = "product"
        if any(k in text_lower for k in ["exchange", "ruilen", "omruilen", "swap size", "different size"]):
            intents.append("exchange_inquiry")
        if any(k in text_lower for k in ["return", "retour", "retourneren", "refund", "terugbetaling"]):
            intents.append("return_request")
        if any(k in text_lower for k in ["damaged", "broken", "beschadigd", "kapot"]):
            intents.append("damaged_item")
        if any(k in text_lower for k in ["replacement"]):
            intents.append("replacement_request")
    elif any(k in text_lower for k in ["charge", "charged", "billing", "invoice", "payment", "duplicate", "betaald", "factuur"]):
        primary_category = "billing"
        intents.append("billing_inquiry")
    elif any(k in text_lower for k in ["tracking", "delivery", "shipped", "carrier", "late", "delay", "bezorging", "pakket", "levering"]):
        primary_category = "delivery"
        intents.append("delivery_inquiry")
    else:
        primary_category = "other"
        intents.append("general_inquiry")

    # Confidence calculation:
    # High if clear order_id and specific actionable intent
    # Low (< 0.70) if generic inquiry or missing essential info (TR5)
    if order_id and primary_category != "other":
        confidence = 0.90
    elif primary_category != "other":
        confidence = 0.75
    else:
        confidence = 0.50

    # TR5 low confidence handling
    decision = "REQUEST_INFO" if confidence < 0.70 else "PROCEED"

    return {
        "order_id": order_id,
        "primary_category": primary_category,
        "secondary_category": None,
        "urgency": urgency,
        "language": language,
        "confidence": confidence,
        "intents_detected": intents,
        "decision": decision,
    }


def triage_ticket(ticket_text: str, sender_email: Optional[str] = None) -> Dict[str, Any]:
    """
    Executes triage on incoming ticket using Azure OpenAI (gpt-4o-mini).
    Falls back to deterministic extraction if LLM is unconfigured or fails.
    """
    if not ticket_text or not ticket_text.strip():
        return {
            "order_id": None,
            "primary_category": "other",
            "secondary_category": None,
            "urgency": "low",
            "language": "en",
            "confidence": 0.0,
            "intents_detected": [],
            "decision": "REQUEST_INFO",
        }

    # If Azure OpenAI credentials are not configured, use deterministic fallback
    if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_API_KEY:
        return _fallback_triage(ticket_text, sender_email)

    try:
        client = AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY,
            api_version=AZURE_OPENAI_API_VERSION,
        )

        user_content = f"Ticket body:\n{ticket_text}"
        if sender_email:
            user_content = f"Sender Email: {sender_email}\n" + user_content

        response = client.chat.completions.create(
            model=AZURE_OPENAI_CHAT_DEPLOYMENT,
            messages=[
                {"role": "system", "content": TRIAGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )

        raw_json = response.choices[0].message.content
        data = json.loads(raw_json)

        # Enforce type constraints and schema bounds
        order_id = data.get("order_id")
        if order_id and not re.match(r"^O-\d{3,5}$", str(order_id).strip(), re.IGNORECASE):
            order_id = _detect_order_id_regex(ticket_text)

        confidence = float(data.get("confidence", 0.85))
        # Rule TR5: Low confidence trigger
        decision = "REQUEST_INFO" if confidence < 0.70 else "PROCEED"

        return {
            "order_id": order_id,
            "primary_category": data.get("primary_category", "other"),
            "secondary_category": data.get("secondary_category"),
            "urgency": data.get("urgency", "medium"),
            "language": data.get("language", "en"),
            "confidence": round(confidence, 2),
            "intents_detected": data.get("intents_detected", []),
            "decision": decision,
        }

    except Exception:
        # Graceful degradation to deterministic parser on network or auth errors
        return _fallback_triage(ticket_text, sender_email)
