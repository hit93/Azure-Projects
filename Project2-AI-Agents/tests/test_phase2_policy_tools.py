"""
Unit & Integration Verification for Phase 2: Local Tools & Deterministic Policy Engine.
Tests all MCP database tools, RF1-RF9 rules, financial boundaries, velocity limits,
idempotency, and escalation handlers.
"""

import sys
from pathlib import Path
import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from src.tools.mcp_tools import (
    get_customer,
    get_order,
    get_customer_orders,
    get_refund_history,
    get_payments,
    calculate_refund_amount,
    execute_refund,
    cancel_order,
    execute_replacement,
    update_shipping_address,
    reset_mock_data,
)
from src.policy_engine import (
    EVAL_DATE,
    generate_auth_token,
    verify_auth_token,
    evaluate_return_and_refund,
    evaluate_replacement,
    evaluate_delivery,
    evaluate_cancellation,
    evaluate_billing,
    evaluate_escalations,
)


def setup_function():
    """Reset mock database state before each test run."""
    reset_mock_data()


def teardown_function():
    """Clean up after test run."""
    reset_mock_data()


# ── 1. Read-Only Retrieval Tools ─────────────────────────────────────────────

def test_get_customer():
    print("[1/12] Testing Customer Retrieval Tool...")
    # Exact and case-insensitive check
    c1 = get_customer("anna@example.com")
    assert c1 is not None
    assert c1["customer_id"] == "C001"
    assert c1["fraud_flag"] is False

    c2 = get_customer("CARLA@EXAMPLE.COM")
    assert c2 is not None
    assert c2["customer_id"] == "C003"
    assert c2["fraud_flag"] is True

    assert get_customer("nonexistent@example.com") is None


def test_get_order():
    print("[2/12] Testing Order Retrieval Tool...")
    order = get_order("O-1001")
    assert order is not None
    assert order["customer_id"] == "C001"
    assert order["subtotal_eur"] == 39.90
    assert order["shipping_fee_eur"] == 4.95
    assert order["status"] == "delivered"
    assert order["final_sale"] is False

    assert get_order("O-9999") is None


def test_get_customer_orders_and_history():
    print("[3/12] Testing Customer Orders and Velocity History...")
    # Customer C001 orders in last 60 days
    c1_orders = get_customer_orders("C001", days_limit=60)
    assert len(c1_orders) >= 2

    # Customer C002 has 3 refunds in last 90 days
    c2_refunds = get_refund_history("C002", days_limit=90)
    assert len(c2_refunds) == 3


def test_get_payments():
    print("[4/12] Testing Payment Transactions...")
    payments = get_payments("O-1007")
    assert len(payments) == 2
    assert payments[0]["amount_eur"] == 74.50
    assert payments[1]["amount_eur"] == 74.50


# ── 2. Refund Calculation (RF2) ──────────────────────────────────────────────

def test_calculate_refund_amount():
    print("[5/12] Testing Refund Calculation (RF2 Label Fee)...")
    # Change of mind: €39.90 - €4.95 = €34.95
    calc_mind = calculate_refund_amount("O-1001", reason="changed mind")
    assert calc_mind["subtotal"] == 39.90
    assert calc_mind["fee_deducted"] == 4.95
    assert calc_mind["net_refund"] == 34.95

    # Defective / Damaged: €39.90 - €0.00 = €39.90
    calc_defect = calculate_refund_amount("O-1001", reason="defective")
    assert calc_defect["subtotal"] == 39.90
    assert calc_defect["fee_deducted"] == 0.00
    assert calc_defect["net_refund"] == 39.90


# ── 3. Deterministic Financial Thresholds & Boundaries (RF3) ─────────────────

def test_boundary_financial_tiers():
    print("[6/12] Testing Financial Boundaries (€50.00 vs €50.01 vs €300.00)...")
    c_eva = get_customer("eva@example.com")
    c_hana = get_customer("hana@example.com")
    c_dev = get_customer("dev@example.com")

    # Boundary 1: O-1014 subtotal is exactly €50.00 (damaged, no fee) -> AUTO_APPROVE
    o_50 = get_order("O-1014")
    assert o_50["subtotal_eur"] == 50.00
    res_50 = evaluate_return_and_refund(o_50, c_eva, reason="damaged")
    assert res_50["decision"] == "AUTO_APPROVE"
    assert res_50["net_refund"] == 50.00
    assert res_50["auth_token"] is not None

    # Boundary 2: O-1015 subtotal is €50.01 (damaged, no fee) -> HUMAN_REVIEW_MANAGER
    o_50_01 = get_order("O-1015")
    assert o_50_01["subtotal_eur"] == 50.01
    res_50_01 = evaluate_return_and_refund(o_50_01, c_hana, reason="damaged")
    assert res_50_01["decision"] == "HUMAN_REVIEW_MANAGER"
    assert res_50_01["net_refund"] == 50.01
    assert res_50_01["auth_token"] is None

    # Boundary 3: O-1005 subtotal is €389.00 -> HUMAN_REVIEW_SENIOR
    o_389 = get_order("O-1005")
    assert o_389["subtotal_eur"] == 389.00
    res_389 = evaluate_return_and_refund(o_389, c_dev, reason="defective")
    assert res_389["decision"] == "HUMAN_REVIEW_SENIOR"


