"""
Specialized Agent implementations for Resolve Support Desk:
- TriageAgent: Entity extraction, language detection, intent categorization.
- KnowledgeAgent: RAG over policy documents with Cohere reranking & refusal tokens.
- ReplyAgent: Customer-facing communication synthesis with policy compliance.
"""

from src.agents.triage_agent import triage_ticket
from src.agents.knowledge_agent import query_knowledge_base
from src.agents.reply_agent import draft_customer_reply

__all__ = ["triage_ticket", "query_knowledge_base", "draft_customer_reply"]

