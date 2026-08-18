"""
File 3 — The coordinator: adding an A2A specialist as a tool
=============================================================
Creates (or updates) a Foundry Prompt Agent that can call the specialist from
a2a_server.py over the A2A protocol.

The whole point: from the coordinator model's perspective, the remote specialist
is *just another tool*. You give it a base URL, Foundry fetches the agent card,
and the skills on that card become callable tools.

    tool = A2APreviewTool(base_url=SPECIALIST_A2A_URL)
    client.agents.create_version(
        agent_name="research-coordinator",
        definition=PromptAgentDefinition(model=..., instructions=..., tools=[tool]),
    )

Note on the SDK surface — the shipped azure-ai-projects (2.2.x) models A2A as a
*discovery-based* tool: you pass `base_url`, not a name/description pair. Foundry
reads the name, description, and skills from the agent card the server publishes,
which is why a2a_server.py takes that card seriously.

Important: Foundry calls the URL from Azure, so `SPECIALIST_A2A_URL` must be
publicly reachable. `http://localhost:8001` works for the local demo in
run_demo.py, but for a real Foundry agent you need a deployed URL (or a tunnel).
See the README's "Deploy to Azure" section.

Run:
    python coordinator.py                 # create/update the coordinator agent
    python coordinator.py "your question" # ...then ask it something
"""

from dotenv import load_dotenv
load_dotenv()

import os
import sys

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import A2APreviewTool, PromptAgentDefinition

# ── Config ────────────────────────────────────────────────────────────────────

FOUNDRY_ENDPOINT   = os.environ.get("AZURE_EXISTING_AIPROJECT_ENDPOINT", "")
MODEL_DEPLOYMENT   = os.environ.get("AZURE_MODEL_DEPLOYMENT", "gpt-4o-mini")
SPECIALIST_A2A_URL = os.environ.get("SPECIALIST_A2A_URL", "http://localhost:8001")
COORDINATOR_NAME   = os.environ.get("COORDINATOR_AGENT_NAME", "research-coordinator")

AGENT_CARD_PATH = "/.well-known/agent-card.json"

INSTRUCTIONS = """\
You are a research coordinator. You do not answer product questions from your own
knowledge — you delegate them.

Use the Search Specialist tool for any question about product features,
specifications, pricing, or availability. Pass the user's question through
faithfully, then synthesise the specialist's answer into a clear reply.

If a question needs no specialist (a greeting, a clarification), answer directly
and briefly. Always say which specialist you consulted, if any.
"""


def _require_endpoint() -> None:
    if not FOUNDRY_ENDPOINT:
        raise SystemExit(
            "AZURE_EXISTING_AIPROJECT_ENDPOINT is not set.\n"
            "Copy .env.example to .env and fill in your Foundry project endpoint."
        )


def build_client() -> AIProjectClient:
    _require_endpoint()
    return AIProjectClient(
        endpoint=FOUNDRY_ENDPOINT,
        credential=DefaultAzureCredential(),
    )


# ── 1. Register the specialist as a tool on the coordinator ───────────────────

def create_coordinator(client: AIProjectClient) -> str:
    """Create a new version of the coordinator agent with the A2A tool attached."""

    specialist = A2APreviewTool(
        base_url=SPECIALIST_A2A_URL,
        agent_card_path=AGENT_CARD_PATH,
        # For an endpoint behind auth, store credentials in a project connection
        # and pass project_connection_id=... instead of relying on an open URL.
    )

    print(f"Registering A2A specialist: {SPECIALIST_A2A_URL}{AGENT_CARD_PATH}")

    agent = client.agents.create_version(
        agent_name=COORDINATOR_NAME,
        definition=PromptAgentDefinition(
            model=MODEL_DEPLOYMENT,
            instructions=INSTRUCTIONS,
            tools=[specialist],
        ),
        description="Coordinator that delegates product questions to an A2A search specialist",
    )

    version = getattr(agent, "version", "1")
    print(f"Coordinator ready: {COORDINATOR_NAME} v{version}")
    return str(version)


# ── 2. Ask the coordinator something ──────────────────────────────────────────

def ask_coordinator(client: AIProjectClient, question: str, version: str = "1") -> str:
    """Send a question to the coordinator. It decides whether to call the specialist."""
    openai_client = client.get_openai_client()

    response = openai_client.responses.create(
        input=[{"role": "user", "content": question}],
        extra_body={
            "agent_reference": {
                "name":    COORDINATOR_NAME,
                "version": version,
                "type":    "agent_reference",
            }
        },
    )
    return response.output_text


def main():
    question = " ".join(sys.argv[1:]).strip()

    print("\n=== Foundry coordinator + A2A specialist ===\n")

    client  = build_client()
    version = create_coordinator(client)

    if not question:
        print(
            "\nAgent created. Ask it something:\n"
            f'    python coordinator.py "What are the pricing tiers?"\n'
        )
        return

    if SPECIALIST_A2A_URL.startswith(("http://localhost", "http://127.0.0.1")):
        print(
            "\nWarning: SPECIALIST_A2A_URL points at localhost. Foundry calls the\n"
            "specialist from Azure and cannot reach your laptop, so the A2A tool\n"
            "call will fail. Deploy the specialist or use a tunnel — see README.\n"
        )

    print(f"\nQuestion: {question}")
    print(f"Answer:\n{ask_coordinator(client, question, version)}\n")


if __name__ == "__main__":
    main()
