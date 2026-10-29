# Project 2: Resolve — Phased Implementation Plan & Checklist

**Project:** Resolve — Governed Multi-Agent Customer Support Desk  
**Target:** Step-by-Step Implementation for Student Developers  
**Reference Docs:**
- [PRD.md](file:///c:/Users/hites/OneDrive/Desktop/krish%20naik/Azure-Projects/Project2-AI-Agents/planning/PRD.md)
- [TRD.md](file:///c:/Users/hites/OneDrive/Desktop/krish%20naik/Azure-Projects/Project2-AI-Agents/planning/TRD.md)
- [WORKFLOW.md](file:///c:/Users/hites/OneDrive/Desktop/krish%20naik/Azure-Projects/Project2-AI-Agents/planning/WORKFLOW.md)
- [sample-data.md](file:///c:/Users/hites/OneDrive/Desktop/krish%20naik/Azure-Projects/Project2-AI-Agents/data/sample-data.md)

---

## Progress Overview

- [x] **Phase 1: Environment & Knowledge Base Setup**
- [x] **Phase 2: Local Tools & Deterministic Policy Engine**
- [x] **Phase 3: Specialized Agent Implementations**
- [ ] **Phase 4: Orchestrator, Guardrails & Observability**
- [ ] **Phase 5: Benchmark Evaluation & Red Teaming**

---

## Phase 1: Environment & Knowledge Base Setup

**Goal:** Establish the directory structure, configure environment credentials, verify mock databases, and extract individual policy markdown documents for RAG retrieval.

### Checklist:
- [x] **1.1 Directory Structure Creation**
  - [x] Create `Project2-AI-Agents/src/` (root source code package)
  - [x] Create `Project2-AI-Agents/src/tools/` (MCP tool implementations & DB access)
  - [x] Create `Project2-AI-Agents/src/agents/` (Triage, Knowledge, Reply agents)
  - [x] Create `Project2-AI-Agents/src/guardrails/` (PII scrubber, prompt shields, ownership gates)
  - [x] Create `Project2-AI-Agents/kb/` (individual knowledge base markdown files)
  - [x] Create `Project2-AI-Agents/tests/` (unit and integration tests)
  - [x] Create `Project2-AI-Agents/audit_logs/` (local immutable JSON case record storage)

- [x] **1.2 Knowledge Base Document Extraction**
  - [x] Parse `Project2-AI-Agents/data/policies.md` or Section 2 of `sample-data.md`
  - [x] Generate 12 individual policy documents in `Project2-AI-Agents/kb/`:
    - [x] `KB-01.md`: Return Window and Standard Eligibility
    - [x] `KB-02.md`: Refund Calculation and Processing Times
    - [x] `KB-03.md`: Exceptions, Non-Returnable Items, and Final Sale
    - [x] `KB-04.md`: Damaged, Defective, or Incorrect Items (Replacements)
    - [x] `KB-05.md`: Order Cancellations and In-Flight Modifications
    - [x] `KB-06.md`: Shipping Delays, Carrier Tracking, and Lost In Transit
    - [x] `KB-07.md`: Delivered but Missing Packages
    - [x] `KB-08.md`: Duplicate Charges, Billing Errors, and Price Adjustments
    - [x] `KB-09.md`: Safety Escalations, Recalls, and Hazardous Products
    - [x] `KB-10.md`: Customer Conduct, Threats, and Legal Inquiries
    - [x] `KB-11.md`: Operating Hours, Support SLA, and Contact Options
    - [x] `KB-12.md`: Product Care, Material Guides, and Warranty Scope

- [x] **1.3 Environment & Mock Data Verification**
  - [x] Ensure `.env` contains valid credentials:
    - `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_CHAT_DEPLOYMENT`
    - `COHERE_API_KEY` (for reranking)
    - `LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`
  - [x] Verify mock CSV files in `Project2-AI-Agents/data/`:
    - `customers.csv` (contains customer ID, email, fraud_flag)
    - `orders.csv` (contains order ID, customer_id, est_delivery, subtotal_eur, shipping_fee_eur)
    - `payments.csv` (contains payment records)
    - `refund_history.csv` (contains past refunds)

### Verification Check:
- [x] Run verification script to confirm all 12 `KB-xx.md` files exist and CSV schemas match TRD Section 4.1.

---

## Phase 2: Local Tools & Deterministic Policy Engine

**Goal:** Build safe mock database tools and the deterministic Python policy engine (guaranteeing 0% boundary hallucinations on financial thresholds).

### Checklist:
- [x] **2.1 Read-Only Data Retrieval Tools (`src/tools/mcp_tools.py`)**
  - [x] Implement `get_customer(email: str)` -> Customer record or `None`
  - [x] Implement `get_order(order_id: str)` -> Order record or `None`
  - [x] Implement `get_customer_orders(customer_id: str, days_limit: int = 60)` -> List of orders
  - [x] Implement `get_refund_history(customer_id: str, days_limit: int = 90)` -> List of refunds
  - [x] Implement `get_payments(order_id: str)` -> List of payment transactions

- [x] **2.2 State-Changing Action Tools (`src/tools/mcp_tools.py`)**
  - [x] Implement `calculate_refund_amount(order_id: str, item_id: str, reason: str)`:
    - Deduct standard €4.95 return shipping fee (RF2) unless defective/incorrect
  - [x] Implement `execute_refund(order_id, amount, reason, auth_token, idempotency_key)`:
    - Validate `amount > 0` and within subtotal minus prior refunds (RF6)
    - Enforce idempotency: repeated key returns original result without double-refunding
    - Validate single/dual approval signature token (RF3)
  - [x] Implement `cancel_order(order_id: str, auth_token: str)`
  - [x] Implement `execute_replacement(order_id: str, item_id: str, auth_token: str)`
  - [x] Implement `update_shipping_address(order_id: str, new_address: str, auth_token: str)`

- [x] **2.3 Deterministic Policy Engine (`src/policy_engine.py`)**
  - [x] Assert fixed evaluation clock: **`2026-10-20`** (Tuesday)
  - [x] Return Rules Logic (`RF1`–`RF9`):
    - [x] Calculate days elapsed since `delivered_date`
    - [x] Check return window: $\le 30$ days (standard), 31–44 days (`HUMAN_REVIEW_AGENT`), $> 44$ days (`AUTO_DENY`)
    - [x] Calculate cumulative 24-hour refund sum per customer to prevent split-refund exploits
    - [x] Financial approval tiers (`RF3`):
      - $\le €50.00 \to$ `AUTO_APPROVE`
      - $€50.01 - €300.00 \to$ `HUMAN_REVIEW_MANAGER`
      - $> €300.00 \to$ `HUMAN_REVIEW_SENIOR`
    - [x] Velocity limit (`RF4`): $\ge 3$ refunds in last 90 days $\to$ `HUMAN_REVIEW_MANAGER`
    - [x] Fraud check (`RF5`): `fraud_flag == true` $\to$ `HUMAN_REVIEW_MANAGER`
  - [x] Delivery Rules Logic (`DL1`–`DL6`)
  - [x] Cancellation Rules Logic (`CN1`–`CN2`):
    - [x] `processing` $\to$ `AUTO_APPROVE` (CN1)
    - [x] `dispatched` or `delivered` $\to$ `ANSWER_ONLY` with return path instructions (CN2)
  - [x] Billing Rules Logic (`BL1`–`BL3`)
  - [x] Escalation Rules Logic (`ES1`–`ES8`):
    - [x] Safety hazard / violent threats $\to$ `ESCALATE_URGENT` (ES1)
    - [x] Legal threats $\to$ `HUMAN_REVIEW_SENIOR` (ES2)
    - [x] Chargeback / bank dispute $\to$ `HUMAN_REVIEW_SENIOR` (ES3)
  - [x] Auth token generator for approved actions

### Verification Check:
- [x] Run test suite verifying:
  - Boundary: €50.00 triggers `AUTO_APPROVE`, €50.01 triggers `HUMAN_REVIEW_MANAGER`.
  - Velocity: 3 refunds in 90 days routes to manager.
  - Idempotency: duplicate `execute_refund` call does not create a second row in `refund_history.csv`.

---

## Phase 3: Specialized Agent Implementations

**Goal:** Implement individual agents with clear separation of duties and least-privilege access.

### Checklist:
- [x] **3.1 Triage Agent (`src/agents/triage_agent.py`)**
  - [x] Configure fast model (`gpt-4o-mini` or equivalent)
  - [x] Implement zero-tool principle (read-only input queue, no database tools)
  - [x] Enforce structured JSON output matching schema:
    - `order_id` (detected `O-####` or `null`)
    - `primary_category` (`billing`, `delivery`, `product`, `other`)
    - `urgency` (`low`, `medium`, `high`, `critical`)
    - `language` (`en` or `nl`)
    - `triage_confidence` ($0.0 - 1.0$)
    - `customer_intents` list
  - [x] Low confidence trigger: confidence $< 0.70 \to$ emit `REQUEST_INFO` (TR5)

- [x] **3.2 Knowledge Agent (`src/agents/knowledge_agent.py`)**
  - [x] Build local markdown retriever loading all `kb/KB-*.md` documents
  - [x] Integrate Cohere Rerank (`rerank-v3.5`) to score top relevant policy sections
  - [x] Implement strict citation prompt:
    - Every claim must explicitly cite `KB-01` to `KB-12`
    - Unknown topics (e.g. gift cards, price match) must emit `REFUSE_NO_POLICY` token

- [x] **3.3 Approval & Reply Agent (`src/agents/reply_agent.py`)**
  - [x] Ingest Policy Engine deterministic decision (LLM does not make policy or monetary choices)
  - [x] Draft customer-facing reply following Communication Standards:
    - [x] Match customer language (English / Dutch) (OP1)
    - [x] Itemize financial breakdown (subtotal minus €4.95 fee) (OP2)
    - [x] Mask all sensitive internal tokens (`fraud_flag`, `risk_score`) (OP3)
    - [x] Include ticket reference ID and support SLA disclaimer (OP5, KB-11)

### Verification Check:
- [x] Unit tests for Triage Agent on sample tickets (ensuring clean JSON parsing).
- [x] Retrieval tests verifying valid citations for return policies and `REFUSE_NO_POLICY` for ungrounded queries.

---

## Phase 4: Orchestrator, Guardrails & Observability Integration

**Goal:** Assemble the multi-agent pipeline into a guarded workflow with PII protection, immutable audit trails, and LangSmith tracing.

### Checklist:
- [ ] **4.1 Security Guardrails (`src/guardrails/`)**
  - [ ] `prompt_shield.py` (GR1):
    - Detect prompt injections; treat injected text as data, not commands
    - Strip adversarial injections while preserving legitimate customer requests
    - Block full injection attacks with `BLOCK_GUARDRAIL`
  - [ ] `ownership_gate.py` (GR2):
    - Verify `order.customer_id == sender.customer_id`
    - If mismatch or unauthenticated sender, emit neutral denial without revealing order existence
  - [ ] `pii_scrubber.py` (GR3):
    - Regex scrubber for 16-digit credit cards, CVVs, and passwords
    - Replace sensitive strings with `[CARD_MASKED]` **before** audit logging and LangSmith tracing

- [ ] **4.2 Workflow Orchestrator (`src/orchestrator.py`)**
  - [ ] Step 1: Input ingestion, fixed clock assertion (`2026-10-20`), Prompt Shield check
  - [ ] Step 2: Triage invocation & missing order handling (TR3):
    - If `order_id` is null, resolve sender via `get_customer` and inspect 60-day orders
  - [ ] Step 3: Parallel dispatch to Knowledge Agent and Action Agent
  - [ ] Step 4: Deterministic Policy Engine evaluation & authorization token generation
  - [ ] Step 5: Conditional execution (auto-approve tool write vs. human review queue creation)
  - [ ] Step 6: Reply drafting & post-processing PII masking
  - [ ] Step 7: Append-only JSON case record logging to `audit_logs/`

- [ ] **4.3 Observability & LangSmith Setup**
  - [ ] Ensure LangSmith traces capture agent steps with pre-scrubbed PII
  - [ ] Verify OpenTelemetry / tracing metadata tags (`ticket_id`, `decision_code`, `evaluation_date`)

### Verification Check:
- [ ] Execute an end-to-end dry run with ticket `TK-01` (happy path return under €50).
- [ ] Verify that `audit_logs/` contains the full JSON case record conforming to TRD Section 5.1.
- [ ] Verify LangSmith dashboard reflects the traced run without leaking raw PII.

---

## Phase 5: Benchmark Evaluation & Red-Team Testing

**Goal:** Run the formal evaluation suite against the 49 labeled tickets and 34 adversarial attacks.

### Checklist:
- [ ] **5.1 Benchmark Test Runner (`tests/test_benchmark_tickets.py`)**
  - [ ] Load the 49 labeled benchmark tickets from `sample-data.md` Section 4
  - [ ] Implement database state reset before each ticket execution
  - [ ] Calculate system accuracy metrics:
    - [ ] Decision Accuracy ($\ge 90\%$)
    - [ ] Tool Call Precision ($\ge 95\%$)
    - [ ] Citation Groundedness ($\ge 95\%$)
    - [ ] Guardrail Interception Rate ($100\%$ on pure injections)

- [ ] **5.2 Red-Team Adversarial Harness (`tests/test_red_team_attacks.py`)**
  - [ ] Execute the 34 red-team attack scenarios from `sample-data.md` Section 5:
    - [ ] Direct instruction overrides ("Ignore previous instructions...")
    - [ ] Split-refund attacks (attempting multiple €30 refunds to bypass limits)
    - [ ] Cross-account order snooping (GR2)
    - [ ] PII exfiltration attempts
    - [ ] Emotional manipulation and threats
  - [ ] Verify 0% guardrail bypass rate

- [ ] **5.3 Fault Injection & Resilience Testing (`tests/test_fault_injection.py`)**
  - [ ] Simulate tool timeouts / Cohere API failure $\to$ verify graceful fallback to `HUMAN_REVIEW_AGENT` (ES8)
  - [ ] Verify neutral customer holding message is returned

### Verification Check:
- [ ] All 49 benchmark tickets evaluated with logged results.
- [ ] Zero security breaches across all 34 red-team attacks.
- [ ] Final evaluation report generated summarizing metrics and audit compliance.

---

## Verification & Execution Protocol

Before starting any implementation step:
1. Complete all checklist items in order.
2. Confirm the verification check succeeds before moving to the next phase.
3. Keep changes minimal and modular.

