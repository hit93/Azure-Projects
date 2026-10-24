# AI-103: Azure AI Agent Suite

A collection of four connected projects demonstrating AI agent patterns on Microsoft Azure.

---

### Project 1: [RAG Document Agent](Project1-RAG/)
Single-agent system for document intelligence and grounded Q&A using function calling.
- **Pipeline:** Document Ingestion $\to$ Layout Extraction $\to$ Semantic Chunking & Reranking $\to$ Tool-Calling Agent.
- **Key Services:** Azure AI Content Understanding (`prebuilt-layout`), Cohere Rerank (`rerank-v3.5`), Azure OpenAI Service (`gpt-4o`/`gpt-5-mini` tool calling).

---

### Project 2: Resolve — Governed Multi-Agent Customer Support Desk
Self-contained multi-agent system that reads a customer ticket, finds the answer, takes safe actions through tools, and asks a human before any risky one. Unlike a chatbot with a good prompt, every decision is bounded, traceable and reversible, and the guardrails are tested under attack. It uses its own small knowledge base and a mock orders API, so it runs on its own.

- **Agent Roles (4):**
  - **Triage Agent:** Classifies the ticket (billing, delivery, product, other), extracts order ID and urgency, and routes it.
  - **Knowledge Agent:** Answers policy and how-to questions with grounded citations from a support knowledge base (RAG). Refuses instead of guessing when the policy documents do not support an answer.
  - **Action Agent:** Calls MCP tools to look up orders, check delivery status, and create refund or replacement requests.
  - **Approval and Reply Agent:** Auto-approves low-risk actions (for example a refund under a set amount); queues high-risk ones for human review; writes the final customer reply and a case log.
- **Flow:** Ticket $\to$ Input Guardrails $\to$ Triage $\to$ Knowledge / Action $\to$ Approval Gate $\to$ Output Guardrails $\to$ Reply + Audit Record.

#### Advanced layer 1: Governed autonomy and audit trail
- **Per-agent identity:** Each agent runs under its own managed identity (Microsoft Entra, keyless) with least-privilege roles. For example, only the Action Agent can reach the refunds tool, and the Knowledge Agent has read-only access to the search index.
- **Decision record for every case:** The model and deployment, prompt version, policy version, tool inputs and outputs, token counts, estimated cost and the final decision are stored together, so any decision can be reconstructed after the fact.
- **Append-only audit log:** Decision records are written to tamper-resistant storage (for example Azure Blob immutable storage), separate from the operational data.
- **Policy as versioned data:** Refund limits, risk rules and escalation thresholds live in a versioned policy file rather than in prompts, so changing a limit is a reviewed change and the policy version is recorded in each decision.
- **Reversible actions:** Every refund or replacement request can be undone through a compensating action, and reversals are logged the same way.
- **Human review queue:** High-risk and low-confidence cases go to a reviewer interface. Reviewer decisions and comments are stored as labeled examples for evaluation.
- **Cost and limits:** Token and cost tracking per agent and per ticket, with rate-limit handling and a per-ticket budget that escalates to a human when exceeded.

#### Advanced layer 2: Red-team validation
- **Guardrails on both sides:** Azure AI Content Safety on input and output, with Prompt Shields to catch direct and indirect prompt injection (including instructions hidden in ticket text or retrieved documents).
- **Automated adversarial runs:** A PyRIT-based red-team suite attacks the desk with jailbreaks, indirect prompt injection, multi-turn escalation and attempts to push the Action Agent past its refund limit or into another customer's order.
- **Pass/fail gate:** Attack success rate is measured per release, and a regression in any category fails the CI pipeline.

#### Evaluation and operations
- **Scenario test set:** A labeled set of tickets covering clear approvals, clear escalations, policy gaps, ambiguous requests and attacks.
- **Metrics:** Routing accuracy, groundedness and citation correctness, refund-amount accuracy, correct escalation rate, auto-resolution rate, cost per ticket and attack success rate.
- **Observability:** Foundry tracing across all four agents, with latency and token breakdowns per step.
- **Delivery:** Infrastructure defined as code and deployed through GitHub Actions with keyless authentication. The evaluation and red-team suites run before each release.

- **Key Services:** Foundry Agent Service (multi-agent orchestration), MCP server (orders and refunds tools on mock data), Azure AI Search (policy documents), Azure AI Content Safety (guardrails and Prompt Shields), Microsoft Entra managed identities, Azure Blob immutable storage (audit log), PyRIT (red teaming), Foundry tracing and evaluations, Azure Monitor / Application Insights, GitHub Actions.
- **What makes it meaningful:** Real decisions with real risk limits, grounded answers, a human-in-the-loop path, full traceability of every decision, and measurable quality and security (groundedness, correct routing, refund accuracy, attack success rate).

---

### Project 3: Vision & Content Understanding Suite
Multimodal system for computer vision, document intelligence, and generative media.
- **Capabilities:** Visual Q&A, image/video generation and editing, and responsible AI guardrails.
- **Key Services:** Azure OpenAI (multimodal/vision models), Azure AI Content Understanding.

---

### Project 4: Voice-Enabled Text Analytics Agent
Speech interface and text processing service designed to integrate across the suite.
- **Capabilities:** Voice front-end for Project 1; registers as an MCP tool monitored by Project 2.
- **Key Services:** Azure AI Speech (STT/TTS), Azure AI Translator, LLM structured text analytics.