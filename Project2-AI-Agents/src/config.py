import os
from pathlib import Path
from dotenv import load_dotenv

# ── Paths ────────────────────────────────────────────────────────────────────
SRC_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SRC_DIR.parent
ROOT_DIR = PROJECT_DIR.parent

DATA_DIR = PROJECT_DIR / "data"
KB_DIR = PROJECT_DIR / "kb"
AUDIT_LOG_DIR = PROJECT_DIR / "audit_logs"
TESTS_DIR = PROJECT_DIR / "tests"

# Ensure runtime directories exist
AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── Load Environment Variables ───────────────────────────────────────────────
# Load root .env first (shared with Project 1), then local .env if present
load_dotenv(dotenv_path=ROOT_DIR / ".env")
load_dotenv(dotenv_path=PROJECT_DIR / ".env")

# ── System Evaluation Clock Assertion ────────────────────────────────────────
# Fixed evaluation date for deterministic regression testing (Tuesday, Oct 20, 2026)
EVALUATION_DATE = "2026-10-20"

# ── Azure OpenAI Configuration ──────────────────────────────────────────────
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")

# Support deployments from both Project 1 & Project 2 conventions
AZURE_OPENAI_CHAT_DEPLOYMENT = (
    os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
    or os.getenv("DEPLOYMENT")
    or "gpt-4o"
)
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.getenv(
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small"
)

# ── Cohere Reranker Configuration ───────────────────────────────────────────
COHERE_API_KEY = os.getenv("COHERE_API_KEY") or os.getenv("COHERE_KEY")

# ── LangSmith Observability & Debugging ───────────────────────────────────────
LANGCHAIN_TRACING_V2 = os.getenv("LANGCHAIN_TRACING_V2", "true").lower() == "true"
LANGCHAIN_ENDPOINT = os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY")
LANGCHAIN_PROJECT = os.getenv("LANGCHAIN_PROJECT", "resolve-multi-agent")

# Set OS environment variables for LangChain SDK auto-instrumentation
if LANGCHAIN_TRACING_V2 and LANGCHAIN_API_KEY:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_ENDPOINT"] = LANGCHAIN_ENDPOINT
    os.environ["LANGCHAIN_API_KEY"] = LANGCHAIN_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = LANGCHAIN_PROJECT


def validate_config(require_api_keys: bool = False) -> dict:
    """
    Validates essential environment variables and local paths.
    Returns a dictionary of configuration health status.
    """
    status = {
        "azure_openai_endpoint": bool(AZURE_OPENAI_ENDPOINT),
        "azure_openai_key": bool(AZURE_OPENAI_API_KEY),
        "chat_deployment": AZURE_OPENAI_CHAT_DEPLOYMENT,
        "cohere_key": bool(COHERE_API_KEY),
        "langsmith_tracing": LANGCHAIN_TRACING_V2 and bool(LANGCHAIN_API_KEY),
        "evaluation_date": EVALUATION_DATE,
        "data_dir_exists": DATA_DIR.is_dir(),
        "kb_dir_exists": KB_DIR.is_dir(),
        "kb_files_count": len(list(KB_DIR.glob("KB-*.md"))),
        "audit_dir_exists": AUDIT_LOG_DIR.is_dir(),
    }

    if require_api_keys:
        missing = []
        if not AZURE_OPENAI_ENDPOINT:
            missing.append("AZURE_OPENAI_ENDPOINT")
        if not AZURE_OPENAI_API_KEY:
            missing.append("AZURE_OPENAI_API_KEY")
        if missing:
            raise ValueError(f"Missing required environment variables in .env: {', '.join(missing)}")

    return status

