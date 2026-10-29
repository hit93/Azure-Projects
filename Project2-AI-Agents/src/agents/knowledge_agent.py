"""
Knowledge Agent for Resolve Support Desk.
Loads policy documents (KB-01 to KB-12), performs Cohere reranking,
and enforces strict grounding with REFUSE_NO_POLICY for ungrounded topics.
"""

import re
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from openai import AzureOpenAI

from src.config import (
    KB_DIR,
    COHERE_API_KEY,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_CHAT_DEPLOYMENT,
)

# Topics deliberately excluded from policy documents (TRD 3.2, GR6, ES7)
UNSUPPORTED_TOPICS = [
    r"\bgift\s*cards?\b",
    r"\bcadeaubon(nen)?\b",
    r"\bcadeaukaart(en)?\b",
    r"\bprice\s*match(ing)?\b",
    r"\bprijsgarantie\b",
    r"\bloyalty\b",
    r"\brewards?\s*points?\b",
    r"\bbeloningspunten\b",
    r"\bin-?store\s*pickup\b",
    r"\bphysical\s*stores?\b",
]

KNOWLEDGE_SYSTEM_PROMPT = """You are the specialized Knowledge Agent for NorthPeak Support Desk.
Your task is to answer policy, return, delivery, and warranty inquiries strictly grounded in provided knowledge base excerpts.

CRITICAL RULES:
1. Grounding Guarantee: Every fact in your answer must be supported by the provided KB docs.
2. Mandatory Citation: Explicitly cite document IDs (e.g., [KB-01], [KB-04]) next to each policy rule.
3. If the query asks about gift cards, price matching, loyalty rewards, or topics absent from the excerpts,
   you MUST reply with: REFUSE_NO_POLICY.
4. Keep answers concise, factual, and supportive.
"""


def load_all_kb_documents() -> List[Dict[str, str]]:
    """Loads all KB-*.md documents from the kb directory."""
    documents = []
    if not KB_DIR.is_dir():
        return documents

    for path in sorted(KB_DIR.glob("KB-*.md")):
        doc_id = path.stem.upper()
        content = path.read_text(encoding="utf-8").strip()
        lines = content.splitlines()
        title = lines[0].replace("#", "").strip() if lines else doc_id
        # Extract body text without the markdown title header
        body = "\n".join([line for line in lines if not line.strip().startswith("#")]).strip()
        documents.append({
            "id": doc_id,
            "title": title,
            "content": content,
            "body": body,
            "path": str(path),
        })
    return documents


def _is_unsupported_topic(query: str) -> bool:
    """Checks whether the query is about intentionally unsupported subjects (gift cards, price match)."""
    q_lower = query.lower()
    return any(re.search(pat, q_lower) for pat in UNSUPPORTED_TOPICS)


