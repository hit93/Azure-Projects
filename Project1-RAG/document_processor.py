import re
import json
from pathlib import Path
from azure.ai.contentunderstanding import ContentUnderstandingClient
from azure.ai.contentunderstanding.models import AnalysisInput
from azure.core.credentials import AzureKeyCredential

from config import CU_ENDPOINT, CU_KEY, COHERE_KEY, THIS_DIR, ROOT_DIR, DOCS_DIR


def chunk_markdown(text: str, max_chunk_len: int = 1200) -> list[str]:
    """Splits markdown text into logical paragraphs or sections."""
    raw_blocks = re.split(r"\n\s*\n", text)
    chunks = []
    curr = []
    curr_len = 0
    for block in raw_blocks:
        b = block.strip()
        if not b:
            continue
        if curr_len + len(b) > max_chunk_len and curr:
            chunks.append("\n\n".join(curr))
            curr = [b]
            curr_len = len(b)
        else:
            curr.append(b)
            curr_len += len(b)
    if curr:
        chunks.append("\n\n".join(curr))
    return chunks or [text]


def rerank_chunks(query: str, chunks: list[str], top_n: int = 4) -> list[str]:
    """Uses Cohere rerank-v3.5 to select the most relevant document chunks."""
    if not COHERE_KEY or not chunks:
        return chunks[:top_n]
    try:
        import cohere
        co = cohere.ClientV2(api_key=COHERE_KEY)
        res = co.rerank(
            model="rerank-v3.5",
            query=query,
            documents=chunks,
            top_n=min(top_n, len(chunks)),
        )
        print(f"🎯 [Cohere] Reranked {len(chunks)} sections down to top {len(res.results)} most relevant.")
        return [chunks[item.index] for item in res.results]
    except Exception as e:
        print(f"⚠️ [Cohere Warning] Rerank skipped: {e}")
        return chunks[:top_n]


def analyze_document(url_or_path: str, query: str = "") -> str:
    """Extracts text from a document URL/file using Azure Content Understanding,

    then reranks sections using Cohere.
    """
    print(f"\n🔧 [Tool Calling] Analyzing document: {url_or_path}...")

    # Guard: check if Content Understanding key is configured
    if not CU_KEY or not CU_ENDPOINT:
        return (
            "Error: AZURE_CONTENT_UNDERSTANDING_KEY or AZURE_CONTENT_UNDERSTANDING_ENDPOINT "
            "is not set in .env. Please configure them to analyze documents."
        )

    try:
        # 1. Prepare input (web URL or local file)
        if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
            inp = AnalysisInput(url=url_or_path)
        else:
            p = Path(url_or_path)
            if not p.is_absolute():
                candidates = [THIS_DIR / p, ROOT_DIR / p, DOCS_DIR / p.name]
                for c in candidates:
                    if c.exists():
                        p = c
                        break
            if not p.exists():
                return f"Error: Local file '{url_or_path}' not found on disk."
            with open(p, "rb") as f:
                inp = AnalysisInput(data=f.read())

        # 2. Call Azure AI Content Understanding
        cu_client = ContentUnderstandingClient(
            endpoint=CU_ENDPOINT,
            credential=AzureKeyCredential(CU_KEY),
        )
        poller = cu_client.begin_analyze(analyzer_id="prebuilt-layout", inputs=[inp])
        result = poller.result()

        # 3. Extract Markdown
        md_parts = [c.markdown for c in result.contents if getattr(c, "markdown", None)]
        full_text = "\n\n".join(md_parts) if md_parts else json.dumps(result.as_dict())

        # 4. Chunk and Rerank with Cohere
        chunks = chunk_markdown(full_text)
        search_query = query if query else "Key information, summary, and findings"
        top_chunks = rerank_chunks(query=search_query, chunks=chunks, top_n=4)

        return "\n\n---\n\n".join(top_chunks)

    except Exception as e:
        return f"Error analyzing document: {str(e)}"
