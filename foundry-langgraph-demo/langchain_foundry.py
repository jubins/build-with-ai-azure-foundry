"""
File 1 — LangChain + Microsoft Foundry Agent
=============================================
Wraps your Foundry Prompt Agent as a LangChain tool, then builds a
multi-turn conversation loop on top of it.

All LLM calls go through project_client.get_openai_client().responses.create()
using the agent_reference pattern — the same call that works in run_agent.py.
AzureChatOpenAI is NOT used here because the Foundry endpoint does not expose
a standard /chat/completions route.

Install:
    pip install -r requirements.txt

Run:
    python langchain_foundry.py
"""

from dotenv import load_dotenv
load_dotenv()

import os
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage

# ── 1. Foundry client (same pattern as run_agent.py) ────────────────────────

FOUNDRY_ENDPOINT = os.environ["AZURE_EXISTING_AIPROJECT_ENDPOINT"]
AGENT_ID         = os.environ.get("AZURE_EXISTING_AGENT_ID", "helpful-ai-agent:1")
_parts           = AGENT_ID.split(":")
AGENT_NAME       = _parts[0]
AGENT_VERSION    = _parts[1] if len(_parts) > 1 else "1"

project_client = AIProjectClient(
    endpoint=FOUNDRY_ENDPOINT,
    credential=DefaultAzureCredential(),
)
openai_client = project_client.get_openai_client()


def call_foundry_agent(user_message: str) -> str:
    """Calls your Foundry Prompt Agent and returns its text response."""
    response = openai_client.responses.create(
        input=[{"role": "user", "content": user_message}],
        extra_body={
            "agent_reference": {
                "name":    AGENT_NAME,
                "version": AGENT_VERSION,
                "type":    "agent_reference",
            }
        },
    )
    return response.output_text


# ── 2. LangChain tools ───────────────────────────────────────────────────────

@tool
def ask_foundry_agent(question: str) -> str:
    """
    Ask the Foundry AI agent a question.
    Use this for any question the user asks — the Foundry agent knows how to help.
    """
    return call_foundry_agent(question)


@tool
def get_current_date(_: str = "") -> str:
    """Returns today's date. Use when the user asks what day or date it is."""
    from datetime import date
    return f"Today's date is {date.today().strftime('%B %d, %Y')}."


tools_by_name = {
    "ask_foundry_agent": ask_foundry_agent,
    "get_current_date":  get_current_date,
}


# ── 3. Simple routing layer ───────────────────────────────────────────────────
# Since the Foundry endpoint doesn't expose /chat/completions, we do a lightweight
# keyword-based route instead of using AzureChatOpenAI as an orchestrator.

def route_and_answer(question: str) -> str:
    q = question.lower()
    if any(w in q for w in ("date", "today", "day")):
        return get_current_date.invoke("")
    return ask_foundry_agent.invoke(question)


# ── 4. Multi-turn conversation ────────────────────────────────────────────────

def main():
    print("\n=== LangChain + Foundry Agent Demo ===\n")

    chat_history: list = []

    questions = [
        "What can you help me with?",
        "What is today's date?",
        "Tell me more about your capabilities.",
    ]

    for question in questions:
        print(f"You: {question}")
        answer = route_and_answer(question)
        print(f"Agent: {answer}\n")

        chat_history.append(HumanMessage(content=question))
        chat_history.append(AIMessage(content=answer))


if __name__ == "__main__":
    main()
