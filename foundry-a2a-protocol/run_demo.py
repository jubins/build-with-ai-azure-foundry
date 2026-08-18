"""
File 4 — End-to-end demo you can actually run locally
======================================================
coordinator.py needs a *public* specialist URL, because Foundry calls the A2A
endpoint from Azure. That's a deployment step, not a laptop step.

This file gives you the same pattern with a local coordinator: routing happens
here, the A2A call goes over real HTTP to a2a_server.py, and you can watch the
whole handshake. It's the honest local version of the Ep 9 flow.

    run_demo.py (coordinator)  ──A2A/JSON-RPC──►  a2a_server.py (specialist)
                                                        │
                                                        ▼
                                              Foundry Prompt Agent

Run:
    ./run.sh demo

That starts the specialist and then this file. To run it by hand:
    OFFLINE_MODE=1 python a2a_server.py     # terminal 1
    python run_demo.py                      # terminal 2
"""

from dotenv import load_dotenv
load_dotenv()

import os
import sys

import httpx

from a2a_client import fetch_agent_card, send_task, extract_answer

SPECIALIST_A2A_URL = os.environ.get("SPECIALIST_A2A_URL", "http://localhost:8001")

# Questions the specialist owns, per its agent card. A real coordinator lets the
# model make this call; here we keep the routing rule visible and deterministic
# so the demo shows the A2A mechanics rather than model behaviour.
_SPECIALIST_TOPICS = {
    "price", "pricing", "cost", "tier", "plan", "feature", "spec",
    "specification", "support", "available", "availability", "docs",
    "documentation", "sso", "integration",
}

_DIRECT_REPLIES = {
    "hello":     "Hello! Ask me about product features, pricing, or availability.",
    "hi":        "Hi there! What would you like to know about the product?",
    "thanks":    "You're welcome!",
    "thank you": "You're welcome!",
    "bye":       "Goodbye!",
}


def route(question: str) -> str:
    """Decide whether this question needs the specialist."""
    q = question.lower().strip().rstrip("?!.")
    if q in _DIRECT_REPLIES:
        return "direct"
    words = set(q.replace("?", " ").replace(",", " ").split())
    return "specialist" if words & _SPECIALIST_TOPICS else "direct"


def answer_direct(question: str) -> str:
    q = question.lower().strip().rstrip("?!.")
    return _DIRECT_REPLIES.get(
        q, "I handle product questions — try asking about features, pricing, or availability."
    )


def answer_via_specialist(question: str, client: httpx.Client) -> str:
    """The A2A call: discover the card, send the task, read the artifact."""
    card = fetch_agent_card(SPECIALIST_A2A_URL, client)
    print(f"  [coordinator] delegating to '{card.get('name')}' over A2A")

    task = send_task(card, question, client)
    print(f"  [coordinator] task {task.get('id', '')[:8]} → {task.get('status', {}).get('state')}")

    return extract_answer(task)


def handle(question: str, client: httpx.Client) -> str:
    decision = route(question)
    print(f"  [coordinator] route: {decision}")

    if decision == "direct":
        return f"{answer_direct(question)}\n\n[Answered by: Coordinator]"

    answer = answer_via_specialist(question, client)
    return f"{answer}\n\n[Answered by: Search Specialist via A2A]"


def main():
    questions = sys.argv[1:] or [
        "Hello",
        "What are the pricing tiers?",
        "Does the product support SSO?",
        "Thanks",
    ]

    print("\n=== Coordinator + A2A specialist (local) ===\n")
    print(f"Specialist: {SPECIALIST_A2A_URL}\n")

    with httpx.Client() as client:
        try:
            fetch_agent_card(SPECIALIST_A2A_URL, client)
        except httpx.ConnectError:
            print(f"Could not reach the specialist at {SPECIALIST_A2A_URL}.")
            print("Start it first:  ./run.sh specialist")
            sys.exit(1)

        for q in questions:
            print(f"Question: {q}")
            print(f"Answer:\n{handle(q, client)}")
            print("-" * 60)


if __name__ == "__main__":
    main()
