## Foundry Hosted Agent — FastAPI Service

A REST API that wraps your Azure AI Foundry Prompt Agent, built with FastAPI.

### Prerequisites

See `install.sh` for one-time setup (Python 3.13+, Azure Developer CLI, Foundry extension).

You also need to be logged in to Azure:

```bash
az login
```

### Setup

1. Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

The defaults already point to the `jubinsoni-9036` Foundry project and the `helpful-ai-agent:1` agent.

2. Start the server:

```bash
./run.sh
```

The API will be available at `http://localhost:8000`.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check |
| GET | `/agent-info` | Shows configured endpoint and agent |
| POST | `/chat` | Send a message to the Foundry agent |

### Chat request

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What can you help me with?"}'
```

Optional — override the system prompt for one call:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello", "system_prompt": "Respond only in haiku."}'
```

### Interactive API docs

FastAPI ships a built-in Swagger UI at:

```
http://localhost:8000/docs
```

### Environment variables

| Variable | Description |
|----------|-------------|
| `AZURE_EXISTING_AIPROJECT_ENDPOINT` | Your Foundry project endpoint URL |
| `AZURE_EXISTING_AGENT_ID` | Agent name and version in `name:version` format |

### Deploying to Azure

To wrap this in a web app and deploy to Azure, run from this directory:

```bash
azd init -t https://github.com/Azure-Samples/get-started-with-ai-agents
azd up
```

To tear down:

```bash
azd down
```
