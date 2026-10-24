# Project 1: RAG Document Agent

A single-agent system for document intelligence and grounded Q&A using OpenAI function calling, Azure AI Content Understanding, and Cohere Reranking.

---

## 📌 Architecture & Pipeline

As outlined in the root [readme.md](../readme.md), the RAG Document Agent follows a 4-stage pipeline:

```text
[ Document Ingestion ] 
   (Public Web URL or Azure Blob Storage URL with SAS token)
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

## ☁️ Azure Services & Configuration Details

### 1. Azure AI Content Understanding
- **Service Role:** Cloud-native document intelligence service (part of Microsoft Foundry) that extracts structured Markdown, tables, key-value pairs, and hierarchical layouts from complex documents.
- **Analyzer Used:** `prebuilt-layout`.
- **Input Requirement:** Azure Content Understanding processes documents via HTTP/HTTPS URLs. The target document must be publicly accessible on the web (e.g. arXiv research papers) or hosted in Azure Blob Storage with a Shared Access Signature (SAS) token.
  > **Note:** Because Azure Content Understanding runs as a cloud service, it cannot directly reach into your local machine's file paths.
- **Environment Variables:**
  - `AZURE_CONTENT_UNDERSTANDING_ENDPOINT`: The Foundry / AI service endpoint (`https://<resource-name>.services.ai.azure.com/`).
  - `CONTENT_UNDERSTANDING_KEY`: Secret API key for authentication.

### 2. Azure OpenAI Service
- **Service Role:** Provides enterprise-grade LLMs powering the conversational agent, intent detection, and grounded synthesis.
- **Deployment Used:** `gpt-4o` or `gpt-5-mini`.
- **Function Calling:** Leverages native OpenAI tool calling (`tools`) to decide dynamically whether document analysis is needed based on user input.
- **Environment Variables:**
  - `AZURE_OPENAI_ENDPOINT`: Target Azure OpenAI resource endpoint (`https://<resource-name>.openai.azure.com/`).
  - `AZURE_OPENAI_API_KEY`: Authentication key.
  - `AZURE_OPENAI_API_VERSION`: API version (e.g. `2024-10-21`).
  - `AZURE_OPENAI_CHAT_DEPLOYMENT`: Name of the deployed model (e.g. `gpt-4o`).

### 3. Cohere Reranker
- **Service Role:** Post-retrieval ranking (`rerank-v3.5`) that scores and filters extracted document chunks, ensuring only the most relevant context is passed to the LLM context window.

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
├── docs/                   # 📂 Reference documentation
└── pipeline/               # 📂 Exploration & prototyping scripts (demo.py)
```

### Module Responsibilities

| File | Purpose |
| :--- | :--- |
| [`config.py`](config.py) | Centralizes configuration, validates credentials from `.env`, and initializes `chat_client`. |
| [`document_processor.py`](document_processor.py) | Handles document ingestion, layout extraction (`ContentUnderstandingClient`), markdown chunking, and Cohere reranking (`rerank-v3.5`). |
| [`tools.py`](tools.py) | Defines the `analyze_document` tool schema with strict instructions to prevent hallucinated URLs. |
| [`chat_app.py`](chat_app.py) | Orchestrates the conversational agent loop and synthesizes grounded answers from retrieved sections. |

---

## ⚙️ Environment Configuration

Create a [`.env`](../.env) file in the root directory with your Azure and Cohere credentials:

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
You: Summarize the key findings in https://arxiv.org/pdf/2610.30135
```
The agent automatically:
1. Detects the URL and calls `analyze_document(url_or_path="https://arxiv.org/pdf/2610.30135", query="key findings")`.
2. Sends the document to Azure AI Content Understanding for layout and text extraction.
3. Reranks the extracted markdown chunks using Cohere `rerank-v3.5`.
4. Synthesizes a grounded response citing the document.

### Example 2: General Q&A
If no document URL is mentioned, the assistant answers directly without triggering external document analysis:
```text
You: What is Retrieval-Augmented Generation?
```
