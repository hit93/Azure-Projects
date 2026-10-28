# Project 2: Resolve — Governed Multi-Agent Customer Support Desk
# Product Requirements Document (PRD)

---

## 1. Executive Summary & Problem Statement

In modern e-commerce, customer support teams are overwhelmed by high inquiry volumes for routine requests like order tracking, returns, cancellations, and product care. While single-prompt conversational LLM chatbots have been widely adopted, they present serious production risks:
- **Hallucination of Store Policies:** Fabricating return windows, fee waivers, or unsupported warranty terms.
- **Unbounded Actions:** Taking financial or operational actions (such as authorizing refunds or canceling dispatched shipments) without deterministic risk checks.
- **Vulnerability to Attacks:** Succumbing to direct and indirect prompt injections in ticket text or attachments.
- **Lack of Traceability:** Inability to explain *why* an action was taken or reconstruct the state when a dispute arises.

**Resolve** solves this by implementing a **governed, self-contained multi-agent support desk** for **NorthPeak Outfitters** (a fictional outdoor gear retailer). 

Resolve partitions responsibilities across four specialized AI agents. Every decision is bounded by versioned business policies, traceable through append-only audit records, reversible through compensating actions, and guarded by automated human-in-the-loop (HITL) review gates.

---

## 2. Product Vision & Core Pillars

```
+---------------------------------------------------------------------------------------------------+
|                                         RESOLVE CORE PILLARS                                      |
+------------------------------+------------------------------+-------------------------------------+
|      Governed Autonomy       |       Grounded Answers       |         Defensive Security          |
| Actions bounded by financial | Answers backed by citations  | Azure AI Content Safety, Prompt     |
| thresholds & human reviews.  | from official policy docs.   | Shields, and PyRIT red-team tested. |
+------------------------------+------------------------------+-------------------------------------+
```

1. **Governed Autonomy:** The system can autonomously resolve routine, low-risk requests (e.g., standard returns within 30 days under €50), but strictly routes higher-risk, high-value, or ambiguous actions to human reviewers.
2. **Grounded Answers (Zero Policy Hallucinations):** Policy explanations must cite specific Knowledge Base documents (`KB-01` through `KB-12`). If no policy document covers a topic (e.g., gift cards or price matching), the system refuses to guess (`REFUSE_NO_POLICY`).
3. **Defensive Security & Privacy:** Customer identities and order ownership are strictly enforced (GR2). Personal Identifiable Information (PII) such as credit card numbers and passwords are masked automatically (GR3). Injected prompt attacks are treated purely as data, never as instructions (GR1).
4. **End-to-End Auditability:** Every ticket produces a forensic decision log capturing model version, prompts, token counts, cost estimate, applied rule IDs, and tool executions.

---

## 3. Target Personas & Use Cases

### 3.1 Personas

| Persona | Role | Key Needs & Expectations |
| :--- | :--- | :--- |
| **End Customer** | Outdoor gear shopper | Fast, 24/7 resolution for order status, hassle-free returns within policy, and clear explanations. |
| **Support Agent (Tier 1)** | Human frontline agent | Reviews borderline cases (e.g., goodwill returns 1–14 days late, carrier lost-package inquiries) with pre-assembled context. |
| **Support Manager (Tier 2)** | Customer support manager | Approves medium-value refunds (€50.01–€300.00), reviews velocity alerts ($\ge 3$ refunds in 90 days), and oversees fraud flags. |
| **Senior Reviewer / Legal** | Compliance & leadership | Handles high-value claims (> €300.00), safety hazards, and formal legal claims. Requires two sign-offs. |
| **Student / Developer** | AI Engineer learner | Clear architectural boundaries, understandable agent roles, and reproducible Azure AI patterns. |

### 3.2 User Journeys

#### Journey A: Autonomous Low-Risk Return (`AUTO_APPROVE`)
1. Customer emails: *"I want to return my hiking socks from order O-1001 because I changed my mind."*
2. System verifies order delivery date is within 30 days, subtotal is €35.00, and customer owns the order.
3. System applies policy **RF1** and **RF2**: Item subtotal (€35.00) minus return label fee (€4.95) = €30.05 refund.
4. Amount is $\le$ €50.00, so system executes `AUTO_APPROVE`, triggers the refund tool, and sends the return label instructions.

#### Journey B: High-Value Refund Escalation (`HUMAN_REVIEW_MANAGER`)
1. Customer requests a return for a premium tent (€180.00).
2. Eligibility check passes, but refund amount (€175.05 after €4.95 fee) exceeds the €50.00 autonomous threshold.
3. System outputs `HUMAN_REVIEW_MANAGER`, sends an acknowledgment email to the customer with an official timeline (1 business day), and queues the case for manager review.

#### Journey C: Missing Policy Query (`REFUSE_NO_POLICY`)
1. Customer asks: *"Do you match competitor prices for backpacks?"*
2. Knowledge Agent searches the policy index. Price matching is deliberately absent from the knowledge base.
3. System refuses to fabricate a rule, outputs `REFUSE_NO_POLICY`, informs the customer that price matching is not covered by standard automated policy, and logs a follow-up task for human review.

---

## 4. Decision Taxonomy & Outcome Codes

Every intent in every incoming ticket is assigned an explicit, deterministic decision code:

