## Foundry Hosted Agent — FastAPI Service

A REST API that wraps your Azure AI Foundry Prompt Agent, built with FastAPI.

---

### Run locally

1. Copy the example env file:

```bash
cp .env.example .env
```

2. Start the server:

```bash
./run.sh
```

API available at `http://localhost:8000`. Swagger UI at `http://localhost:8000/docs`.

---

### Deploy to Azure (Container Apps)

This gives you a real public HTTPS URL. The container scales to zero when idle, so **cost is ~$0 when not in use**.

**Prerequisites:** `azd` CLI + Docker Desktop running.

**One-time setup:**

```bash
azd auth login
azd env new foundry-agent-prod
azd env set AZURE_EXISTING_AIPROJECT_ENDPOINT https://jubinsoni-9036-resource.services.ai.azure.com/api/projects/jubinsoni-9036
azd env set AZURE_EXISTING_AGENT_ID helpful-ai-agent:1
```

**Deploy:**

```bash
azd up
```

`azd` will:
1. Build the Docker image from `Dockerfile`
2. Push it to Azure Container Registry
3. Provision a Container Apps environment + managed identity
4. Deploy the container with your Foundry env vars injected
5. Print your public URL when done

**Tear down everything (stops all charges):**

```bash
azd down
```

---

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check |
| GET | `/agent-info` | Shows configured endpoint and agent |
| POST | `/chat` | Send a message to the Foundry agent |

**Chat example:**

```bash
curl -X POST https://YOUR-APP-URL/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What can you help me with?"}'
```

---

### Environment variables

| Variable | Description |
|----------|-------------|
| `AZURE_EXISTING_AIPROJECT_ENDPOINT` | Your Foundry project endpoint URL |
| `AZURE_EXISTING_AGENT_ID` | Agent name and version (`name:version`) |
