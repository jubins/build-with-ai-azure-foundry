"""
Foundry Hosted Agent — FastAPI service
=======================================
Exposes your Azure AI Foundry Prompt Agent as a REST API.

Endpoints:
  POST /chat          — send a message, get a response
  GET  /health        — liveness check
  GET  /agent-info    — show which agent + endpoint is configured

Auth: DefaultAzureCredential (az login, managed identity, env vars)
"""

from dotenv import load_dotenv
load_dotenv()

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

# ── Config ────────────────────────────────────────────────────────────────────

FOUNDRY_ENDPOINT = os.environ.get("AZURE_EXISTING_AIPROJECT_ENDPOINT", "")
AGENT_ID         = os.environ.get("AZURE_EXISTING_AGENT_ID", "helpful-ai-agent:1")

if not FOUNDRY_ENDPOINT:
    raise RuntimeError(
        "AZURE_EXISTING_AIPROJECT_ENDPOINT is not set. "
        "Copy .env.example to .env and fill in your values."
    )

_parts       = AGENT_ID.split(":")
AGENT_NAME   = _parts[0]
AGENT_VERSION = _parts[1] if len(_parts) > 1 else "1"

# ── Foundry client (initialised once at startup) ──────────────────────────────

project_client: AIProjectClient
openai_client: object


@asynccontextmanager
async def lifespan(app: FastAPI):
    global project_client, openai_client
    project_client = AIProjectClient(
        endpoint=FOUNDRY_ENDPOINT,
        credential=DefaultAzureCredential(),
    )
    openai_client = project_client.get_openai_client()
    print(f"Connected to Foundry endpoint: {FOUNDRY_ENDPOINT}")
    print(f"Agent: {AGENT_NAME} v{AGENT_VERSION}")
    yield
    # nothing to tear down — HTTP client closes itself


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Foundry Hosted Agent",
    description="REST wrapper around an Azure AI Foundry Prompt Agent",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ───────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    system_prompt: str | None = None  # optional per-request system override


class ChatResponse(BaseModel):
    reply: str
    agent: str
    version: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/agent-info")
def agent_info():
    return {
        "endpoint": FOUNDRY_ENDPOINT,
        "agent":    AGENT_NAME,
        "version":  AGENT_VERSION,
    }


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")

    messages = []
    if req.system_prompt:
        messages.append({"role": "system", "content": req.system_prompt})
    messages.append({"role": "user", "content": req.message})

    try:
        response = openai_client.responses.create(
            input=messages,
            extra_body={
                "agent_reference": {
                    "name":    AGENT_NAME,
                    "version": AGENT_VERSION,
                    "type":    "agent_reference",
                }
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Foundry agent error: {exc}") from exc

    return ChatResponse(
        reply=response.output_text,
        agent=AGENT_NAME,
        version=AGENT_VERSION,
    )
