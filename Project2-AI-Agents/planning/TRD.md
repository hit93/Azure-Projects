# Project 2: Resolve — Governed Multi-Agent Customer Support Desk
# Technical Requirements Document (TRD)

---

## 1. System Architecture & High-Level Design

Resolve uses a decoupled, multi-agent architecture built on the Microsoft Azure AI ecosystem. Each component has an explicit security boundary, distinct system prompt, and deterministic validation gate.

```
+----------------------------------------------------------------------------------------------------+
|                                    AZURE AI AGENT SUITE ARCHITECTURE                               |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|  [ Customer Channels ]  --->  [ Input Guardrails: Azure AI Content Safety & Prompt Shields ]        |
|                                                     |                                              |
|                                                     v                                              |
|                                     +-------------------------------+                              |
|                                     |    Triage Agent (GPT-4o)      |                              |
|                                     | Order Extraction & Routing    |                              |
|                                     +---------------+---------------+                              |
|                                                     |                                              |
|                          +--------------------------+--------------------------+                   |
|                          |                                                     |                   |
|                          v                                                     v                   |
|          +-------------------------------+                     +-------------------------------+   |
|          |    Knowledge Agent (RAG)      |                     |      Action Agent (MCP)       |   |
|          | Cohere RAG / Rerank (KB)      |                     | Order Lookup & Calculations   |   |
|          +---------------+---------------+                     +---------------+---------------+   |
|                          |                                                     |                   |
|                          +--------------------------+--------------------------+                   |
|                                                     |                                              |
|                                                     v                                              |
|                                     +-------------------------------+                              |
|                                     | Approval & Reply Agent (LLM)  |                              |
|                                     | Policy Gate & Response Synth  |                              |
|                                     +---------------+---------------+                              |
|                                                     |                                              |
|                                                     v                                              |
|  [ Final Output ]       <---  [ Output Guardrails & Content Safety ]                                |
|          +                                          +                                              |
|          v                                          v                                              |
|  Customer Reply Email                       Append-Only Audit Log (Azure Blob Immutable Storage)   |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

---

## 2. Azure Technology Stack & Component Mapping

| Architectural Layer | Azure Service / Technology | Purpose & Implementation Details |
| :--- | :--- | :--- |
| **Reasoning Engine** | Azure OpenAI Service (`gpt-4o`, `gpt-4o-mini`) | Structured extraction, JSON validation, intent classification, policy reasoning. |
| **Agent Orchestration** | Azure AI Foundry Agent Service / Python SDK | Multi-agent coordination, thread persistence, turn execution, and telemetry tracing. |
| **Input/Output Guardrails**| Azure AI Content Safety (Prompt Shields) | Detects direct user jailbreak attempts and indirect injection inside emails and attachments. |
| **Knowledge Retrieval (RAG)**| Cohere Embed / Rerank (`rerank-v3.5`) | Semantic retrieval and reranking over local markdown policy chunks `KB-01`–`KB-12` (no Azure AI Search required). |
| **Tool Execution** | Model Context Protocol (MCP) Server / Python tools | Secure, typed tool server reading CSV mock data (`orders.csv`, `customers.csv`, `payments.csv`). |
| **Identity & Access** | Microsoft Entra ID (Managed Identities) | Keyless, role-based access control (RBAC) granting least privilege to each agent. |
| **Audit Storage** | Azure Blob Storage (Immutable WORM Policy) | Append-only audit storage ensuring tamper-resistant decision and trace records. |
| **Observability & Debugging** | LangSmith & Azure Application Insights | Live visual traces for debugging agent turns, prompt diffs, token usage, and failure diagnosis (free 5,000 runs/mo). |
| **Adversarial Testing** | PyRIT (Python Risk Identification Tool) | Automated red-teaming orchestrator executing 34 attack scenarios before releases. |

---

## 3. Multi-Agent Role Specifications

### 3.1 Triage Agent
- **Purpose:** Ingests raw ticket text, sanitizes input, extracts core entities, and determines urgency and routing.
- **Model:** `gpt-4o-mini` (optimized for fast, low-cost structured JSON extraction).
- **Inputs:** `ticket_text: str`, `sender_email: str`, `received_timestamp: str`.
- **Outputs (Structured JSON):**
  ```json
  {
    "order_id": "O-1001",
    "primary_category": "product",
    "secondary_category": null,
    "urgency": "medium",
    "language": "en",
    "confidence": 0.94,
    "intents_detected": ["refund_request"]
  }
  ```
- **Key Deterministic Logic:**
  - *TR3 (Order ID Resolution):* If `order_id` is missing, the Triage Agent only reports `order_id: null` (it has no tool access, see 6.1). The orchestrator then calls `get_customer` and `get_customer_orders` through the Action Agent's read-only identity. If the customer has exactly 1 order in the last 60 days, bind that order and explicitly state the assumption in the reply. If 0 or $>1$ orders, emit `REQUEST_INFO`.
  - *TR5 (Low Confidence):* If triage confidence $< 0.70$ or intent is ambiguous, emit `REQUEST_INFO`.

### 3.2 Knowledge Agent (RAG)
- **Purpose:** Answers policy, care, warranty, and store procedure inquiries using strictly grounded retrieval.
- **Data Source:** Local markdown repository `kb/KB-01.md` through `kb/KB-12.md`.
- **Search & Ranking Strategy:** Semantic chunk retrieval + Cohere Rerank API (`rerank-v3.5`). Policy chunks are compared against the customer query and reranked using Cohere's relevance scores.
- **Strict Grounding Rule (GR6 & ES7):**
  - Minimum relevance score threshold (e.g., `relevance_score >= 0.70`).
  - Deliberately missing topics (gift cards, loyalty programs, price matching) produce low relevance scores and trigger `REFUSE_NO_POLICY`. The agent outputs an explicit refusal token and creates a human follow-up task instead of guessing.

### 3.3 Action Agent (MCP Tool Executor)
- **Purpose:** Executes queries and state changes against customer and order databases through typed MCP tools.
- **Security Constraint:** Read-only access to customer/order records until an authorization token is signed by the Approval Gate.
- **Tool Catalog (Section 4):**
  - `get_customer(email)`
  - `get_order(order_id)`
  - `get_customer_orders(customer_id, days_limit)`
  - `get_refund_history(customer_id, days_limit)`
  - `get_payments(order_id)`
  - `calculate_refund_amount(order_id, item_id, reason)`
  - `execute_refund(order_id, amount, reason, auth_token, idempotency_key)`
  - `execute_replacement(order_id, item_id, auth_token)`
  - `cancel_order(order_id, auth_token)`
  - `update_shipping_address(order_id, new_address, auth_token)`

### 3.4 Approval and Reply Agent
- **Purpose:** Synthesizes outputs from Triage, Knowledge, and Action agents; obtains the decision from the deterministic Policy Engine; drafts the customer reply; and writes the audit log.
- **Policy Engine (deterministic code, not an LLM):** All thresholds, windows, tiers and arithmetic (RF1–RF9, RP1–RP4, DL1–DL6, CN1–CN2, BL1–BL3, ES1–ES8) are implemented as code that reads a versioned policy file. It returns the decision code, the rule IDs and the authorization token. The LLM never decides an amount, a tier or an approval, because exact boundaries such as €50.00 versus €50.01 must not depend on model output. `policy_version` in the audit record is this file's version.
- **Model:** `gpt-4o` drafts the reply and resolves ambiguous wording. It may escalate beyond the engine's decision but can never auto-approve what the engine escalated or denied.
- **Core Verification Checklist (implemented in the Policy Engine):**
  1. *Guardrails:* Verify GR1 (anti-injection) and GR2 (the order's `customer_id` equals the sender's `customer_id`).
  2. *Refund Tiers (RF3):* computed on the refund amount **summed per customer over a rolling 24 hours**: $\le$ €50 $\to$ `AUTO_APPROVE`; €50.01–€300 $\to$ `HUMAN_REVIEW_MANAGER`; $>$ €300 $\to$ `HUMAN_REVIEW_SENIOR`. The 24-hour sum is what stops split-refund attacks (RT-17, RT-24).
  3. *Velocity Limits (RF4):* Check 90-day refund count; if $\ge 3 \to$ `HUMAN_REVIEW_MANAGER`.
  4. *Fraud Check (RF5):* If `fraud_flag == true` $\to$ `HUMAN_REVIEW_MANAGER` (never mention fraud to the customer).
  5. *Cap and duplicates (RF6):* Refund cannot exceed item subtotal minus prior refunds, and an order can have only one open refund; a repeat request is `MERGE_DUPLICATE`.
  6. *Reply Hygiene (OP1–OP5):* Mask card numbers/PII, match customer language, exclude internal jargon.

---

## 4. MCP Tool Definitions & Mock Database Schemas

### 4.1 Mock Data Schemas (CSV Files)

```
customers.csv:
customer_id, name, email, language, fraud_flag, created_at

