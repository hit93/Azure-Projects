"""
Deterministic Policy Engine for Resolve Support Desk.
Guarantees 0% boundary hallucinations by calculating financial thresholds,
return eligibility, delivery compensation, and escalation routing purely in Python.
"""

import hmac
import hashlib
import json
import base64
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional

from src.config import EVALUATION_DATE

# Evaluation Clock is fixed to Tuesday, Oct 20, 2026
EVAL_DATE = date.fromisoformat(EVALUATION_DATE)
SECRET_KEY = b"resolve-eval-hmac-secret-key-2026-northpeak"


def get_days_elapsed(date_str: Optional[str]) -> Optional[int]:
    """Returns calendar days elapsed between date_str and the EVALUATION_DATE."""
    if not date_str:
        return None
    try:
        target_date = date.fromisoformat(date_str.split("T")[0])
        return (EVAL_DATE - target_date).days
    except (ValueError, TypeError):
        return None


def get_business_days_late(est_delivery_str: Optional[str]) -> int:
    """
    Computes business days (Monday-Friday) between est_delivery and EVALUATION_DATE.
    Returns 0 if delivery is not yet late or date is invalid.
    """
    if not est_delivery_str:
        return 0
    try:
        est_date = date.fromisoformat(est_delivery_str.split("T")[0])
        if est_date >= EVAL_DATE:
            return 0
        
        bus_days = 0
        cur = est_date + timedelta(days=1)
        while cur <= EVAL_DATE:
            if cur.weekday() < 5:  # Monday to Friday
                bus_days += 1
            cur += timedelta(days=1)
        return bus_days
    except (ValueError, TypeError):
        return 0


# ── Cryptographic Authorization Tokens ──────────────────────────────────────

def generate_auth_token(
    tier: str,
    action: str,
    order_id: str,
    amount: float = 0.0,
    signer_id: str = "system",
) -> str:
    """
    Generates a cryptographically signed authorization token encoding:
    - Approval tier (AUTO_APPROVE, HUMAN_REVIEW_MANAGER, HUMAN_REVIEW_SENIOR)
    - Target action and order_id
    - Approved amount and evaluation date
    - Signer ID
    """
    payload = {
        "tier": tier,
        "action": action,
        "order_id": order_id,
        "amount": round(float(amount), 2),
        "signer": signer_id,
        "date": EVALUATION_DATE,
    }
    canonical = json.dumps(payload, sort_keys=True).encode("utf-8")
    sig = hmac.new(SECRET_KEY, canonical, hashlib.sha256).hexdigest()
    encoded_payload = base64.urlsafe_b64encode(canonical).decode("utf-8")
    return f"{encoded_payload}.{sig}"


