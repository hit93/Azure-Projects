# Project 1: RAG Document Agent

A single-agent system for document intelligence and grounded Q&A using OpenAI function calling, Azure AI Content Understanding, and Cohere Reranking.

---

## 📌 Architecture & Pipeline

As outlined in the root [readme.md](../readme.md), the RAG Document Agent follows a 4-stage pipeline:

```text
[ Document Ingestion ] 
   (Local PDF/Word in docs/ or Remote Web URL)
           │
           ▼
[ Layout & Text Extraction ] 
   (Azure AI Content Understanding — 'prebuilt-layout' analyzer)
           │
           ▼
[ Semantic Chunking & Reranking ] 
   (Markdown paragraph splitting + Cohere rerank-v3.5)
           │
           ▼
[ Tool-Calling Agent ] 
   (Azure OpenAI with function calling — analyze_document)
```

---

## 🗂️ Project Structure

The project is structured modularly for clarity, maintainability, and single responsibility:

```text
Project1-RAG/
├── README.md               # 📖 This documentation file
├── config.py               # ⚙️ Environment variable loading & client initialization
├── document_processor.py   # 📄 Azure Content Understanding, chunking & Cohere reranking
├── tools.py                # 🛠️ OpenAI function schema definition for tool calling
├── chat_app.py             # 💬 Main interactive CLI chat loop
├── docs/                   # 📂 Directory for local files (PDFs, Word docs)
└── pipeline/               # 📂 Standalone exploration & prototyping scripts (demo.py)
```

### Module Responsibilities

| File | Purpose |
| :--- | :--- |
| [`config.py`](config.py) | Centralizes configuration, validates credentials from `.env`, and initializes `chat_client`. |
| [`document_processor.py`](document_processor.py) | Handles document ingestion, layout extraction (`ContentUnderstandingClient`), markdown chunking, and Cohere reranking (`rerank-v3.5`). |
| [`tools.py`](tools.py) | Defines the `analyze_document` tool schema with strict instructions to prevent hallucinated URLs. |
| [`chat_app.py`](chat_app.py) | Orchestrates the conversational agent loop and synthesizes grounded answers from retrieved sections. |

---

## 🔑 Key Services & Prerequisites

- **Azure OpenAI**: Model deployment (e.g. `gpt-4o` or `gpt-5-mini`) for the agentic chat interface and tool calling.
- **Azure AI Content Understanding**: Extracts markdown structure, tables, and layouts using the `prebuilt-layout` analyzer.
- **Cohere Reranker (`rerank-v3.5`)**: Reorders document chunks by relevance to the user's specific query.
- *(Roadmap)* **Azure AI Search & Foundry Agent Service**: Persistent hybrid vector search and managed agent orchestration.

---

## ⚙️ Environment Configuration

Ensure your root [`.env`](../.env) file contains the following environment variables:

```env
# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/
AZURE_OPENAI_API_KEY=<your-azure-openai-key>
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o

# Azure AI Content Understanding
AZURE_CONTENT_UNDERSTANDING_ENDPOINT=https://<your-resource>.services.ai.azure.com/
CONTENT_UNDERSTANDING_KEY=<your-content-understanding-key>

# Cohere Reranking
COHERE_API_KEY=<your-cohere-api-key>
```

---

## 🚀 Getting Started

### 1. Activate the Virtual Environment
```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

### 2. Install Required Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the Chat Application
```bash
python Project1-RAG/chat_app.py
```

---

## 💬 Usage Examples

### Example 1: Web Document Analysis
Provide an online PDF or paper link directly in your prompt:
```text
You: Summarize the main methodology in https://arxiv.org/pdf/2610.30135
```
The agent automatically:
1. Calls `analyze_document(url_or_path="https://arxiv.org/pdf/2610.30135", query="main methodology")`.
2. Sends the document to Azure AI Content Understanding for layout extraction.
3. Reranks the extracted markdown chunks using Cohere.
4. Generates a grounded synthesis citing the retrieved passages.

### Example 2: Local File Analysis
Place documents inside the [`docs/`](docs/) directory and refer to them:
```text
You: What are the main findings in Cricket_YOLOv5_Detection_Report.docx?
```

### Example 3: General Q&A
If no document is mentioned, the assistant answers directly without triggering external document analysis:
```text
You: What is Retrieval-Augmented Generation?
```