def _heuristic_rank(query: str, documents: List[Dict[str, str]]) -> List[Tuple[Dict[str, str], float]]:
    """Simple term-overlap scoring when Cohere is not configured or offline."""
    query_words = set(re.findall(r"\w+", query.lower()))
    stopwords = {"the", "a", "an", "is", "for", "of", "and", "in", "to", "how", "what", "can", "i", "do", "you", "my", "our"}
    clean_query = query_words - stopwords

    if not clean_query:
        return [(doc, 0.1) for doc in documents]

    scored = []
    for doc in documents:
        text = f"{doc['title']} {doc['content']}".lower()
        score = 0.0
        for w in clean_query:
            if w in text:
                score += 1.0
                if w in doc['title'].lower():
                    score += 1.5  # Extra weight for title matches

        normalized_score = min(1.0, score / max(1, len(clean_query) * 2))
        scored.append((doc, round(normalized_score, 3)))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def query_knowledge_base(query: str, top_k: int = 3) -> Dict[str, Any]:
    """
    Retrieves grounded answers and citations from the policy knowledge base.
    Uses Cohere Rerank if configured; otherwise falls back to local heuristic ranking.
    Enforces REFUSE_NO_POLICY for ungrounded/unsupported topics.
    """
    if not query or not query.strip():
        return {
            "status": "REFUSE_NO_POLICY",
            "answer": "No query provided.",
            "citations": [],
            "confidence": 0.0,
        }

    # 1. Check for intentionally unsupported topics (Rule GR6 & ES7)
    if _is_unsupported_topic(query):
        return {
            "status": "REFUSE_NO_POLICY",
            "answer": (
                "NorthPeak does not currently offer gift cards, price matching, or loyalty rewards under our published policies. "
                "A support specialist can assist with any further questions."
            ),
            "citations": [],
            "confidence": 0.0,
        }

    documents = load_all_kb_documents()
    if not documents:
        return {
            "status": "REFUSE_NO_POLICY",
            "answer": "Knowledge base documents are currently unavailable.",
            "citations": [],
            "confidence": 0.0,
        }

    top_docs = []
    top_score = 0.0

    # 2. Try Cohere Rerank if key is available
    if COHERE_API_KEY:
        try:
            import cohere
            co = cohere.ClientV2(api_key=COHERE_API_KEY)
            doc_texts = [f"{d['title']}\n{d['content']}" for d in documents]
            response = co.rerank(
                model="rerank-v3.5",
                query=query,
                documents=doc_texts,
                top_n=top_k,
            )
            for r in response.results:
                matched_doc = documents[r.index]
                score = float(r.relevance_score)
                top_docs.append((matched_doc, score))
            if top_docs:
                top_score = top_docs[0][1]
        except Exception:
            top_docs = []

    # Fallback ranking if Cohere was not used or encountered an error
    if not top_docs:
        scored = _heuristic_rank(query, documents)
        top_docs = scored[:top_k]
        top_score = top_docs[0][1] if top_docs else 0.0

    # 3. Grounding Threshold: Refuse if relevance is too low (< 0.25)
    if top_score < 0.25:
        return {
            "status": "REFUSE_NO_POLICY",
            "answer": "This topic is not covered in our standard store policies. An agent can follow up with more details.",
            "citations": [],
            "confidence": round(top_score, 2),
        }

    matched_citations = [doc["id"] for doc, _ in top_docs[:top_k]]
    excerpts_text = "\n\n".join([f"[{d['id']} - {d['title']}]\n{d['content']}" for d, _ in top_docs])

    # 4. Generate answer using Azure OpenAI if configured
    if AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY:
        try:
            client = AzureOpenAI(
                azure_endpoint=AZURE_OPENAI_ENDPOINT,
                api_key=AZURE_OPENAI_API_KEY,
                api_version=AZURE_OPENAI_API_VERSION,
            )
            completion = client.chat.completions.create(
                model=AZURE_OPENAI_CHAT_DEPLOYMENT,
                messages=[
                    {"role": "system", "content": KNOWLEDGE_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Customer Question:\n{query}\n\nRelevant Policy Excerpts:\n{excerpts_text}",
                    },
                ],
                temperature=0.0,
            )
            answer = completion.choices[0].message.content.strip()

            if "REFUSE_NO_POLICY" in answer:
                return {
                    "status": "REFUSE_NO_POLICY",
                    "answer": answer,
                    "citations": [],
                    "confidence": 0.0,
                }

            # Extract any cited KB numbers from answer text
            found_citations = sorted(list(set(re.findall(r"KB-\d{2}", answer))))
            return {
                "status": "GROUNDED",
                "answer": answer,
                "citations": found_citations or matched_citations[:2],
                "confidence": round(top_score, 2),
            }
        except Exception:
            pass

    # 5. Deterministic fallback answer synthesis if LLM is offline
    best_doc, best_score = top_docs[0]
    doc_body = best_doc.get("body") or best_doc["content"]
    return {
        "status": "GROUNDED",
        "answer": f"According to our policy [{best_doc['id']}]:\n{doc_body}",
        "citations": [best_doc["id"]],
        "confidence": round(best_score, 2),
    }