# ── 4. Velocity Limits, Fraud Flags, & Rolling 24h Sum (RF3, RF4, RF5) ────────

def test_velocity_limit_rf4():
    print("[7/12] Testing Refund Velocity Limit (RF4)...")
    # Customer C002 has 3 refunds in last 90 days. Even a €30 refund must route to manager.
    c2 = get_customer("ben@example.com")
    c2_orders = get_customer_orders("C002")
    c2_order = get_order("O-1012")  # subtotal €35.00
    c2_refunds_90d = get_refund_history("C002", days_limit=90)

    res = evaluate_return_and_refund(
        c2_order,
        c2,
        reason="defective",
        customer_refunds_90d=c2_refunds_90d,
    )
    assert res["decision"] == "HUMAN_REVIEW_MANAGER"
    assert "RF4" in res["rule_ids"]


def test_fraud_flag_rf5():
    print("[8/12] Testing Fraud Flag Protection (RF5)...")
    # Customer C003 has fraud_flag = True
    c3 = get_customer("carla@example.com")
    assert c3["fraud_flag"] is True
    o_small = get_order("O-1013")  # subtotal €29.00

    res = evaluate_return_and_refund(o_small, c3, reason="changed mind")
    assert res["decision"] == "HUMAN_REVIEW_MANAGER"
    assert "RF5" in res["rule_ids"]


def test_rolling_24h_sum_split_refund_exploit():
    print("[9/12] Testing 24h Rolling Sum Split-Refund Exploit Protection...")
    c_anna = get_customer("anna@example.com")
    o_1001 = get_order("O-1001")  # €39.90 - €4.95 = €34.95

    # First refund today: €34.95 -> AUTO_APPROVE
    res1 = evaluate_return_and_refund(o_1001, c_anna, reason="changed mind", customer_refunds_24h=[])
    assert res1["decision"] == "AUTO_APPROVE"

    # Split refund attack: Same customer attempts another €30.00 refund on same day.
    # Total becomes €34.95 + €30.00 = €64.95 > €50.00 -> HUMAN_REVIEW_MANAGER
    prior_24h = [{"amount_eur": 34.95, "date": "2026-10-20"}]
    res2 = evaluate_return_and_refund(o_1001, c_anna, reason="changed mind", customer_refunds_24h=prior_24h)
    assert res2["decision"] == "HUMAN_REVIEW_MANAGER"


# ── 5. Delivery, Cancellation & Billing Rules (DL3, DL4, DL5, CN1, BL1) ──────

def test_delivery_cancellation_billing():
    print("[10/12] Testing Delivery, Cancellation & Billing Policies...")
    # DL3: O-1002 was due Oct 9. On Oct 20 (7 business days late) -> refund shipping €4.95
    o_late = get_order("O-1002")
    res_dl3 = evaluate_delivery(o_late)
    assert res_dl3["decision"] == "AUTO_APPROVE"
    assert res_dl3["net_refund"] == 4.95
    assert "DL3" in res_dl3["rule_ids"]

    # DL4: O-1016 no scan since Sept 30 (20 calendar days) -> lost parcel manager review
    o_lost = get_order("O-1016")
    res_dl4 = evaluate_delivery(o_lost)
    assert res_dl4["decision"] == "HUMAN_REVIEW_MANAGER"
    assert "DL4" in res_dl4["rule_ids"]

    # CN1: O-1008 is in 'processing' -> AUTO_APPROVE cancellation + 100% refund (€58 + €4.95)
    o_proc = get_order("O-1008")
    res_cn1 = evaluate_cancellation(o_proc)
    assert res_cn1["decision"] == "AUTO_APPROVE"
    assert res_cn1["net_refund"] == 62.95

    # BL1: O-1007 has duplicate payment P-7002 of €74.50 -> AUTO_APPROVE
    o_dup = get_order("O-1007")
    payments_dup = get_payments("O-1007")
    res_bl1 = evaluate_billing(o_dup, payments_dup)
    assert res_bl1["decision"] == "AUTO_APPROVE"
    assert res_bl1["net_refund"] == 74.50


