import json
from config import chat_client, DEPLOYMENT, CU_KEY, COHERE_KEY
from document_processor import analyze_document
from tools import tools

SYSTEM_PROMPT = (
    "You are an expert AI assistant. "
    "When the user explicitly provides a document URL or local file path to analyze, "
    "call analyze_document using that specific URL or path and their question as the query. "
    "CRITICAL: Never invent, guess, or hallucinate document URLs or filenames. "
    "If the user asks a general question without providing any document or URL, "
    "answer directly from your knowledge base without calling any tools, or politely ask the user for the document URL/path."
)


def main():
    print("=" * 60)
    print("🤖 Azure AI + Cohere Rerank Document Agent")
    print(f"   Model       : {DEPLOYMENT}")
    print(f"   Content Doc : {'✅ Configured' if CU_KEY else '⚠️ Key missing in .env'}")
    print(f"   Cohere Rank : {'✅ Configured' if COHERE_KEY else '⚠️ Key missing in .env (optional)'}")
    print("   Type 'quit' or 'exit' to exit.")
    print("=" * 60 + "\n")

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    ]

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print("Goodbye!")
            break

        messages.append({"role": "user", "content": user_input})

        try:
            response = chat_client.chat.completions.create(
                model=DEPLOYMENT,
                messages=messages,
                tools=tools,
            )
            msg = response.choices[0].message

            if msg.tool_calls:
                messages.append(msg)
                for tool_call in msg.tool_calls:
                    args = json.loads(tool_call.function.arguments)
                    tool_output = analyze_document(
                        url_or_path=args.get("url_or_path", ""),
                        query=args.get("query", user_input),
                    )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_output,
                    })

                final_res = chat_client.chat.completions.create(
                    model=DEPLOYMENT,
                    messages=messages,
                )
                reply = final_res.choices[0].message.content or ""
            else:
                reply = msg.content or ""

            messages.append({"role": "assistant", "content": reply})
            print(f"\nAssistant: {reply}")

        except Exception as e:
            print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    main()
