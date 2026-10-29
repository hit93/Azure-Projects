"""
Unit tests for Phase 3 Specialized Agents:
- TriageAgent: Entity extraction, category routing, language detection, TR5 confidence threshold.
- KnowledgeAgent: Grounded policy retrieval, citations, REFUSE_NO_POLICY on ungrounded queries.
- ReplyAgent: Language matching (OP1), financial itemization (OP2), internal token masking (OP3), SLA disclaimer (OP5).
"""

import sys
import unittest
from pathlib import Path

# Setup path so src is importable
PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from src.agents.triage_agent import triage_ticket
from src.agents.knowledge_agent import query_knowledge_base, load_all_kb_documents
from src.agents.reply_agent import draft_customer_reply, _mask_internal_tokens
from src.tools.mcp_tools import get_order
from src.policy_engine import evaluate_return_and_refund


class TestTriageAgent(unittest.TestCase):
    def test_extract_order_id_and_product_category(self):
        ticket = "Hello, I want to return my boots from order O-1001. They are too small."
        res = triage_ticket(ticket)
        self.assertEqual(res["order_id"], "O-1001")
        self.assertEqual(res["primary_category"], "product")
        self.assertIn("return_request", res["intents_detected"])
        self.assertEqual(res["language"], "en")

    def test_detect_dutch_language(self):
        ticket = "Hallo, ik wil graag mijn bestelling O-0870 retourneren. Het pakket is beschadigd."
        res = triage_ticket(ticket)
        self.assertEqual(res["order_id"], "O-0870")
        self.assertEqual(res["language"], "nl")
        self.assertEqual(res["primary_category"], "product")

    def test_critical_urgency_for_hazard(self):
        ticket = "URGENT: The electric heater I bought in order O-0500 started sparking and caught fire! This is a safety hazard."
        res = triage_ticket(ticket)
        self.assertEqual(res["urgency"], "critical")
        self.assertEqual(res["order_id"], "O-0500")

    def test_missing_order_id_and_low_confidence(self):
        ticket = "Hey there, just wondering what's up."
        res = triage_ticket(ticket)
        self.assertIsNone(res["order_id"])
        self.assertEqual(res["decision"], "REQUEST_INFO")


class TestKnowledgeAgent(unittest.TestCase):
    def test_load_all_kb_documents(self):
        docs = load_all_kb_documents()
        self.assertGreaterEqual(len(docs), 12, "Should load at least 12 KB policy documents.")
        doc_ids = {d["id"] for d in docs}
        self.assertIn("KB-01", doc_ids)
        self.assertIn("KB-11", doc_ids)

    def test_grounded_return_policy_query(self):
        query = "How many days do I have to return an item?"
        res = query_knowledge_base(query)
        self.assertEqual(res["status"], "GROUNDED")
        self.assertIn("KB-01", res["citations"])
        self.assertIn("30", res["answer"])

    def test_refuse_unsupported_gift_cards(self):
        query = "Can I purchase a digital gift card or voucher for my friend?"
        res = query_knowledge_base(query)
        self.assertEqual(res["status"], "REFUSE_NO_POLICY")
        self.assertEqual(len(res["citations"]), 0)

    def test_refuse_unsupported_price_match(self):
        query = "Do you offer a price match guarantee if I found it cheaper on another site?"
        res = query_knowledge_base(query)
        self.assertEqual(res["status"], "REFUSE_NO_POLICY")


class TestReplyAgent(unittest.TestCase):
    def test_reply_english_with_financial_itemization(self):
        policy_decision = {
            "decision": "AUTO_APPROVE",
            "net_refund": 45.05,
            "fee_deducted": 4.95,
            "explanation": "Return requested within 30 days. Standard €4.95 return shipping fee deducted.",
            "kb_citations": ["KB-01", "KB-02"],
        }
        res = draft_customer_reply(
            ticket_id="T-9001",
            customer_name="Alice Smith",
            customer_language="en",
            policy_decision=policy_decision,
            order_id="O-1001",
        )
        self.assertEqual(res["language"], "en")
        self.assertIn("[Ticket #T-9001]", res["body"])
        self.assertIn("€45.05", res["body"])
        self.assertIn("€4.95", res["body"])
        self.assertIn("Mon-Fri 09:00-17:00 CET", res["body"])

    def test_reply_dutch_language_match(self):
        policy_decision = {
            "decision": "AUTO_APPROVE",
            "net_refund": 60.00,
            "fee_deducted": 0.00,
            "explanation": "Defectief artikel geretourneerd. Volledige terugbetaling goedgekeurd.",
            "kb_citations": ["KB-01", "KB-04"],
        }
        res = draft_customer_reply(
            ticket_id="T-9002",
            customer_name="Jan Jansen",
            customer_language="nl",
            policy_decision=policy_decision,
            order_id="O-0870",
        )
        self.assertEqual(res["language"], "nl")
        self.assertIn("Beste Jan Jansen", res["body"])
        self.assertIn("[Ticket #T-9002]", res["body"])
        self.assertIn("Klantenservice", res["body"])

    def test_masking_internal_tokens(self):
        sensitive_text = "System check: fraud_flag is true, risk_score is 85, rule RF3 applies, token auth_token_xyz"
        clean = _mask_internal_tokens(sensitive_text)
        self.assertNotIn("fraud_flag", clean)
        self.assertNotIn("risk_score", clean)
        self.assertNotIn("RF3", clean)
        self.assertNotIn("auth_token", clean)


class TestEndToEndPipelineSinglePhrase(unittest.TestCase):
    """
    End-to-End integration test running all agents on a single customer phrase:
    Customer Message -> Triage Agent -> Policy & Knowledge Check -> Reply Agent
    """

    def test_single_phrase_all_agents_pipeline(self):
        # 1. Single customer phrase
        single_phrase = "I bought boots in order O-1001, but they are too small. Can I exchange them?"

        # --- STEP 1: TRIAGE AGENT ---
        triage = triage_ticket(single_phrase)
        self.assertEqual(triage["order_id"], "O-1001")
        self.assertEqual(triage["primary_category"], "product")
        self.assertEqual(triage["language"], "en")
        self.assertIn("exchange_inquiry", triage["intents_detected"])
        self.assertEqual(triage["decision"], "PROCEED")

        # --- STEP 2: POLICY & KNOWLEDGE ENGINE ---
        order = get_order(triage["order_id"])
        self.assertIsNotNone(order, "Order O-1001 should exist in database.")

        mock_customer = {"customer_id": order["customer_id"], "fraud_flag": False}
        policy_decision = evaluate_return_and_refund(
            order=order, customer=mock_customer, reason="changed_mind"
        )
        policy_decision["intent"] = "exchange_inquiry"

        self.assertEqual(policy_decision["decision"], "AUTO_APPROVE")
        self.assertEqual(policy_decision["fee_deducted"], 4.95)
        self.assertEqual(policy_decision["net_refund"], 34.95)

        # --- STEP 3: REPLY AGENT ---
        reply = draft_customer_reply(
            ticket_id="T-E2E-01",
            customer_name="Alice Smith",
            customer_language=triage["language"],
            policy_decision=policy_decision,
            order_id=triage["order_id"],
        )

        # Assert all formatting and business rules
        self.assertEqual(reply["language"], "en")
        self.assertIn("[Ticket #T-E2E-01]", reply["body"])
        self.assertIn("€34.95", reply["body"])
        self.assertIn("€4.95", reply["body"])
        self.assertIn("do not offer direct size exchanges", reply["body"])
        self.assertIn("Mon-Fri 09:00-17:00 CET", reply["body"])


if __name__ == "__main__":
    unittest.main()