# ── 6. Critical Safety & Legal Escalations (ES1, ES2, ES7) ───────────────────

def test_escalation_rules():
    print("[11/12] Testing Safety (ES1), Legal (ES2), and Missing Policy (ES7)...")
    # ES1: Battery overheating / fire
    res_es1 = evaluate_escalations("The headlamp battery overheated and caught fire while charging!")
    assert res_es1 is not None
    assert res_es1["decision"] == "ESCALATE_URGENT"

    # ES2: Attorney threat
    res_es2 = evaluate_escalations("I will speak with my lawyer and take legal action in court.")
    assert res_es2 is not None
    assert res_es2["decision"] == "HUMAN_REVIEW_SENIOR"

    # ES7: Price match (intentionally missing from KB)
    res_es7 = evaluate_escalations("Do you offer a competitor price match policy?")
    assert res_es7 is not None
    assert res_es7["decision"] == "REFUSE_NO_POLICY"


# ── 7. Tool Execution & Idempotency Guarantee ────────────────────────────────

def test_execute_refund_idempotency_and_security():
    print("[12/12] Testing Execute Refund Tool & Idempotency...")
    # 1. Successful execution with valid auth token
    token = generate_auth_token("AUTO_APPROVE", "refund", "O-1001", 34.95)
    key = "idem-test-key-001"

    res_1 = execute_refund(
        order_id="O-1001",
        amount=34.95,
        reason="changed mind",
        auth_token=token,
        idempotency_key=key,
    )
    assert res_1["status"] == "success"
    assert res_1["amount_eur"] == 34.95
    refund_id_1 = res_1["refund_id"]

    # 2. Idempotency Check: Calling again with SAME key returns same result without duplicate row
    res_2 = execute_refund(
        order_id="O-1001",
        amount=34.95,
        reason="changed mind",
        auth_token=token,
        idempotency_key=key,
    )
    assert res_2["status"] == "success"
    assert res_2["refund_id"] == refund_id_1

    # 3. Security: Attempting refund with invalid token must raise PermissionError
    fake_token = "invalid.token.payload"
    try:
        execute_refund("O-1001", 10.00, "changed mind", fake_token, "idem-test-key-fake")
        assert False, "Execution should have failed with invalid token"
    except PermissionError:
        pass

    # 4. Security: Attempting refund exceeding balance must raise ValueError (RF6)
    try:
        token_s1 = generate_auth_token("HUMAN_REVIEW_SENIOR", "refund", "O-1003", 500.00, signer_id="senior_1")
        token_s2 = generate_auth_token("HUMAN_REVIEW_SENIOR", "refund", "O-1003", 500.00, signer_id="senior_2")
        dual_senior_token = f"{token_s1},{token_s2}"
        execute_refund("O-1003", 500.00, "defective", dual_senior_token, "idem-test-key-over")
        assert False, "Execution should have failed due to RF6 balance cap"
    except ValueError as val_err:
        assert "exceeds remaining eligible balance" in str(val_err)


if __name__ == "__main__":
    print("\n" + "=" * 65)
    print("PHASE 2 COMPREHENSIVE VERIFICATION RUN")
    print("=" * 65)
    try:
        setup_function()
        test_get_customer()
        test_get_order()
        test_get_customer_orders_and_history()
        test_get_payments()
        test_calculate_refund_amount()
        test_boundary_financial_tiers()
        test_velocity_limit_rf4()
        test_fraud_flag_rf5()
        test_rolling_24h_sum_split_refund_exploit()
        test_delivery_cancellation_billing()
        test_escalation_rules()
        test_execute_refund_idempotency_and_security()
        teardown_function()
        print("\n" + "=" * 65)
        print("ALL 12 PHASE 2 VERIFICATION TESTS PASSED SUCCESSFULLY!")
        print("=" * 65 + "\n")
    except AssertionError as err:
        print(f"\n[FAIL] Phase 2 Test Failed: {err}")
        teardown_function()
        sys.exit(1)
    except Exception as err:
        print(f"\n[ERROR] Phase 2 Execution Error: {err}")
        teardown_function()
        sys.exit(1)