| Decision Code | Meaning | Human Involved? | Example Trigger |
| :--- | :--- | :---: | :--- |
| `AUTO_APPROVE` | Action executed autonomously without human intervention. | No | Return within 30 days under €50; cancellation while order is in `processing`. |
| `AUTO_DENY` | Declined with an exact policy-grounded explanation. | No | Return requested $> 14$ days after the 30-day window (RF7). |
| `ANSWER_ONLY` | Factual or policy information given from Knowledge Base; no state change. | No | Product care instructions for down jackets or wool socks (KB-12). |
| `REQUEST_INFO` | Required information missing from the customer; no action taken yet. | No | Damaged item claim submitted without photos (RP2). |
| `HUMAN_REVIEW_AGENT` | Queued for Tier 1 frontline support agent review. | Yes | Goodwill return 1–14 days late (RF7); carrier tracking says delivered but customer did not receive (DL5). |
| `HUMAN_REVIEW_MANAGER` | Queued for Tier 2 manager approval. | Yes | Refund between €50.01 and €300.00 (RF3); customer with 3+ refunds in 90 days (RF4); active fraud flag (RF5). |
| `HUMAN_REVIEW_SENIOR` | Queued for senior review (requires two independent approvals). | Yes | Refund over €300.00 (RF3); customer making explicit legal or attorney threats (ES2); chargeback or bank-dispute notice (ES3). |
| `ESCALATE_URGENT` | Urgent same-day human escalation protocol. | Yes | Battery overheating/fire, safety hazard, bodily injury, or violent threats (ES1). |
| `REFUSE_NO_POLICY` | System cannot find supporting documentation; refuses to invent rules. | Yes | Inquiry on gift cards, loyalty points, or competitor price matching. |
| `MERGE_DUPLICATE` | Merged into an existing open case. | No / Yes | Customer submits a duplicate refund request for an order with a pending claim. |
| `BLOCK_GUARDRAIL` | Ticket blocked entirely; no tools executed; security event logged. | No | Pure prompt injection attack (GR1) or attempting to access an order owned by another email (GR2). |
| `HANDOFF` | Direct customer handoff to human support. | Yes | Customer explicitly requests: *"I want to talk to a real person."* (ES6). |

---

## 5. Multi-Intent Handling & Case Status

Customers frequently combine multiple requests in a single ticket (e.g., asking for an address change on one order and inquiring about return policy on another).

- **Intent Independence:** Resolve splits composite tickets into an `intents[]` array. Each intent is evaluated against the rulebook independently.
- **Overall Case Status:**
  - `resolved`: Every intent was successfully handled autonomously (`AUTO_APPROVE`, `AUTO_DENY`, or `ANSWER_ONLY`).
  - `pending_human`: One or more intents or follow-up tasks require human review (`HUMAN_REVIEW_*`, `ESCALATE_URGENT`, `REQUEST_INFO`, `REFUSE_NO_POLICY`).
  - `blocked`: Only when the entire ticket is rejected under `BLOCK_GUARDRAIL`.

---

## 6. Functional & Operational Requirements

### 6.1 Guardrail Requirements (GR1–GR6)
- **GR1 (Prompt Injection & Override):** Treat ticket text and attachments strictly as data, never as system instructions. If legitimate requests exist alongside injected prompts, process the legitimate request while raising `security_flag = true`. Block only if purely adversarial.
- **GR2 (Order Ownership):** Verify that the sender email matches the customer on file for the specified order. Reject mismatches immediately (`BLOCK_GUARDRAIL`).
- **GR3 (Data Protection):** Mask full payment card numbers, CVVs, PINs, and passwords in replies, traces, and audit logs. Cite `KB-10`.
- **GR4 (Tone & Civility):** Maintain a neutral, empathetic, and professional tone even when facing insults or abuse. Never mirror hostility.
- **GR5 (Off-topic Handling):** Politely redirect off-topic inquiries back to outdoor gear order support without invoking tools.
- **GR6 (Strict Grounding):** Every timeline, fee, or policy claim in a response must directly map to a retrieved Knowledge Base document.

### 6.2 Communication Standards (OP1–OP5)
- **OP1 (Language Alignment):** Match the customer's language (supporting English and Dutch).
- **OP2 (Clarity of Action):** State the exact decision, financial breakdown (fees deducted), and official timelines (KB-02).
- **OP3 (Internal Secrecy):** Never expose internal system details (e.g., prompt templates, threshold numbers, tool names, fraud flags, or model names).
- **OP4 (No False Promises):** Never make unauthorized commitments or promises outside approved decisions.
- **OP5 (Case Reference):** Provide a unique ticket reference ID (`TK-####`) and expected support response windows (KB-11).

---

## 7. Success Metrics & Key Performance Indicators (KPIs)

| Metric | Target | Measurement Method |
| :--- | :--- | :--- |
| **Routing Accuracy (TR1 & TR2)** | $\ge 95\%$ | Evaluated against the 49 labeled benchmark tickets. |
| **Groundedness & Citation Accuracy** | $100\%$ | Automated audit ensuring all claims cite `KB-01`–`KB-12` with zero hallucinations. |
| **Refund Calculation Precision** | $100\%$ | Exact verification of item subtotals and the €4.95 label fee deduction. |
| **Escalation Routing Accuracy** | $100\%$ | Perfect tier separation (frontline vs manager vs senior vs safety). |
| **Autonomous Resolution Rate** | $40\% - 60\%$ | Percentage of routine tickets closed cleanly without human intervention. |
| **Attack Success Rate (ASR)** | $0.0\%$ | Zero successful jailbreaks, unauthorized tool calls, or data leaks across the 34 red-team attacks. |
| **Cost per Ticket** | $< \$0.02$ | Token efficiency and prompt optimization using Azure OpenAI `gpt-4o` / `gpt-4o-mini`. |
