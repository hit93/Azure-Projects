import os
from pathlib import Path
from dotenv import load_dotenv
from openai import AzureOpenAI

# ── Paths ────────────────────────────────────────────────────────────────────
THIS_DIR = Path(__file__).resolve().parent
ROOT_DIR = THIS_DIR.parent
DOCS_DIR = THIS_DIR / "docs"

# ── Load Environment Variables ───────────────────────────────────────────────
load_dotenv(dotenv_path=ROOT_DIR / ".env")

# ── Azure OpenAI Configuration ──────────────────────────────────────────────
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY  = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VER  = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
DEPLOYMENT            = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o")

# ── Azure AI Content Understanding Configuration ───────────────────────────
CU_ENDPOINT = os.getenv("AZURE_CONTENT_UNDERSTANDING_ENDPOINT") or os.getenv("AZURE_PROJECT_ENDPOINT")
CU_KEY      = os.getenv("AZURE_CONTENT_UNDERSTANDING_KEY") or os.getenv("CONTENT_UNDERSTANDING_KEY")

# ── Cohere Reranker Configuration ───────────────────────────────────────────
COHERE_KEY  = os.getenv("COHERE_API_KEY")

# ── Validation ──────────────────────────────────────────────────────────────
if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_API_KEY:
    raise ValueError("❌ Missing AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_API_KEY in .env file.")

# ── Client Initializations ──────────────────────────────────────────────────
chat_client = AzureOpenAI(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_API_KEY,
    api_version=AZURE_OPENAI_API_VER,
)
