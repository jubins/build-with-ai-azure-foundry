"""
File 2 — Calling an A2A endpoint by hand
=========================================
A minimal A2A client. This is what Foundry's A2APreviewTool does for you
internally — worth seeing once so the tool isn't a black box.

The two-step handshake:
  1. GET  {base_url}/.well-known/agent-card.json   → discover the agent
  2. POST {card["url"]}  with JSON-RPC message/send → send a task, get a Task back

Run (with a2a_server.py already running in another terminal):
    python a2a_client.py "What are the pricing tiers?"
"""

from dotenv import load_dotenv
load_dotenv()

import os
import sys
import uuid

import httpx

DEFAULT_BASE_URL = os.environ.get("SPECIALIST_A2A_URL", "http://localhost:8001")
AGENT_CARD_PATH  = "/.well-known/agent-card.json"


def fetch_agent_card(base_url: str, client: httpx.Client) -> dict:
    """Step 1 — discovery. Learn who this agent is and where to send tasks."""
    url = base_url.rstrip("/") + AGENT_CARD_PATH
    resp = client.get(url, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def send_task(card: dict, question: str, client: httpx.Client) -> dict:
    """Step 2 — send a task via JSON-RPC `message/send`, return the Task object."""
    endpoint = card.get("url", DEFAULT_BASE_URL)

    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": str(uuid.uuid4()),
                "kind": "message",
                "parts": [{"kind": "text", "text": question}],
            }
        },
    }

    resp = client.post(endpoint, json=payload, timeout=120.0)
    resp.raise_for_status()
    body = resp.json()

    if "error" in body:
        raise RuntimeError(f"A2A error {body['error'].get('code')}: {body['error'].get('message')}")

    return body["result"]


def extract_answer(task: dict) -> str:
    """Read the text out of the Task's artifacts."""
    chunks = []
    for artifact in task.get("artifacts", []):
        for part in artifact.get("parts", []):
            if part.get("kind", "text") == "text" and part.get("text"):
                chunks.append(part["text"])
    return "\n".join(chunks).strip()


def ask(question: str, base_url: str = DEFAULT_BASE_URL) -> str:
    """Full round trip: discover, send, read."""
    with httpx.Client() as client:
        card = fetch_agent_card(base_url, client)
        task = send_task(card, question, client)
        return extract_answer(task)


def main():
    question = " ".join(sys.argv[1:]) or "What are the pricing tiers?"
    base_url = DEFAULT_BASE_URL

    print("\n=== A2A client — manual round trip ===\n")
    print(f"Base URL: {base_url}")

    with httpx.Client() as client:
        try:
            card = fetch_agent_card(base_url, client)
        except httpx.ConnectError:
            print(f"\nCould not reach {base_url}.")
            print("Start the specialist first:  ./run.sh specialist")
            sys.exit(1)

        print(f"\n[1] Agent card discovered")
        print(f"    name:   {card.get('name')}")
        print(f"    skills: {', '.join(s['id'] for s in card.get('skills', []))}")
        print(f"    url:    {card.get('url')}")

        print(f"\n[2] Sending task: {question!r}")
        task = send_task(card, question, client)
        print(f"    task id: {task.get('id', '')[:8]}")
        print(f"    state:   {task.get('status', {}).get('state')}")

        print(f"\n[3] Answer:\n{extract_answer(task)}\n")


if __name__ == "__main__":
    main()
