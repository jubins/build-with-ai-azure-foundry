## Agent-to-Agent (A2A) Endpoints in Foundry — Episode 9

Expose a Foundry agent as an A2A endpoint, then call it from a coordinator agent.

Continues from `foundry-langgraph-demo` (Ep 7) and `foundry-hosted-agent` (Ep 8) —
the same Prompt Agent, now wearing a standard A2A interface so *other agents* can call it.

```
Coordinator agent  ──A2A/JSON-RPC──►  Search Specialist  ──►  Foundry Prompt Agent
   (routes tasks)                     (a2a_server.py)
```

---

### Files

| File | What it does |
|------|--------------|
| `a2a_server.py` | The specialist. Publishes an agent card + JSON-RPC `message/send` endpoint |
| `a2a_client.py` | A hand-rolled A2A client — shows the handshake Foundry does for you |
| `coordinator.py` | Creates a Foundry agent with the specialist attached via `A2APreviewTool` |
| `run_demo.py` | Local coordinator → A2A → specialist, runnable on your laptop |
| `infra/` + `Dockerfile` | Deploys the specialist to Container Apps so Foundry can reach it |

---

### Run locally

```bash
./install.sh          # creates venv, installs deps
cp .env.example .env  # then fill in your Foundry values
./run.sh demo
```

`run.sh demo` starts the specialist, runs the coordinator against it, and shuts
it down on exit. To see the protocol with **no Azure at all**:

```bash
OFFLINE_MODE=1 ./run.sh demo
```

Other modes:

```bash
./run.sh specialist                        # just the A2A server
./run.sh client "What are the pricing tiers?"   # manual round trip
./run.sh coordinator                       # create the Foundry coordinator agent
```

---

### The two pieces of the protocol

**1. The agent card** — discovery. `GET /.well-known/agent-card.json` returns the
agent's name, description, and skills. This is what a caller reads to decide
whether to route a task here, so the descriptions do real work.

```bash
curl -s http://localhost:8001/.well-known/agent-card.json
```

**2. `message/send`** — the task call. JSON-RPC 2.0 over `POST /`:

```bash
curl -s -X POST http://localhost:8001/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"message/send",
       "params":{"message":{"role":"user","kind":"message","messageId":"m1",
                 "parts":[{"kind":"text","text":"What are the pricing tiers?"}]}}}'
```

You get back a Task whose `artifacts[].parts[].text` holds the answer.

---

### Wiring it into Foundry

Attaching the specialist to a coordinator is one tool:

```python
from azure.ai.projects.models import A2APreviewTool, PromptAgentDefinition

specialist = A2APreviewTool(base_url=SPECIALIST_A2A_URL)

client.agents.create_version(
    agent_name="research-coordinator",
    definition=PromptAgentDefinition(
        model=MODEL_DEPLOYMENT,
        instructions=INSTRUCTIONS,
        tools=[specialist],
    ),
)
```

**A note on the SDK.** The shipped `azure-ai-projects` (2.2.x) models A2A as
*discovery-based*: you pass `base_url` and Foundry fetches the agent card to learn
the name, description, and skills. You do **not** pass `name=`/`description=` on
the tool — those come from the card. Some slide decks and preview write-ups show an
`A2ATool(name=..., description=..., endpoint_url=...)` shape along with an
`A2AEndpointConfig` for enabling A2A on an existing agent; those names aren't in
the released package. The code here is written against what the SDK actually
exposes, which is why `a2a_server.py` publishes a real agent card.

Fields `A2APreviewTool` accepts: `base_url`, `agent_card_path`,
`project_connection_id`, `send_credentials_for_agent_card`.

---

### Deploy to Azure

**Foundry calls your A2A endpoint from Azure**, so `localhost:8001` will not work
for a real coordinator agent — the tool call fails to resolve. The specialist needs
a public HTTPS URL first. `run_demo.py` exists precisely because of this: it keeps
the whole loop local so you can develop without deploying.

**Prerequisites:** `azd` CLI + Docker Desktop running.

```bash
azd auth login
azd env new foundry-a2a-prod
azd env set AZURE_EXISTING_AIPROJECT_ENDPOINT https://YOUR-RESOURCE.services.ai.azure.com/api/projects/YOUR-PROJECT
azd env set AZURE_EXISTING_AGENT_ID helpful-ai-agent:1
azd up
```

`azd up` builds the image, provisions Container Apps + a managed identity, and
prints `SPECIALIST_A2A_URL`. The app scales to zero when idle, so **cost is ~$0
when not in use**.

The deployed container receives its own public URL as `SPECIALIST_A2A_URL`, which
the agent card advertises — the app can't discover its ingress hostname on its own,
so the Bicep computes it and injects it.

Then point the coordinator at the deployed specialist:

```bash
azd env get-values | grep SPECIALIST_A2A_URL   # copy this into .env
./run.sh coordinator "What are the pricing tiers?"
```

Verify the deployment before wiring it up:

```bash
curl -s https://YOUR-APP-URL/.well-known/agent-card.json
```

**Tear down everything:**

```bash
azd down
```

---

### Grant the specialist access to Foundry

The container authenticates with its managed identity, which needs a role on your
Foundry project (this is a one-time grant `azd` does not do for you):

```bash
az role assignment create \
  --assignee <managed-identity-client-id> \
  --role "Azure AI User" \
  --scope <your-foundry-project-resource-id>
```

The client ID is printed by `azd` as part of the deployment outputs, or findable on
the `id-<env-name>` identity resource.

---

### Seeing the cross-agent trace

With Application Insights connected to the same resource for both agents, one
coordinator run shows as a single trace: coordinator spans on top, an A2A tool-call
span, and the specialist's spans nested underneath. Trace context propagates over
W3C TraceContext headers across the A2A boundary.

Portal: **Operate → Traces**, or use the Foundry Trace Inspector VS Code extension
from Ep 4.

---

### Environment variables

| Variable | Description |
|----------|-------------|
| `AZURE_EXISTING_AIPROJECT_ENDPOINT` | Foundry project endpoint URL |
| `AZURE_EXISTING_AGENT_ID` | Prompt Agent backing the specialist (`name:version`) |
| `AZURE_MODEL_DEPLOYMENT` | Model deployment for the coordinator (default `gpt-4o-mini`) |
| `SPECIALIST_A2A_URL` | Public base URL of the specialist |
| `COORDINATOR_AGENT_NAME` | Name of the coordinator agent (default `research-coordinator`) |
| `A2A_PORT` | Local port for the specialist (default `8001`) |
| `OFFLINE_MODE` | `1` to run the protocol with canned replies, no Azure |

---

### When to use this pattern

Multiple domains, multiple teams, independent deployability and debugging. If one
team owns the whole thing and a single agent can handle it, a Prompt Agent with a
few tools (Ep 2) or a hosted agent (Ep 8) is the better fit — don't split until the
complexity is real.

A2A is in preview: `learn.microsoft.com/en-us/azure/ai-foundry/agents/`
