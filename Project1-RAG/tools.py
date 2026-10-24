"""OpenAI tool definitions for function calling."""

tools = [
    {
        "type": "function",
        "function": {
            "name": "analyze_document",
            "description": (
                "Analyze and extract the most relevant sections of an explicit document URL "
                "or local file path provided by the user using layout analysis and Cohere reranking."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url_or_path": {
                        "type": "string",
                        "description": "The exact web URL or local file path provided by the user. Do NOT make up or hallucinate URLs.",
                    },
                    "query": {
                        "type": "string",
                        "description": "The user's specific question or topic to search and rerank within the document.",
                    },
                },
                "required": ["url_or_path"],
            },
        },
    }
]
