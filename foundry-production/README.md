## Foundry Agents in Production — Episode 10

The pre-launch checklist, as code you can run instead of a slide you have to remember.

Final episode of the series — after Ep 8 (hosted agent) and Ep 9 (A2A endpoints),
this is what you do before any of it faces real users.

```bash
./install.sh          # creates venv, installs deps
cp .env.example .env  # then fill in your Azure values
./run.sh audit        # the checklist, as pass/fail
```

---

### The one command

```
$ ./run.sh audit

=== Foundry production pre-launch audit ===

  [PASS  ] Content recording    disabled (production default)
  [PASS  ] Sampling             app exports 10% of traces; ingestion sampling: not set (100%)
  [WARN  ] Retention            90 days (target 30)
            → App Insights → Usage and estimated costs → Data retention → 30 days
  [WARN  ] RBAC                 4 principal(s) can read trace content — Contributor×1, Log Analytics Reader×3
            → Review these assignments. Anyone with these roles can read recorded
              prompt and response content in Log Analytics.
  [MANUAL] Content safety       not readable via this SDK path — verify by hand
            → Foundry portal → your project → Guardrails + controls.
  [PASS  ] max_output_tokens    1024 tokens

  3 passed · 0 failed · 2 warnings · 1 manual · 0 skipped
```

Exits non-zero on any FAIL, so you can gate a deploy pipeline with it:

```bash
./run.sh audit || exit 1
./run.sh audit --json    # machine-readable
```

Checks that need Azure (`sampling`, `retention`, `RBAC`) degrade to **SKIP** with a
reason if credentials or resource names are missing — a partial setup still gives
you a useful report rather than a stack trace.

---

### Files

| File | What it does |
|------|--------------|
| `preflight_audit.py` | The checklist as a pass/fail report |
| `tracing_config.py` | Content recording + sampling, with production-safe defaults |
| `agent_guardrails.py` | Calling the agent with a hard output-token cap |
| `infra/alerts.bicep` | The five Monitor alert rules |
| `deploy_alerts.sh` | One command to deploy them |

---

### What trace data actually contains

The distinction that matters, because it decides whether PII lands in Log Analytics:

| Always logged | Only if content recording is ON | Never logged |
|---|---|---|
| Thread + run ID | Full system prompt text | API keys, secrets |
| Agent + model name | **User message content** | Payment data |
| Tool names + call IDs | Model response text | Content-safety-blocked text |
| Token counts | Tool arguments | Data from outside your project |
| Span duration, status | Tool results | |
| Finish reason | | |

See it resolved for your current env:

```bash
./run.sh config
ENABLE_CONTENT_RECORDING=true ./run.sh config    # prints a warning
```

**Production default is OFF.** Turn it on for a scoped debugging session on
non-PII data, then turn it off. Nothing in this repo hardcodes it to `True`.

---

### Two corrections to the slides

Both were checked against `azure-ai-projects` 2.2.0 and the current Azure Monitor docs.

**1. `max_output_tokens` is not an agent-definition field.**

`PromptAgentDefinition` accepts `model`, `instructions`, `temperature`, `top_p`,
`reasoning`, `tools`, `tool_choice`, `text`, and `structured_inputs` — there is no
max-output-tokens field on it. The cap is a **per-request** parameter:

```python
response = openai_client.responses.create(
    input=[...],
    max_output_tokens=1024,          # ← here, not on the agent
    extra_body={"agent_reference": {...}},
)
```

The practical consequence is worth saying on camera: you **cannot** set this once
and forget it. Every call site needs it, so it belongs in a shared wrapper — which
is what `agent_guardrails.py` demonstrates.

**2. Sample in the app, not at ingestion.**

"App Insights samples at 100% by default" is right — `configure_azure_monitor`
defaults to `sampling_ratio=1.0`. But the fix belongs in your app, not the portal:

```python
configure_azure_monitor(connection_string=conn, sampling_ratio=0.1)
```

Microsoft's docs explicitly label portal **ingestion sampling** as "not
recommended" — it drops data at the ingestion point with no control over which
spans survive, which produces broken traces. Use it only when you can't change
the app. The audit reports both so you can see which one is actually in force.

---

### The five alerts

Set these up before go-live, not after the first incident.

```bash
./run.sh alerts --what-if    # preview
./run.sh alerts              # deploy
```

| Alert | Threshold | Catches |
|---|---|---|
| Error rate | > 1% of runs fail | Agent errors, tool failures, safety blocks |
| P95 latency | > 10 seconds | Context accumulation (the Ep 5 bug) |
| Daily token spend | > your budget | Runaway loops, traffic spikes |
| Content safety blocks | > 0.5% | Prompt injection, or a misconfigured threshold |
| Tool call failure rate | > 2% of calls | Tool outages, search timeouts |

Set `ACTION_GROUP_ID` in `.env` to actually notify someone — without it the rules
fire into the void, which is fine for a demo and useless in production.

**Tune the queries before you trust them.** All five are KQL
`scheduledQueryRules`, because these thresholds are ratios and daily aggregations
that metric alerts can't express against agent semantics. The queries filter on
span names like `execute_tool` and `gen_ai`, which vary with your instrumentation.
Run each one in **Logs** against your own data first and adjust — an alert that
silently matches zero rows looks identical to one that's passing.

---

### The two items code can't do for you

**Content safety** — Foundry portal → your project → **Guardrails + controls**.
Non-negotiable for anything public-facing. The audit reports this as `MANUAL`
rather than inventing a green check for something it can't read.

**RBAC** — the audit lists who holds trace-reading roles, but deciding who *should*
have them is your call:

```bash
az role assignment list --scope <app-insights-resource-id> -o table
az role assignment delete --assignee <principal> --role "Log Analytics Reader" --scope <id>
```

Log Analytics Reader grants read access to all recorded trace content. If content
recording was ever on, that includes user messages.

---

### Environment variables

| Variable | Description |
|----------|-------------|
| `AZURE_SUBSCRIPTION_ID` | Subscription holding your App Insights resource |
| `AZURE_RESOURCE_GROUP` | Its resource group |
| `APPLICATION_INSIGHTS_NAME` | App Insights connected to your Foundry project |
| `ENABLE_CONTENT_RECORDING` | `false` in production — logs prompts when `true` |
| `OTEL_TRACE_SAMPLING_RATIO` | Fraction of traces exported (`0.1` = 10%) |
| `MAX_OUTPUT_TOKENS` | Hard cap per response |
| `EXPECTED_RETENTION_DAYS` | What the audit treats as passing (default 30) |
| `EXPECTED_SAMPLING_RATIO` | What the audit treats as passing (default 0.1) |
| `ACTION_GROUP_ID` | Action group for alert notifications |

The Azure checks need `az login` and Reader on the subscription.

---

### The series

Ep1 Platform overview → Ep2 First Prompt Agent → Ep3 Tracing setup →
Ep4 VS Code extension → Ep5 Debugging → Ep6 Token costs → Ep7 LangGraph tracing →
Ep8 Hosted Agent → Ep9 A2A endpoints → **Ep10 Production readiness**

Foundry Trace Inspector: `marketplace.visualstudio.com/items?itemName=jubinsoni.foundry-trace-inspector`
