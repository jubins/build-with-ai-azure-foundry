"""
File 1 — The specialist, exposed as an A2A endpoint
====================================================
A search specialist agent that speaks the Agent-to-Agent (A2A) protocol.

Two things make this an A2A endpoint rather than a plain REST API:

  1. GET  /.well-known/agent-card.json  — the *agent card*. This is how a caller
     discovers what this agent is, what it can do, and where to send tasks.
     Foundry's A2APreviewTool fetches exactly this path by default.

  2. POST /                             — JSON-RPC 2.0 `message/send`. The caller
     sends a task message, this agent works, and returns a Task with an artifact.

The actual answering is delegated to your Foundry Prompt Agent (Ep 2/7/8), so
this is the same agent you already have — just wearing an A2A interface.

Run:
    python a2a_server.py            # or: ./run.sh specialist
"""

from dotenv import load_dotenv
load_dotenv()

import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ── Config ────────────────────────────────────────────────────────────────────

FOUNDRY_ENDPOINT = os.environ.get("AZURE_EXISTING_AIPROJECT_ENDPOINT", "")
AGENT_ID         = os.environ.get("AZURE_EXISTING_AGENT_ID", "helpful-ai-agent:1")
A2A_PORT         = int(os.environ.get("A2A_PORT", "8001"))

# The URL other agents use to reach this one. Locally that's localhost; in Azure
# it's your Container App URL. The agent card advertises this value.
PUBLIC_URL = os.environ.get("SPECIALIST_A2A_URL", f"http://localhost:{A2A_PORT}")

_parts        = AGENT_ID.split(":")
AGENT_NAME    = _parts[0]
AGENT_VERSION = _parts[1] if len(_parts) > 1 else "1"

# Set OFFLINE_MODE=1 to run the full A2A handshake without any Azure calls.
# Useful for demoing the protocol itself before wiring up Foundry.
OFFLINE_MODE = os.environ.get("OFFLINE_MODE", "").lower() in {"1", "true", "yes"}


# ── Foundry client ────────────────────────────────────────────────────────────

openai_client: Any = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global openai_client

    if OFFLINE_MODE:
        print("OFFLINE_MODE — replies are canned, no Foundry calls made.")
    elif not FOUNDRY_ENDPOINT:
        raise RuntimeError(
            "AZURE_EXISTING_AIPROJECT_ENDPOINT is not set. "
            "Copy .env.example to .env, or set OFFLINE_MODE=1 to demo the "
            "protocol without Azure."
        )
    else:
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient

        project_client = AIProjectClient(
            endpoint=FOUNDRY_ENDPOINT,
            credential=DefaultAzureCredential(),
        )
        openai_client = project_client.get_openai_client()
        print(f"Connected to Foundry: {FOUNDRY_ENDPOINT}")
        print(f"Backing agent: {AGENT_NAME} v{AGENT_VERSION}")

    print(f"A2A agent card: {PUBLIC_URL}/.well-known/agent-card.json")
    yield


app = FastAPI(
    title="Search Specialist (A2A)",
    description="A Foundry agent exposed over the Agent-to-Agent protocol",
    version="1.0.0",
    lifespan=lifespan,
)


# ── 1. The agent card ─────────────────────────────────────────────────────────
# This is the discovery document. A coordinator fetches it to learn the agent's
# name, skills, and where to POST tasks. Keep the descriptions specific — the
# calling model reads them to decide whether to route a task here.

AGENT_CARD = {
    "protocolVersion": "0.3.0",
    "name": "Search Specialist",
    "description": (
        "Searches product documentation and the web. Use for any question about "
        "product features, specifications, pricing, or availability."
    ),
    "url": PUBLIC_URL,
    "preferredTransport": "JSONRPC",
    "version": "1.0.0",
    "capabilities": {
        "streaming": False,
        "pushNotifications": False,
        "stateTransitionHistory": False,
    },
    "defaultInputModes":  ["text/plain"],
    "defaultOutputModes": ["text/plain"],
    "skills": [
        {
            "id": "product_search",
            "name": "Product documentation search",
            "description": (
                "Answers questions about product features, specifications, "
                "pricing, and availability by searching docs and the web."
            ),
            "tags": ["search", "documentation", "product"],
            "examples": [
                "What are the pricing tiers?",
                "Does the product support single sign-on?",
            ],
        }
    ],
}


@app.get("/.well-known/agent-card.json")
def agent_card():
    """Discovery endpoint — A2APreviewTool fetches this path by default."""
    return AGENT_CARD


@app.get("/health")
def health():
    return {"status": "ok", "mode": "offline" if OFFLINE_MODE else "foundry"}


# ── 2. Doing the work ─────────────────────────────────────────────────────────

def _extract_text(message: dict) -> str:
    """Pull the text out of an A2A message's parts array."""
    parts = message.get("parts", []) if isinstance(message, dict) else []
    chunks = [
        p.get("text", "")
        for p in parts
        if isinstance(p, dict) and p.get("kind", "text") == "text"
    ]
    return "\n".join(c for c in chunks if c).strip()


def _answer(question: str) -> str:
    """Delegate to the Foundry Prompt Agent — same call as Ep 7 and Ep 8."""
    if OFFLINE_MODE:
        return (
            f"[offline specialist] I would search the docs for: {question!r}. "
            "Set OFFLINE_MODE=0 and configure Foundry for a real answer."
        )

    response = openai_client.responses.create(
        input=[{"role": "user", "content": question}],
        extra_body={
            "agent_reference": {
                "name":    AGENT_NAME,
                "version": AGENT_VERSION,
                "type":    "agent_reference",
            }
        },
    )
    return response.output_text


# ── 3. JSON-RPC endpoint ──────────────────────────────────────────────────────
# A2A rides on JSON-RPC 2.0. The method we implement is `message/send`:
# caller sends a message, we return a completed Task carrying the answer.

def _rpc_error(req_id: Any, code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=200,  # JSON-RPC signals errors in the body, not the HTTP status
        content={"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}},
    )


@app.post("/")
async def jsonrpc(request: Request):
    try:
        body = await request.json()
    except Exception:
        return _rpc_error(None, -32700, "Parse error")

    req_id = body.get("id")
    method = body.get("method")
    params = body.get("params") or {}

    if method != "message/send":
        return _rpc_error(req_id, -32601, f"Method not found: {method}")

    message  = params.get("message") or {}
    question = _extract_text(message)
    if not question:
        return _rpc_error(req_id, -32602, "message.parts contained no text")

    print(f"  [specialist] received task: {question!r}")

    try:
        answer = _answer(question)
    except Exception as exc:
        return _rpc_error(req_id, -32000, f"Specialist failed: {exc}")

    task_id    = str(uuid.uuid4())
    context_id = message.get("contextId") or str(uuid.uuid4())
    now        = datetime.now(timezone.utc).isoformat()

    # A completed Task. The `artifacts` array carries the result the caller reads.
    task = {
        "id":        task_id,
        "contextId": context_id,
        "kind":      "task",
        "status": {
            "state":     "completed",
            "timestamp": now,
        },
        "artifacts": [
            {
                "artifactId": str(uuid.uuid4()),
                "name":       "answer",
                "parts":      [{"kind": "text", "text": answer}],
            }
        ],
    }

    print(f"  [specialist] completed task {task_id[:8]}")
    return {"jsonrpc": "2.0", "id": req_id, "result": task}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=A2A_PORT)
