"""
File 2 — LangGraph + Microsoft Foundry Agent
=============================================
Builds a LangGraph pipeline that calls your Foundry Prompt Agent.

What this shows:
- A 3-node LangGraph state machine: classify → answer → format
- The 'answer_with_foundry' node calls your Foundry Prompt Agent
- The 'classify' node does lightweight keyword routing (simple vs complex)
- The 'format' node cleans up the response for display
- Conditional edges — LangGraph routing based on question type

All LLM calls go through project_client.get_openai_client().responses.create()
using the agent_reference pattern — the same call that works in run_agent.py.

Install:
    pip install -r requirements.txt

Run:
    python langgraph_foundry.py
"""

from dotenv import load_dotenv
load_dotenv()

import os
from typing import TypedDict, Literal
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from langgraph.graph import StateGraph, END

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
    """Direct call to your Foundry Prompt Agent."""
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


# ── 2. State schema ──────────────────────────────────────────────────────────

class State(TypedDict):
    question:      str
    question_type: Literal["simple", "complex"]
    raw_answer:    str
    final_answer:  str


# ── 3. Nodes ─────────────────────────────────────────────────────────────────

# Simple keyword-based classifier — avoids needing a second LLM endpoint.
_SIMPLE_TRIGGERS = {"hello", "hi", "bye", "goodbye", "thanks", "thank you", "yes", "no"}

def classify(state: State) -> State:
    q = state["question"].lower().strip().rstrip("!.")
    question_type = "simple" if q in _SIMPLE_TRIGGERS else "complex"
    print(f"  [classify] '{state['question']}' → {question_type}")
    return {**state, "question_type": question_type}


def answer_simple(state: State) -> State:
    quick_answers = {
        "hello":      "Hello! How can I help you today?",
        "hi":         "Hi there! What can I help you with?",
        "bye":        "Goodbye! Have a great day.",
        "goodbye":    "Goodbye! Have a great day.",
        "thanks":     "You're welcome!",
        "thank you":  "You're welcome!",
        "yes":        "Got it.",
        "no":         "Understood.",
    }
    q = state["question"].lower().strip().rstrip("!.")
    answer = quick_answers.get(q, f"Sure — {state['question']}")
    print(f"  [answer_simple] Answered directly without Foundry agent")
    return {**state, "raw_answer": answer}


def answer_with_foundry(state: State) -> State:
    print(f"  [answer_foundry] Calling Foundry agent: '{state['question']}'")
    raw = call_foundry_agent(state["question"])
    return {**state, "raw_answer": raw}


def format_response(state: State) -> State:
    answer = state["raw_answer"].strip()
    source = "Foundry Agent" if state["question_type"] == "complex" else "Direct"
    formatted = f"{answer}\n\n[Answered by: {source}]"
    print(f"  [format] Done")
    return {**state, "final_answer": formatted}


# ── 4. Routing function ──────────────────────────────────────────────────────

def route_by_type(state: State) -> Literal["answer_simple", "answer_with_foundry"]:
    return "answer_simple" if state["question_type"] == "simple" else "answer_with_foundry"


# ── 5. Build the graph ───────────────────────────────────────────────────────

graph = StateGraph(State)

graph.add_node("classify",            classify)
graph.add_node("answer_simple",       answer_simple)
graph.add_node("answer_with_foundry", answer_with_foundry)
graph.add_node("format_response",     format_response)

graph.set_entry_point("classify")

graph.add_conditional_edges(
    "classify",
    route_by_type,
    {
        "answer_simple":       "answer_simple",
        "answer_with_foundry": "answer_with_foundry",
    }
)

graph.add_edge("answer_simple",       "format_response")
graph.add_edge("answer_with_foundry", "format_response")
graph.add_edge("format_response",     END)

app = graph.compile()


# ── 6. Run it ────────────────────────────────────────────────────────────────

def run(question: str) -> str:
    result = app.invoke({
        "question":      question,
        "question_type": "complex",
        "raw_answer":    "",
        "final_answer":  "",
    })
    return result["final_answer"]


def main():
    print("\n=== LangGraph + Foundry Agent Demo ===\n")
    print("Graph: classify → [answer_simple | answer_with_foundry] → format\n")

    questions = [
        "Hello",
        "What can you help me with?",
        "Tell me what you know about AI.",
        "Thanks",
    ]

    for q in questions:
        print(f"\nQuestion: {q}")
        answer = run(q)
        print(f"Answer:\n{answer}")
        print("-" * 50)


if __name__ == "__main__":
    main()