def _verify_single_token(token: str, action: str, order_id: str, amount: float) -> Optional[Dict[str, Any]]:
    """Verifies cryptographic signature and constraints for a single token."""
    if not token or "." not in token:
        return None
    try:
        encoded_payload, sig = token.strip().split(".", 1)
        canonical = base64.urlsafe_b64decode(encoded_payload.encode("utf-8"))
        expected_sig = hmac.new(SECRET_KEY, canonical, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        payload = json.loads(canonical.decode("utf-8"))
        if payload.get("action") != action:
            return None
        if payload.get("order_id") != order_id:
            return None
        # Approved token amount must cover the requested amount
        if round(amount, 2) > round(float(payload.get("amount", 0.0)) + 0.01, 2):
            return None
        return payload
    except Exception:
        return None


def verify_auth_token(
    auth_token: str,
    action: str,
    order_id: str,
    amount: float = 0.0,
) -> bool:
    """
    Validates token signatures and enforces RF3 approval tier hierarchy:
    - amount <= €50.00: requires at least 1 valid token (AUTO_APPROVE or higher)
    - €50.01 to €300.00: requires at least 1 MANAGER or SENIOR token
    - amount > €300.00: requires 2 distinct SENIOR tokens from different signers (or dual token joined by comma)
    """
    if not auth_token:
        return False

    tokens = [t.strip() for t in auth_token.split(",") if t.strip()]

    # High value > €300.00 requires two distinct senior signatures
    if amount > 300.00:
        if len(tokens) < 2:
            return False
        parsed_0 = _verify_single_token(tokens[0], action, order_id, amount)
        parsed_1 = _verify_single_token(tokens[1], action, order_id, amount)
        if not parsed_0 or not parsed_1:
            return False
        if parsed_0.get("tier") != "HUMAN_REVIEW_SENIOR" or parsed_1.get("tier") != "HUMAN_REVIEW_SENIOR":
            return False
        if parsed_0.get("signer") == parsed_1.get("signer"):
            return False  # Must be two distinct senior approvers
        return True

    # Moderate value €50.01 to €300.00 requires manager or senior
    parsed = _verify_single_token(tokens[0], action, order_id, amount)
    if not parsed:
        return False

    token_tier = parsed.get("tier")
    if amount > 50.00:
        return token_tier in {"HUMAN_REVIEW_MANAGER", "HUMAN_REVIEW_SENIOR"}

    # Autonomous tier <= €50.00 allows AUTO_APPROVE or higher
    return token_tier in {"AUTO_APPROVE", "HUMAN_REVIEW_MANAGER", "HUMAN_REVIEW_SENIOR"}


# ── Deterministic Policy Evaluation ─────────────────────────────────────────

def evaluate_return_and_refund(
    order: Dict[str, Any],
    customer: Dict[str, Any],
    reason: str,
    customer_refunds_90d: Optional[List[Dict[str, Any]]] = None,
    customer_refunds_24h: Optional[List[Dict[str, Any]]] = None,
    has_photo: bool = True,
) -> Dict[str, Any]:
    """
    Evaluates return and refund eligibility strictly adhering to RF1-RF9.
    Returns deterministic outcome code, refund breakdown, and auth token if approved.
    """
    rule_ids = []
    kb_citations = ["KB-01", "KB-02"]
    order_id = order["order_id"]
    customer_id = customer["customer_id"]

    # 1. Status Check
    status = order.get("status", "")
    if status == "processing":
        # Order is still processing: route to cancellation CN1
        return evaluate_cancellation(order)
    elif status != "delivered":
        return {
            "decision": "ANSWER_ONLY",
            "action": "none",
            "net_refund": 0.00,
            "fee_deducted": 0.00,
            "rule_ids": ["DL1"],
            "auth_token": None,
            "explanation": f"Order {order_id} is currently '{status}'. Items must be delivered before initiating a return.",
            "kb_citations": ["KB-01", "KB-05"],
        }

    # 2. Check Final Sale (RF8 / KB-08)
    is_final_sale = order.get("final_sale", False)
    clean_reason = reason.strip().lower()
    is_change_of_mind = clean_reason in {
        "changed mind",
        "changed_mind",
        "unwanted",
        "wrong size",
        "no longer needed",
        "does not fit",
        "don't fit",
    }

    if is_final_sale and is_change_of_mind:
        rule_ids.extend(["RF8", "KB-08"])
        return {
            "decision": "AUTO_DENY",
            "action": "none",
            "net_refund": 0.00,
            "fee_deducted": 0.00,
            "rule_ids": rule_ids,
            "auth_token": None,
            "explanation": f"Order {order_id} contains a final-sale item. Change-of-mind returns are not accepted for final sale items.",
            "kb_citations": ["KB-08"],
        }

    # 3. Check Delivery Date Window (RF1, RF7, RF9)
    days_since_delivery = get_days_elapsed(order.get("delivered_date"))
    if days_since_delivery is None:
        days_since_delivery = 0

    if days_since_delivery > 44:
        # Check for 12-month manufacturing warranty defect (RF9 / KB-04)
        if not is_change_of_mind and days_since_delivery <= 365:
            rule_ids.extend(["RF9", "KB-04"])
            return {
                "decision": "REQUEST_INFO",
                "action": "warranty_claim",
                "net_refund": 0.00,
                "fee_deducted": 0.00,
                "rule_ids": rule_ids,
                "auth_token": None,
                "explanation": "Return window has passed, but item may be eligible under our 12-month warranty. Please provide photos and proof of purchase for review.",
                "kb_citations": ["KB-04"],
            }
        rule_ids.extend(["RF7", "KB-01"])
        return {
            "decision": "AUTO_DENY",
            "action": "none",
            "net_refund": 0.00,
            "fee_deducted": 0.00,
            "rule_ids": rule_ids,
            "auth_token": None,
            "explanation": f"Return request was submitted {days_since_delivery} days after delivery, exceeding the 30-day window plus 14-day grace period.",
            "kb_citations": ["KB-01"],
        }

    if 31 <= days_since_delivery <= 44:
        rule_ids.extend(["RF7", "KB-01"])
        return {
            "decision": "HUMAN_REVIEW_AGENT",
            "action": "goodwill_return",
            "net_refund": 0.00,
            "fee_deducted": 0.00,
            "rule_ids": rule_ids,
            "auth_token": None,
            "explanation": f"Return requested {days_since_delivery - 30} days after standard 30-day window. Routed to frontline agent for goodwill review.",
            "kb_citations": ["KB-01"],
        }

    # 4. Standard Eligible Return (RF1, RF2)
    rule_ids.extend(["RF1", "RF2"])
    subtotal = float(order.get("subtotal_eur", 0.0))
    if is_change_of_mind:
        fee_deducted = 4.95
        net_refund = round(max(0.0, subtotal - fee_deducted), 2)
    else:
        fee_deducted = 0.00
        net_refund = round(subtotal, 2)

    # 5. Fraud Flag Check (RF5)
    if customer.get("fraud_flag", False):
        rule_ids.append("RF5")
        return {
            "decision": "HUMAN_REVIEW_MANAGER",
            "action": "refund_escalated",
            "net_refund": net_refund,
            "fee_deducted": fee_deducted,
            "rule_ids": rule_ids,
            "auth_token": None,
            "explanation": "Refund request requires tier 2 manager review.",
            "kb_citations": kb_citations,
        }

    # 6. Velocity Limit Check (RF4: >= 3 refunds in last 90 days)
    recent_90d_count = len(customer_refunds_90d) if customer_refunds_90d else 0
    if recent_90d_count >= 3:
        rule_ids.append("RF4")
        return {
            "decision": "HUMAN_REVIEW_MANAGER",
            "action": "refund_escalated",
            "net_refund": net_refund,
            "fee_deducted": fee_deducted,
            "rule_ids": rule_ids,
            "auth_token": None,
            "explanation": f"Customer has {recent_90d_count} refunds in last 90 days. Velocity limit reached; routed to manager.",
            "kb_citations": kb_citations,
        }

    # 7. Rolling 24-Hour Refund Sum & Approval Tiers (RF3)
    sum_24h = sum(float(r.get("amount_eur", 0.0)) for r in (customer_refunds_24h or []))
    total_24h_projected = round(sum_24h + net_refund, 2)
    rule_ids.append("RF3")

    if total_24h_projected <= 50.00:
        token = generate_auth_token(
            tier="AUTO_APPROVE",
            action="refund",
            order_id=order_id,
            amount=net_refund,
        )
        return {
            "decision": "AUTO_APPROVE",
            "action": "execute_refund",
            "net_refund": net_refund,
            "fee_deducted": fee_deducted,
            "rule_ids": rule_ids,
            "auth_token": token,
            "explanation": f"Refund of €{net_refund:.2f} qualifies for autonomous approval (<= €50.00).",
            "kb_citations": kb_citations,
        }
    elif total_24h_projected <= 300.00:
        return {
            "decision": "HUMAN_REVIEW_MANAGER",
            "action": "refund_escalated",
            "net_refund": net_refund,
            "fee_deducted": fee_deducted,
            "rule_ids": rule_ids,
            "auth_token": None,
            "explanation": f"Cumulative 24h refund sum (€{total_24h_projected:.2f}) exceeds €50.00; routed to manager.",
            "kb_citations": kb_citations,
        }
    else:
        return {
            "decision": "HUMAN_REVIEW_SENIOR",
            "action": "refund_escalated",
            "net_refund": net_refund,
            "fee_deducted": fee_deducted,
            "rule_ids": rule_ids,
            "auth_token": None,
            "explanation": f"Cumulative 24h refund sum (€{total_24h_projected:.2f}) exceeds €300.00; requires dual senior approval.",
            "kb_citations": kb_citations,
        }


def evaluate_replacement(
    order: Dict[str, Any],
    customer: Dict[str, Any],
    reason: str,
    has_photo: bool = True,
    photo_shows_label: bool = True,
) -> Dict[str, Any]:
    """
    Evaluates replacement eligibility (RP1-RP4).
    """
    order_id = order["order_id"]
    rule_ids = []
    kb_citations = ["KB-03"]

    # 1. Delivery window check
    days = get_days_elapsed(order.get("delivered_date"))
    if days is not None and days > 30:
        return {
            "decision": "REQUEST_INFO",
            "action": "warranty_claim",
            "rule_ids": ["RF9", "KB-04"],
            "auth_token": None,
            "explanation": "Replacement requested after 30 days. Handled under 12-month warranty (KB-04).",
            "kb_citations": ["KB-04"],
        }

    # 2. Photo requirement (RP2, KB-03)
    if not has_photo:
        return {
            "decision": "REQUEST_INFO",
            "action": "request_photo",
            "rule_ids": ["RP2", "KB-03"],
            "auth_token": None,
            "explanation": "A photo of the damaged or defective item is required to process a replacement.",
            "kb_citations": ["KB-03"],
        }

    clean_reason = reason.strip().lower()
    if "wrong" in clean_reason and not photo_shows_label:
        return {
            "decision": "REQUEST_INFO",
            "action": "request_label_photo",
            "rule_ids": ["RP1", "KB-03"],
            "auth_token": None,
            "explanation": "For incorrect items, KB-03 requires a photo showing both the item and its package label.",
            "kb_citations": ["KB-03"],
        }

    # 3. Fraud check (RF5)
    if customer.get("fraud_flag", False):
        return {
            "decision": "HUMAN_REVIEW_MANAGER",
            "action": "replacement_escalated",
            "rule_ids": ["RF5"],
            "auth_token": None,
            "explanation": "Replacement requires manager review.",
            "kb_citations": kb_citations,
        }

    # 4. In Stock Check (RP3)
    if not order.get("in_stock_for_replacement", True):
        return {
            "decision": "HUMAN_REVIEW_AGENT",
            "action": "offer_refund_alternative",
            "rule_ids": ["RP3", "KB-03"],
            "auth_token": None,
            "explanation": f"Item '{order['item']}' is currently out of stock for replacement. Offer customer refund path.",
            "kb_citations": ["KB-03"],
        }

    # 5. Value limit (€100) (RP3)
    subtotal = float(order.get("subtotal_eur", 0.0))
    if subtotal > 100.00:
        return {
            "decision": "HUMAN_REVIEW_MANAGER",
            "action": "replacement_escalated",
            "rule_ids": ["RP3"],
            "auth_token": None,
            "explanation": f"Item value (€{subtotal:.2f}) exceeds €100.00 threshold for autonomous replacement.",
            "kb_citations": kb_citations,
        }

    # 6. Eligible for Autonomous Replacement (RP1)
    token = generate_auth_token(
        tier="AUTO_APPROVE",
        action="replacement",
        order_id=order_id,
        amount=subtotal,
    )
    return {
        "decision": "AUTO_APPROVE",
        "action": "execute_replacement",
        "rule_ids": ["RP1", "KB-03"],
        "auth_token": token,
        "explanation": f"Free replacement approved for '{order['item']}' under RP1 (dispatched within 2 business days).",
        "kb_citations": kb_citations,
    }


def evaluate_delivery(
    order: Dict[str, Any],
    reported_not_received: bool = False,
) -> Dict[str, Any]:
    """
    Evaluates delivery status and late parcel compensation (DL1-DL5).
    """
    order_id = order["order_id"]
    status = order.get("status", "")

    # DL5: Delivered according to tracking but customer reports not received
    if reported_not_received and status == "delivered":
        return {
            "decision": "HUMAN_REVIEW_AGENT",
            "action": "open_carrier_investigation",
            "rule_ids": ["DL5", "KB-06"],
            "auth_token": None,
            "explanation": "Parcel marked delivered but missing. Carrier investigation opened (up to 10 business days). No immediate refund.",
            "kb_citations": ["KB-06"],
        }

    # DL4: Lost in transit (15+ days without scan)
    last_scan = order.get("last_scan_date")
    if last_scan:
        days_no_scan = get_days_elapsed(last_scan)
        if days_no_scan is not None and days_no_scan >= 15:
            return {
                "decision": "HUMAN_REVIEW_MANAGER",
                "action": "lost_parcel_resolution",
                "rule_ids": ["DL4", "KB-06"],
                "auth_token": None,
                "explanation": f"Parcel has had no tracking scan for {days_no_scan} days. Presumed lost; routed to manager.",
                "kb_citations": ["KB-06"],
            }

    # Check delivery lateness based on est_delivery
    est_delivery = order.get("est_delivery")
    bus_days_late = get_business_days_late(est_delivery)
    shipping_fee = float(order.get("shipping_fee_eur", 0.0))

    if bus_days_late > 5:
        # DL3: >5 business days late -> refund shipping fee
        token = (
            generate_auth_token("AUTO_APPROVE", "refund", order_id, shipping_fee)
            if shipping_fee > 0
            else None
        )
        return {
            "decision": "AUTO_APPROVE" if shipping_fee > 0 else "ANSWER_ONLY",
            "action": "refund_shipping_fee" if shipping_fee > 0 else "tracking_update",
            "net_refund": shipping_fee,
            "fee_deducted": 0.00,
            "rule_ids": ["DL3", "KB-06"],
            "auth_token": token,
            "explanation": f"Parcel is {bus_days_late} business days late (>5 days). Standard shipping fee of €{shipping_fee:.2f} refunded.",
            "kb_citations": ["KB-06"],
        }
    elif bus_days_late >= 1:
        # DL2: 1-5 business days late -> apologize and provide tracking, no compensation
        return {
            "decision": "ANSWER_ONLY",
            "action": "tracking_update",
            "net_refund": 0.00,
            "fee_deducted": 0.00,
            "rule_ids": ["DL2", "KB-06"],
            "auth_token": None,
            "explanation": f"Parcel is {bus_days_late} business days late. Tracking provided; please allow standard arrival time.",
            "kb_citations": ["KB-06"],
        }
    else:
        # DL1: On time
        return {
            "decision": "ANSWER_ONLY",
            "action": "tracking_update",
            "net_refund": 0.00,
            "fee_deducted": 0.00,
            "rule_ids": ["DL1", "KB-05"],
            "auth_token": None,
            "explanation": f"Parcel is within expected delivery timeline (estimated: {est_delivery}).",
            "kb_citations": ["KB-05"],
        }


def evaluate_cancellation(order: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates order cancellation (CN1, CN2).
    """
    order_id = order["order_id"]
    status = order.get("status", "")

    if status == "processing":
        subtotal = float(order.get("subtotal_eur", 0.0))
        shipping = float(order.get("shipping_fee_eur", 0.0))
        total_refund = round(subtotal + shipping, 2)
        token = generate_auth_token("AUTO_APPROVE", "cancel", order_id, total_refund)
        return {
            "decision": "AUTO_APPROVE",
            "action": "cancel_order",
            "net_refund": total_refund,
            "fee_deducted": 0.00,
            "rule_ids": ["CN1", "KB-07"],
            "auth_token": token,
            "explanation": f"Order {order_id} is 'processing'. Cancelled with 100% refund (€{total_refund:.2f}) including shipping.",
            "kb_citations": ["KB-07", "KB-02"],
        }
    else:
        return {
            "decision": "ANSWER_ONLY",
            "action": "provide_return_instructions",
            "net_refund": 0.00,
            "fee_deducted": 0.00,
            "rule_ids": ["CN2", "KB-07", "KB-01"],
            "auth_token": None,
            "explanation": f"Order {order_id} has already dispatched/delivered ('{status}'). It cannot be cancelled, but may be returned upon arrival.",
            "kb_citations": ["KB-07", "KB-01"],
        }


def evaluate_billing(
    order: Dict[str, Any],
    payments: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Evaluates billing inquiries and duplicate payment claims (BL1-BL3).
    """
    order_id = order["order_id"]
    captured = [p for p in payments if p.get("status") == "captured"]

    # BL1: Duplicate Payment (2 or more captured payments)
    if len(captured) >= 2:
        duplicate_payment = captured[1]
        dup_amount = float(duplicate_payment.get("amount_eur", 0.0))
        token = generate_auth_token("AUTO_APPROVE", "refund", order_id, dup_amount)
        return {
            "decision": "AUTO_APPROVE",
            "action": "refund_duplicate_payment",
            "net_refund": dup_amount,
            "fee_deducted": 0.00,
            "rule_ids": ["BL1", "KB-09", "KB-02"],
            "auth_token": token,
            "explanation": f"Confirmed duplicate payment of €{dup_amount:.2f} for order {order_id}. Refund issued (3-5 business days).",
            "kb_citations": ["KB-09", "KB-02"],
        }

    return {
        "decision": "HUMAN_REVIEW_AGENT",
        "action": "investigate_payment",
        "net_refund": 0.00,
        "fee_deducted": 0.00,
        "rule_ids": ["BL2"],
        "auth_token": None,
        "explanation": f"No duplicate payment found on file for order {order_id}. Routed to billing agent for investigation.",
        "kb_citations": ["KB-09"],
    }


def evaluate_escalations(text: str) -> Optional[Dict[str, Any]]:
    """
    Detects critical escalation triggers: safety/hazards (ES1), legal threats (ES2),
    chargebacks (ES3), explicit agent requests (ES6), and deliberately missing policies (ES7).
    """
    lower = text.lower()

    # ES1: Safety, fire, smoke, burns, bodily injury, violent threats
    safety_triggers = [
        "overheat", "overheating", "caught fire", "caught on fire", "fire",
        "smoke", "smoking", "burned", "burning", "exploded", "shocked",
        "injury", "injured", "hospital", "poison", "violent", "kill"
    ]
    if any(trigger in lower for trigger in safety_triggers):
        return {
            "decision": "ESCALATE_URGENT",
            "action": "safety_escalation",
            "rule_ids": ["ES1", "KB-11"],
            "auth_token": None,
            "explanation": "Safety hazard or bodily injury detected. Instruct customer to cease use immediately; urgent same-day human escalation.",
            "kb_citations": ["KB-11"],
        }

    # ES2: Legal threats
    legal_triggers = ["lawyer", "attorney", "sue you", "legal action", "lawsuit", "court", "litigation"]
    if any(trigger in lower for trigger in legal_triggers):
        return {
            "decision": "HUMAN_REVIEW_SENIOR",
            "action": "legal_review",
            "rule_ids": ["ES2", "KB-10"],
            "auth_token": None,
            "explanation": "Explicit legal or attorney threat detected. Neutral acknowledgment; routed to senior management.",
            "kb_citations": ["KB-10"],
        }

    # ES3: Chargeback or bank dispute
    dispute_triggers = ["chargeback", "bank dispute", "disputed with my bank", "dispute with credit card"]
    if any(trigger in lower for trigger in dispute_triggers):
        return {
            "decision": "HUMAN_REVIEW_SENIOR",
            "action": "dispute_review",
            "rule_ids": ["ES3", "KB-09"],
            "auth_token": None,
            "explanation": "Bank dispute or chargeback reported. Flagged for senior billing review; no automated refund.",
            "kb_citations": ["KB-09"],
        }

    # ES6: Explicit customer request for human
    human_triggers = ["speak to a human", "talk to a person", "talk to a real person", "human agent", "real agent"]
    if any(trigger in lower for trigger in human_triggers):
        return {
            "decision": "HANDOFF",
            "action": "human_handoff",
            "rule_ids": ["ES6", "KB-11"],
            "auth_token": None,
            "explanation": "Customer requested human support agent. Handoff queued with case summary.",
            "kb_citations": ["KB-11"],
        }

    # ES7: Missing topics from KB (price matching, gift cards, loyalty points)
    missing_topics = ["price match", "gift card", "loyalty point", "loyalty program", "bulk order", "wholesale"]
    if any(trigger in lower for trigger in missing_topics):
        return {
            "decision": "REFUSE_NO_POLICY",
            "action": "refuse_and_queue",
            "rule_ids": ["ES7", "missing_topics"],
            "auth_token": None,
            "explanation": "Inquiry covers a topic deliberately unaddressed in automated knowledge base. System refuses to hallucinate.",
            "kb_citations": [],
        }

    return None

