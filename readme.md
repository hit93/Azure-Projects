# AI-103: Azure AI Agent Suite

A collection of four connected projects demonstrating AI agent patterns on Microsoft Azure.

---

### Project 1: RAG Document Agent
Single-agent system for document intelligence and grounded Q&A using function calling.
- **Pipeline:** Ingestion $\to$ Layout Extraction $\to$ Hybrid Index $\to$ Tool-Calling Agent.
- **Key Services:** Azure AI Content Understanding, Azure AI Search (hybrid vector + semantic), Foundry Agent Service.

---

### Project 2: Resolve — Multi-Agent Customer Support Desk
Self-contained multi-agent system that reads a customer ticket, finds the answer, takes safe actions through tools, and asks a human before any risky one. It uses its own small knowledge base and a mock orders API, so it runs on its own.
- **Agent Roles (4):**
  - **Triage Agent:** Classifies the ticket (billing, delivery, product, other), extracts order ID and urgency, and routes it.
  - **Knowledge Agent:** Answers policy and how-to questions with grounded citations from a support knowledge base (RAG).
  - **Action Agent:** Calls MCP tools to look up orders, check delivery status, and create refund or replacement requests.
  - **Approval and Reply Agent:** Auto-approves low-risk actions (for example a refund under a set amount); queues high-risk ones for human review; writes the final customer reply and a case log.
- **Flow:** Ticket $\to$ Triage $\to$ Knowledge / Action $\to$ Approval Gate $\to$ Reply + Case Log.
- **Key Services:** Foundry Agent Service (multi-agent orchestration), MCP server (orders and refunds tools on mock data), Azure AI Search (policy documents), Azure AI Content Safety (input and output guardrails), Foundry tracing and evaluations.
- **What makes it meaningful:** Real decisions with real risk limits, grounded answers, a human-in-the-loop path, and measurable quality (groundedness, correct routing, refund accuracy).

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