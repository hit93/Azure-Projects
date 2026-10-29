"""
Interactive Agent Playground for Phase 3 Specialized Agents.
Type any custom customer message to test the full pipeline:
1. Triage Agent (Parses order ID, category, urgency, language)
2. Knowledge / Policy Evaluation (Checks rules or searches KB)
3. Reply Agent (Generates final customer email with fee breakdown & SLA)
"""

import sys
import json
from src.agents.triage_agent import triage_ticket
from src.agents.knowledge_agent import query_knowledge_base
from src.agents.reply_agent import draft_customer_reply
from src.tools.mcp_tools import get_order
from src.policy_engine import evaluate_return_and_refund


def run_pipeline(user_prompt: str, customer_name: str = "Valued Customer") -> None:
    """Runs a custom customer prompt through Triage, Knowledge/Policy, and Reply agents."""
    print("\n" + "=" * 65)
    print(f"INPUT TICKET:\n\"{user_prompt}\"")
    print("=" * 65)

    # 1. TRIAGE AGENT
    print("\n[STEP 1] Triage Agent Analyzing...")
    triage = triage_ticket(user_prompt)
    print(json.dumps(triage, indent=2))

    order_id = triage.get("order_id")
    language = triage.get("language", "en")
    category = triage.get("primary_category", "other")
    intents = triage.get("intents_detected", [])

    # 2. KNOWLEDGE / POLICY EVALUATION
    knowledge_context = None
    policy_decision = {
        "decision": "ANSWER_ONLY",
        "net_refund": 0.0,
        "fee_deducted": 0.0,
        "explanation": "General inquiry received.",
        "kb_citations": [],
    }

    if order_id:
        print(f"\n[STEP 2] Order {order_id} Detected -> Checking Order & Policy Engine...")
        order = get_order(order_id)
        if order:
            mock_customer = {"customer_id": order["customer_id"], "fraud_flag": False}
            reason = "damaged" if "damaged_item" in intents else "changed_mind"
            policy_decision = evaluate_return_and_refund(order=order, customer=mock_customer, reason=reason)
            policy_decision["intents"] = intents
            if "exchange_inquiry" in intents:
                policy_decision["intent"] = "exchange_inquiry"
            print(f"Policy Engine Decision: {policy_decision.get('decision')}")
            print(f"Explanation: {policy_decision.get('explanation')}")
            if policy_decision.get("net_refund", 0) > 0:
                print(f"Eligible Net Refund: €{policy_decision.get('net_refund'):.2f}")
        else:
            print(f"Note: Order ID {order_id} was not found in mock orders.csv.")
            policy_decision["explanation"] = f"Order {order_id} was not found in our records."
            policy_decision["decision"] = "REQUEST_INFO"
    else:
        print("\n[STEP 2] No Order ID -> Querying Knowledge Base...")
        kb_result = query_knowledge_base(user_prompt)
        print(f"KB Status: {kb_result.get('status')}")
        if kb_result.get("citations"):
            print(f"KB Citations: {', '.join(kb_result.get('citations'))}")
        policy_decision["explanation"] = kb_result.get("answer", "")
        policy_decision["decision"] = "ANSWER_ONLY"
        knowledge_context = kb_result.get("answer")

    # 3. REPLY AGENT
    print("\n[STEP 3] Reply Agent Drafting Customer Response...")
    reply = draft_customer_reply(
        ticket_id="T-CUSTOM",
        customer_name=customer_name,
        customer_language=language,
        policy_decision=policy_decision,
        order_id=order_id,
        knowledge_context=knowledge_context,
    )

    print("\n" + "-" * 65)
    print(f"Subject: {reply['subject']}")
    print("-" * 65)
    print(reply["body"])
    print("=" * 65 + "\n")


def main():
    # If the user passed a prompt as a command-line argument:
    # python demo_agents.py "My jacket from O-1001 was broken"
    if len(sys.argv) > 1:
        custom_input = " ".join(sys.argv[1:])
        run_pipeline(custom_input)
        return

    # Otherwise, run in interactive mode
    print("=" * 65)
    print("🤖 NorthPeak Multi-Agent Custom Prompt Tester")
    print("Type your custom customer ticket and press Enter.")
    print("Type 'exit' or 'quit' to stop.")
    print("=" * 65)

    while True:
        try:
            user_input = input("\nEnter ticket prompt > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting. Goodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            print("Goodbye!")
            break

        run_pipeline(user_input)


if __name__ == "__main__":
    main()