orders.csv:
order_id, customer_id, order_date, status, est_delivery, delivered_date, last_scan_date, item, subtotal_eur, shipping_fee_eur, final_sale, in_stock_for_replacement

payments.csv:
payment_id, order_id, amount_eur, status, captured_at

refund_history.csv:
refund_id, customer_id, order_id, date, amount_eur, status, reversal_ref_id (optional, empty in the supplied data)
```

The CSV files in `resolve-test-data.md` (Section 3) are authoritative. `est_delivery`, `last_scan_date`, `final_sale` and `in_stock_for_replacement` are required: without them DL2–DL4, RF8 and RP1 cannot be evaluated. `subtotal_eur` is the item price excluding shipping, which is the base for RF2.

### 4.2 Python Tool Interface Contracts

```python
from typing import Dict, Any, List, Optional

def get_customer(email: str) -> Optional[Dict[str, Any]]:
    """Retrieve customer profile by email address."""
    pass

def get_order(order_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve order details, status, timestamps, and line items."""
    pass

def get_customer_orders(customer_id: str, days_limit: int = 60) -> List[Dict[str, Any]]:
    """Fetch orders placed within the last N days (default 60 days)."""
    pass

def get_refund_history(customer_id: str, days_limit: int = 90) -> List[Dict[str, Any]]:
    """Fetch refunds issued to the customer in the last N days (default 90 days for velocity check)."""
    pass

def get_payments(order_id: str) -> List[Dict[str, Any]]:
    """Fetch payment records for an order (needed for BL1 duplicate-payment and BL2 unmatched-charge checks)."""
    pass

def calculate_refund_amount(order_id: str, item_id: str, reason: str) -> Dict[str, Any]:
    """
    Computes exact refund according to Rule RF2:
    - 'changed_mind': item_subtotal - €4.95 label fee (original shipping excluded).
    - 'defective', 'damaged', 'wrong_item': full item_subtotal.
    Returns: {'subtotal': float, 'fee_deducted': float, 'net_refund': float}
    """
    pass

def execute_refund(order_id: str, amount: float, reason: str, auth_token: str, idempotency_key: str) -> Dict[str, Any]:
    """
    Appends an approved refund to refund_history.csv and updates the order record.
    Must reject: amount <= 0 or non-numeric; amount above item subtotal minus prior refunds (RF6);
    an order that already has an open refund; an auth_token whose approval tier is below the
    amount's tier (RF3: one token up to €300, two distinct tokens above €300).
    A repeated idempotency_key returns the first result and never creates a second refund.
    """
    pass

def cancel_order(order_id: str, auth_token: str) -> Dict[str, Any]:
    """Cancels an order if status == 'processing' and issues 100% refund including shipping (CN1)."""
    pass

def update_shipping_address(order_id: str, new_address: str, auth_token: str) -> Dict[str, Any]:
    """Updates delivery address if status == 'processing' (DL6)."""
    pass
```

---

## 5. Audit Log & Case Record Data Schema (OP6)

Every interaction must emit an append-only JSON record matching this schema to Azure Blob Storage:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ResolveCaseRecord",
  "type": "object",
  "required": [
    "ticket_id",
    "evaluation_date",
    "customer_id",
    "sender_email",
    "triage",
    "intents",
    "follow_up_tasks",
    "overall_status",
    "security_flag",
    "kb_docs_cited",
    "tool_calls",
    "governance",
    "timestamps"
  ],
  "properties": {
    "ticket_id": {"type": "string", "pattern": "^TK-\\d{4}$"},
    "evaluation_date": {"type": "string", "format": "date"},
    "customer_id": {"type": ["string", "null"]},
    "sender_email": {"type": "string", "format": "email"},
    "triage": {
      "type": "object",
      "properties": {
        "primary_category": {"enum": ["product", "billing", "delivery", "other"]},
        "secondary_category": {"type": ["string", "null"]},
        "urgency": {"enum": ["low", "medium", "high", "critical"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "language": {"type": "string"}
      }
    },
    "intents": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "intent_id": {"type": "string"},
          "type": {"type": "string"},
          "order_id": {"type": ["string", "null"]},
          "decision": {"type": "string"},
          "action_taken": {"type": ["string", "null"]},
          "authorized_amount": {"type": ["number", "null"]},
          "currency": {"type": "string"},
          "rule_ids_applied": {"type": "array", "items": {"type": "string"}}
        }
      }
    },
    "follow_up_tasks": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "task_id": {"type": "string"},
          "type": {"type": "string"},
          "owner_tier": {"enum": ["support_agent", "support_manager", "senior_reviewer", "safety_team"]},
          "reason": {"type": "string"}
        }
      }
    },
    "overall_status": {"enum": ["resolved", "pending_human", "blocked"]},
    "security_flag": {"type": "boolean"},
    "kb_docs_cited": {"type": "array", "items": {"type": "string"}},
    "tool_calls": {"type": "array"},
    "governance": {
      "type": "object",
      "properties": {
        "policy_version": {"type": "string"},
        "prompt_version": {"type": "string"},
        "model": {"type": "string"},
        "total_tokens": {"type": "integer"},
        "cost_estimate_usd": {"type": "number"},
        "human_review_required": {"type": "boolean"}
      }
    },
    "timestamps": {
      "type": "object",
      "properties": {
        "received_at": {"type": "string", "format": "date-time"},
        "completed_at": {"type": "string", "format": "date-time"}
      }
    }
  }
}
```

---

## 6. Security, Identity & Red Teaming

### 6.1 Least-Privilege Entra ID Roles

Each agent operates under a distinct Managed Identity:
- **Triage Agent Identity:** Read-only access to input queue; no access to MCP tools or storage.
- **Knowledge Agent Identity:** Read-only access to local policy knowledge base files and secured outbound access to Cohere Rerank API via key/secret management. Cannot reach customer database.
- **Action Agent Identity:** Access to MCP Tool Server with read-only database rights; write rights gated by signature verification.
- **Approval & Reply Identity:** Write access to the immutable audit container (append only). No access to customer data tools.

### 6.2 Defensive Guardrails Implementation
- **Prompt Shields API:** Intercepts ticket text before passing to the Triage Agent. Scored on `jailbreak_detected` and `indirect_injection_detected`.
- **Regex PII Scrubber:** Scans input and reply streams for 16-digit credit card patterns, CVVs, and password resets, substituting masked tokens `[CARD_MASKED]`.
- **Ownership Verification Gate:** Programmatic assertion:
  ```python
  sender = get_customer(ticket.sender_email)   # None for visitors without an account
  order = get_order(order_id)
  if order is None:
      return Decision.REQUEST_INFO             # TR4
  if sender is None or order.customer_id != sender.customer_id:
      return Decision.BLOCK_GUARDRAIL          # GR2
  # Use the same neutral wording for both outcomes ("we could not match that order
  # number to your email") so replies never reveal whether an order exists or who owns it.
  ```
  The check compares the **order's owner** with the sender. Comparing the customer record's email with the sender's email would always match, because the customer was looked up by that same email.

### 6.3 Automated Red-Team Validation (PyRIT)
- A dedicated PyRIT adversarial harness executes 34 red-team attacks before deployment:
  - Attack types: Direct system prompt leaks, cross-account order manipulation, refund threshold bypass attempts, simulated emergency threats to bypass returns.
  - **CI/CD Quality Gate:** Any release where Attack Success Rate $> 0\%$ is automatically blocked.

---

## 7. Observability & Debugging with LangSmith

To facilitate troubleshooting when an agent misclassifies an intent or a tool call fails, Resolve integrates **LangSmith** alongside local audit logs:

### 7.1 Setup & Configuration
- **Free Developer Tier:** 5,000 trace executions/month.
- **PII before tracing (GR3):** Traces go to a third-party service. Run the GR3 scrubber before any traced function receives ticket text, and enable LangSmith's input/output redaction as a second layer, so raw card numbers and passwords (and ideally customer emails) never reach it.
- **Environment Flags:**
  ```bash
  LANGCHAIN_TRACING_V2=true
  LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
  LANGCHAIN_API_KEY=<your-langsmith-api-key>
  LANGCHAIN_PROJECT=resolve-multi-agent
  ```

### 7.2 Code Instrumentation Pattern
Each agent turn and tool invocation is decorated with `@traceable`:
```python
from langsmith import traceable

@traceable(name="triage_agent", run_type="chain")
def run_triage(ticket_text: str, sender_email: str) -> dict:
    # Full prompt, model params, latency, and output JSON are captured
    pass

@traceable(name="execute_refund_tool", run_type="tool")
def execute_refund(order_id: str, amount: float, auth_token: str) -> dict:
    # Captures inputs, outputs, exceptions, and execution duration
    pass
```

### 7.3 Diagnostic Value in Case of Failure
- **Visual Call Graph:** Inspect the exact sequence of agent handoffs.
- **Prompt Diffs:** Compare prompts between model revisions.
- **Root Cause Isolation:** Instantly spot why an edge case resulted in `REQUEST_INFO` or why an evaluation rule tripped.

