"""
MCP Tools Implementation for Resolve Support Desk.
Provides read-only mock data retrieval and state-changing action tools
with strict parameter validation, token verification, and idempotency guarantees.
"""

import csv
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.config import DATA_DIR, EVALUATION_DATE

IDEMPOTENCY_CACHE_FILE = DATA_DIR / ".idempotency_cache.json"


def _read_csv(filename: str) -> List[Dict[str, str]]:
    """Reads a CSV file from DATA_DIR and returns a list of row dicts."""
    file_path = DATA_DIR / filename
    if not file_path.is_file():
        return []
    with open(file_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _load_idempotency_cache() -> Dict[str, Any]:
    """Loads cached results for idempotency checks."""
    if not IDEMPOTENCY_CACHE_FILE.is_file():
        return {}
    try:
        with open(IDEMPOTENCY_CACHE_FILE, mode="r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_idempotency_cache(cache: Dict[str, Any]) -> None:
    """Persists idempotency cache to disk."""
    with open(IDEMPOTENCY_CACHE_FILE, mode="w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def reset_mock_data() -> None:
    """
    Clears the idempotency cache and restores refund_history.csv to its default initial state.
    Helpful for clean test runs.
    """
    if IDEMPOTENCY_CACHE_FILE.is_file():
        IDEMPOTENCY_CACHE_FILE.unlink()

    initial_refunds = [
        {"refund_id": "R-310", "customer_id": "C001", "order_id": "O-0870", "date": "2026-05-14", "amount_eur": "18.00", "status": "approved"},
        {"refund_id": "R-420", "customer_id": "C003", "order_id": "O-0990", "date": "2026-09-30", "amount_eur": "60.00", "status": "approved"},
        {"refund_id": "R-501", "customer_id": "C002", "order_id": "O-0940", "date": "2026-08-12", "amount_eur": "30.00", "status": "approved"},
        {"refund_id": "R-502", "customer_id": "C002", "order_id": "O-0961", "date": "2026-09-05", "amount_eur": "45.00", "status": "approved"},
        {"refund_id": "R-503", "customer_id": "C002", "order_id": "O-0985", "date": "2026-10-01", "amount_eur": "20.00", "status": "approved"},
    ]
    refund_file = DATA_DIR / "refund_history.csv"
    with open(refund_file, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["refund_id", "customer_id", "order_id", "date", "amount_eur", "status"])
        writer.writeheader()
        writer.writerows(initial_refunds)


# ── Read-Only Data Retrieval Tools ──────────────────────────────────────────

def get_customer(email: str) -> Optional[Dict[str, Any]]:
    """Retrieve customer profile by email address (case-insensitive)."""
    if not email:
        return None
    normalized_email = email.strip().lower()
    for row in _read_csv("customers.csv"):
        if row.get("email", "").strip().lower() == normalized_email:
            return {
                "customer_id": row["customer_id"],
                "name": row["name"],
                "email": row["email"],
                "language": row["language"],
                "fraud_flag": row.get("fraud_flag", "false").strip().lower() == "true",
                "created_at": row["created_at"],
            }
    return None


def get_customer_by_id(customer_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve customer profile by customer ID."""
    if not customer_id:
        return None
    cid = customer_id.strip()
    for row in _read_csv("customers.csv"):
        if row.get("customer_id", "").strip() == cid:
            return {
                "customer_id": row["customer_id"],
                "name": row["name"],
                "email": row["email"],
                "language": row["language"],
                "fraud_flag": row.get("fraud_flag", "false").strip().lower() == "true",
                "created_at": row["created_at"],
            }
    return None


def get_order(order_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve order details, status, timestamps, and line items."""
    if not order_id:
        return None
    oid = order_id.strip()
    for row in _read_csv("orders.csv"):
        if row.get("order_id", "").strip() == oid:
            return {
                "order_id": row["order_id"],
                "customer_id": row["customer_id"],
                "order_date": row["order_date"],
                "status": row["status"],
                "est_delivery": row.get("est_delivery") or None,
                "delivered_date": row.get("delivered_date") or None,
                "last_scan_date": row.get("last_scan_date") or None,
                "item": row["item"],
                "subtotal_eur": float(row["subtotal_eur"]),
                "shipping_fee_eur": float(row["shipping_fee_eur"]),
                "final_sale": row.get("final_sale", "false").strip().lower() == "true",
                "in_stock_for_replacement": row.get("in_stock_for_replacement", "true").strip().lower() == "true",
            }
    return None


def get_customer_orders(customer_id: str, days_limit: int = 60) -> List[Dict[str, Any]]:
    """Fetch orders placed by the customer within the last N days (default 60 days)."""
    if not customer_id:
        return []
    cid = customer_id.strip()
    orders = []
    from datetime import date
    eval_d = date.fromisoformat(EVALUATION_DATE)

    for row in _read_csv("orders.csv"):
        if row.get("customer_id", "").strip() == cid:
            order_d = date.fromisoformat(row["order_date"])
            days_diff = (eval_d - order_d).days
            if 0 <= days_diff <= days_limit:
                orders.append({
                    "order_id": row["order_id"],
                    "customer_id": row["customer_id"],
                    "order_date": row["order_date"],
                    "status": row["status"],
                    "est_delivery": row.get("est_delivery") or None,
                    "delivered_date": row.get("delivered_date") or None,
                    "last_scan_date": row.get("last_scan_date") or None,
                    "item": row["item"],
                    "subtotal_eur": float(row["subtotal_eur"]),
                    "shipping_fee_eur": float(row["shipping_fee_eur"]),
                    "final_sale": row.get("final_sale", "false").strip().lower() == "true",
                    "in_stock_for_replacement": row.get("in_stock_for_replacement", "true").strip().lower() == "true",
                    "days_ago": days_diff,
                })
    orders.sort(key=lambda x: x["order_date"], reverse=True)
    return orders


def get_refund_history(customer_id: str, days_limit: int = 90) -> List[Dict[str, Any]]:
    """Fetch refunds issued to customer in the last N days (default 90 days for velocity check)."""
    if not customer_id:
        return []
    cid = customer_id.strip()
    refunds = []
    from datetime import date
    eval_d = date.fromisoformat(EVALUATION_DATE)

    for row in _read_csv("refund_history.csv"):
        if row.get("customer_id", "").strip() == cid:
            refund_d = date.fromisoformat(row["date"])
            days_diff = (eval_d - refund_d).days
            if 0 <= days_diff <= days_limit:
                refunds.append({
                    "refund_id": row["refund_id"],
                    "customer_id": row["customer_id"],
                    "order_id": row["order_id"],
                    "date": row["date"],
                    "amount_eur": float(row["amount_eur"]),
                    "status": row["status"],
                    "days_ago": days_diff,
                })
    refunds.sort(key=lambda x: x["date"], reverse=True)
    return refunds


def get_payments(order_id: str) -> List[Dict[str, Any]]:
    """Fetch payment transactions for an order (needed for BL1 duplicate charge check)."""
    if not order_id:
        return []
    oid = order_id.strip()
    payments = []
    for row in _read_csv("payments.csv"):
        if row.get("order_id", "").strip() == oid:
            payments.append({
                "payment_id": row["payment_id"],
                "order_id": row["order_id"],
                "amount_eur": float(row["amount_eur"]),
                "status": row["status"],
                "captured_at": row["captured_at"],
            })
    return payments


# ── State-Changing Action Tools ─────────────────────────────────────────────

def calculate_refund_amount(order_id: str, item_id: str = "", reason: str = "changed_mind") -> Dict[str, Any]:
    """
    Computes exact refund according to Rule RF2:
    - 'changed_mind' / 'changed mind' / 'unwanted' / 'wrong size':
      item subtotal minus €4.95 label fee (original shipping excluded).
    - 'defective', 'damaged', 'wrong_item', 'wrong item', 'not as described':
      full item subtotal.
    Returns: {'order_id': str, 'subtotal': float, 'fee_deducted': float, 'net_refund': float, 'currency': 'EUR'}
    """
    order = get_order(order_id)
    if not order:
        raise ValueError(f"Order not found: {order_id}")

    subtotal = order["subtotal_eur"]
    normalized_reason = reason.strip().lower()

    change_of_mind_reasons = {
        "changed mind",
        "changed_mind",
        "unwanted",
        "wrong size",
        "no longer needed",
        "does not fit",
        "don't fit",
    }

    if normalized_reason in change_of_mind_reasons:
        fee_deducted = 4.95
        net_refund = round(max(0.0, subtotal - fee_deducted), 2)
    else:
        fee_deducted = 0.00
        net_refund = round(subtotal, 2)

    return {
        "order_id": order_id,
        "subtotal": subtotal,
        "fee_deducted": fee_deducted,
        "net_refund": net_refund,
        "currency": "EUR",
    }


def execute_refund(
    order_id: str,
    amount: float,
    reason: str,
    auth_token: str,
    idempotency_key: str,
) -> Dict[str, Any]:
    """
    Appends an approved refund to refund_history.csv and enforces:
    - Positive numeric amount.
    - Idempotency: repeated key returns original result without duplicate record.
    - Balance cap (RF6): amount cannot exceed subtotal minus prior refunds.
    - Cryptographic auth token verification (RF3 tiers: single vs dual senior approval).
    """
    # 1. Idempotency Check
    cache = _load_idempotency_cache()
    if idempotency_key in cache:
        return cache[idempotency_key]

    # 2. Amount Validation
    try:
        amount = round(float(amount), 2)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid refund amount: {amount}")

    if amount <= 0:
        raise ValueError(f"Refund amount must be greater than zero. Received: {amount}")

    # 3. Order Lookup
    order = get_order(order_id)
    if not order:
        raise ValueError(f"Order not found: {order_id}")

    # 4. Token Verification (deny unauthorized calls before checking balance)
    from src.policy_engine import verify_auth_token

    if not verify_auth_token(auth_token, action="refund", order_id=order_id, amount=amount):
        raise PermissionError(
            f"Invalid or unauthorized auth token for refund of €{amount:.2f} on order {order_id}"
        )

    # 5. Check Prior Refunds (RF6)
    existing_refunds = [
        float(r["amount_eur"])
        for r in _read_csv("refund_history.csv")
        if r.get("order_id", "").strip() == order_id and r.get("status") == "approved"
    ]
    prior_refund_total = round(sum(existing_refunds), 2)
    max_eligible = round(order["subtotal_eur"] - prior_refund_total, 2)

    # Allow shipping refund if reason specifically indicates late shipping
    if "shipping" in reason.lower() and amount <= order["shipping_fee_eur"]:
        max_eligible = order["shipping_fee_eur"]

    if round(amount, 2) > round(max_eligible + 0.01, 2):
        raise ValueError(
            f"Refund amount €{amount:.2f} exceeds remaining eligible balance of €{max_eligible:.2f} (RF6)"
        )

    # 6. Append to refund_history.csv
    refund_rows = _read_csv("refund_history.csv")
    max_id = 500
    for r in refund_rows:
        rid = r.get("refund_id", "")
        if rid.startswith("R-"):
            try:
                num = int(rid[2:])
                if num > max_id:
                    max_id = num
            except ValueError:
                pass
    new_refund_id = f"R-{max_id + 1}"

    new_row = {
        "refund_id": new_refund_id,
        "customer_id": order["customer_id"],
        "order_id": order_id,
        "date": EVALUATION_DATE,
        "amount_eur": f"{amount:.2f}",
        "status": "approved",
    }

    refund_file = DATA_DIR / "refund_history.csv"
    with open(refund_file, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["refund_id", "customer_id", "order_id", "date", "amount_eur", "status"]
        )
        writer.writerow(new_row)

    result = {
        "status": "success",
        "refund_id": new_refund_id,
        "order_id": order_id,
        "customer_id": order["customer_id"],
        "amount_eur": amount,
        "date": EVALUATION_DATE,
        "idempotency_key": idempotency_key,
    }

    # 7. Save to Idempotency Cache
    cache[idempotency_key] = result
    _save_idempotency_cache(cache)

    return result


def cancel_order(order_id: str, auth_token: str) -> Dict[str, Any]:
    """Cancels an order if status == 'processing' and issues 100% refund including shipping (CN1)."""
    from src.policy_engine import verify_auth_token

    order = get_order(order_id)
    if not order:
        raise ValueError(f"Order not found: {order_id}")

    if order["status"] != "processing":
        raise ValueError(
            f"Order {order_id} has status '{order['status']}'. Only 'processing' orders can be cancelled (CN1)."
        )

    refund_amount = round(order["subtotal_eur"] + order["shipping_fee_eur"], 2)

    if not verify_auth_token(auth_token, action="cancel", order_id=order_id, amount=refund_amount):
        raise PermissionError(f"Invalid auth token for cancellation of order {order_id}")

    return {
        "status": "cancelled",
        "order_id": order_id,
        "refund_amount_eur": refund_amount,
        "currency": "EUR",
        "message": f"Order {order_id} successfully cancelled. Full refund of €{refund_amount:.2f} issued.",
    }


def execute_replacement(order_id: str, item_id: str, auth_token: str) -> Dict[str, Any]:
    """Issues a free replacement for a damaged, defective, or wrong item (RP1)."""
    from src.policy_engine import verify_auth_token

    order = get_order(order_id)
    if not order:
        raise ValueError(f"Order not found: {order_id}")

    if not order["in_stock_for_replacement"]:
        raise ValueError(f"Item '{order['item']}' is out of stock for replacement (RP3).")

    if not verify_auth_token(auth_token, action="replacement", order_id=order_id, amount=order["subtotal_eur"]):
        raise PermissionError(f"Invalid auth token for replacement on order {order_id}")

    return {
        "status": "replacement_ordered",
        "order_id": order_id,
        "item": order["item"],
        "cost_to_customer_eur": 0.00,
        "dispatch_sla": "2 business days",
    }


def update_shipping_address(order_id: str, new_address: str, auth_token: str) -> Dict[str, Any]:
    """Updates delivery address if status == 'processing' (DL6)."""
    from src.policy_engine import verify_auth_token

    order = get_order(order_id)
    if not order:
        raise ValueError(f"Order not found: {order_id}")

    if order["status"] != "processing":
        raise ValueError(
            f"Address cannot be updated for order {order_id} because status is '{order['status']}' (DL6)."
        )

    if not verify_auth_token(auth_token, action="update_address", order_id=order_id):
        raise PermissionError(f"Invalid auth token for address update on order {order_id}")

    return {
        "status": "address_updated",
        "order_id": order_id,
        "new_address": new_address,
    }
