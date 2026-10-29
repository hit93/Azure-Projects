"""
Unit & Integration Verification for Phase 1 Setup.
Tests folder scaffolding, KB-01 through KB-12 extraction, CSV schemas, and configuration loading.
"""

import sys
from pathlib import Path
import pandas as pd

# Add Project2-AI-Agents to sys.path
PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from src.config import (
    DATA_DIR,
    KB_DIR,
    AUDIT_LOG_DIR,
    EVALUATION_DATE,
    validate_config,
)


def test_directories():
    print("[1/4] Testing Directory Scaffolding...")
    expected_dirs = [
        PROJECT_DIR / "src",
        PROJECT_DIR / "src" / "tools",
        PROJECT_DIR / "src" / "agents",
        PROJECT_DIR / "src" / "guardrails",
        PROJECT_DIR / "kb",
        PROJECT_DIR / "tests",
        PROJECT_DIR / "audit_logs",
    ]
    for d in expected_dirs:
        assert d.is_dir(), f"Directory missing: {d}"
    print("  [OK] All required project directories are present.")


def test_knowledge_base_files():
    print("[2/4] Testing Knowledge Base Extraction...")
    expected_kb_ids = [f"KB-{i:02d}.md" for i in range(1, 13)]
    for kb_id in expected_kb_ids:
        kb_file = KB_DIR / kb_id
        assert kb_file.is_file(), f"KB document missing: {kb_id}"
        content = kb_file.read_text(encoding="utf-8")
        assert len(content.strip()) > 50, f"KB document {kb_id} is empty or too short."
        assert content.startswith(f"# KB-{kb_id[3:5]}"), f"KB title formatted incorrectly in {kb_id}"
    print("  [OK] All 12 policy files (KB-01.md to KB-12.md) are present and valid.")


def test_csv_data_schemas():
    print("[3/4] Testing Mock Data CSV Schemas...")
    schema_expectations = {
        "customers.csv": ["customer_id", "name", "email", "language", "fraud_flag", "created_at"],
        "orders.csv": [
            "order_id",
            "customer_id",
            "order_date",
            "status",
            "est_delivery",
            "delivered_date",
            "last_scan_date",
            "item",
            "subtotal_eur",
            "shipping_fee_eur",
            "final_sale",
            "in_stock_for_replacement",
        ],
        "payments.csv": ["payment_id", "order_id", "amount_eur", "status", "captured_at"],
        "refund_history.csv": ["refund_id", "customer_id", "order_id", "date", "amount_eur", "status"],
    }

    for filename, expected_cols in schema_expectations.items():
        file_path = DATA_DIR / filename
        assert file_path.is_file(), f"CSV file missing: {filename}"
        df = pd.read_csv(file_path)
        actual_cols = list(df.columns)
        assert actual_cols == expected_cols, f"Schema mismatch in {filename}.\nExpected: {expected_cols}\nActual: {actual_cols}"
        assert len(df) > 0, f"CSV file is empty: {filename}"
    print("  [OK] All 4 CSV database tables match TRD Section 4.1 specifications.")


def test_configuration_loading():
    print("[4/4] Testing Configuration & Evaluation Clock...")
    config_status = validate_config(require_api_keys=False)
    assert config_status["evaluation_date"] == "2026-10-20", f"Invalid evaluation clock: {EVALUATION_DATE}"
    assert config_status["kb_files_count"] == 12, f"Expected 12 KB files, got {config_status['kb_files_count']}"
    print("  [OK] Configuration successfully loaded.")
    print("  [OK] Evaluation Clock is locked to Tuesday, Oct 20, 2026 (2026-10-20).")
    print(f"  [OK] Azure OpenAI Configured: {config_status['azure_openai_endpoint']}")
    print(f"  [OK] Cohere Key Configured: {config_status['cohere_key']}")
    print(f"  [OK] LangSmith Tracing Configured: {config_status['langsmith_tracing']}")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("PHASE 1 VERIFICATION RUN")
    print("=" * 60)
    try:
        test_directories()
        test_knowledge_base_files()
        test_csv_data_schemas()
        test_configuration_loading()
        print("\n" + "=" * 60)
        print("ALL PHASE 1 VERIFICATION CHECKS PASSED SUCCESSFULLY!")
        print("=" * 60 + "\n")
    except AssertionError as err:
        print(f"\n[FAIL] Phase 1 Verification Failed: {err}")
        sys.exit(1)
