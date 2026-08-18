"""
File 2 — Agent guardrails: capping output tokens
=================================================
Without a cap, a reasoning loop that goes wrong can burn thousands of tokens in
a single run. You want a hard ceiling.

Where the cap actually lives
----------------------------
`max_output_tokens` is a parameter on the *response call*, not a field on the
agent definition. Checked against azure-ai-projects 2.2.0: PromptAgentDefinition
accepts model, instructions, temperature, top_p, reasoning, tools, tool_choice,
text, and structured_inputs — there is no max-output-tokens field on it.

The practical consequence: you cannot set this once on the agent and forget it.
Every call site has to pass it, which means it belongs in a shared wrapper like
`ask()` below rather than sprinkled through your codebase.

    response = openai_client.responses.create(
        input=[...],
        max_output_tokens=1024,      # ← the guardrail
        extra_body={"agent_reference": {...}},
    )

Run:
    python agent_guardrails.py "your question"
"""

from dotenv import load_dotenv
load_dotenv()

import os
import sys

from tracing_config import max_output_tokens, configure_tracing

FOUNDRY_ENDPOINT = os.environ.get("AZURE_EXISTING_AIPROJECT_ENDPOINT", "")
AGENT_ID         = os.environ.get("AZURE_EXISTING_AGENT_ID", "helpful-ai-agent:1")

_parts        = AGENT_ID.split(":")
AGENT_NAME    = _parts[0]
AGENT_VERSION = _parts[1] if len(_parts) > 1 else "1"

DEFAULT_MAX_OUTPUT_TOKENS = 1024


def build_client():
    if not FOUNDRY_ENDPOINT:
        raise SystemExit(
            "AZURE_EXISTING_AIPROJECT_ENDPOINT is not set.\n"
            "Copy .env.example to .env and fill in your Foundry project endpoint."
        )

    from azure.identity import DefaultAzureCredential
    from azure.ai.projects import AIProjectClient

    project_client = AIProjectClient(
        endpoint=FOUNDRY_ENDPOINT,
        credential=DefaultAzureCredential(),
    )
    return project_client.get_openai_client()


def ask(openai_client, question: str, cap: int | None = None) -> tuple[str, dict]:
    """
    Call the agent with a hard output cap.

    Returns the text plus the usage/finish details you'd want on a dashboard.
    A finish_reason of "length" means the cap truncated the response — worth
    alerting on if it happens often, since it usually means the cap is too low
    or the agent is looping.
    """
    cap = cap or max_output_tokens() or DEFAULT_MAX_OUTPUT_TOKENS

    response = openai_client.responses.create(
        input=[{"role": "user", "content": question}],
        max_output_tokens=cap,
        extra_body={
            "agent_reference": {
                "name":    AGENT_NAME,
                "version": AGENT_VERSION,
                "type":    "agent_reference",
            }
        },
    )

    usage = getattr(response, "usage", None)
    details = {
        "cap":           cap,
        "input_tokens":  getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "truncated":     getattr(response, "incomplete_details", None) is not None,
    }
    return response.output_text, details


def main():
    question = " ".join(sys.argv[1:]) or "Explain what Azure AI Foundry is."

    configure_tracing()
    cap = max_output_tokens() or DEFAULT_MAX_OUTPUT_TOKENS

    print(f"\n=== Agent call with max_output_tokens={cap} ===\n")

    client = build_client()
    answer, details = ask(client, question, cap)

    print(f"Question: {question}")
    print(f"Answer:\n{answer}\n")
    print(f"Tokens — in: {details['input_tokens']}, out: {details['output_tokens']} (cap {details['cap']})")

    if details["truncated"]:
        print("\nResponse hit the cap and was truncated. Raise the cap, or find out")
        print("why the agent is generating this much.")


if __name__ == "__main__":
    main()
