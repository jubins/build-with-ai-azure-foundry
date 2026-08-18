"""
File 3 — Pre-launch audit
==========================
Runs the Episode 10 checklist against a real project and prints pass/fail,
instead of clicking through six portal blades and trusting your memory.

What it checks
--------------
  1. Content recording   — local config (env), the setting your app controls
  2. Sampling            — App Insights ingestion sampling %, plus local ratio
  3. Retention           — App Insights retention_in_days vs your target
  4. RBAC                — who holds trace-reading roles on App Insights
  5. Content safety      — reported, not auto-checked (see the note below)
  6. max_output_tokens   — local config

What it can't check honestly
----------------------------
Content safety config isn't exposed as a first-class read on the project via
this SDK path, so item 5 prints as MANUAL with a portal link rather than
inventing a green check. An audit that lies about what it verified is worse
than one that admits a gap.

Needs `az login` and Reader on the subscription. Every check degrades to SKIP
with a reason rather than crashing, so a partial credential set still gives a
useful report.

Run:
    python preflight_audit.py
    python preflight_audit.py --json     # machine-readable, for CI
"""

from dotenv import load_dotenv
load_dotenv()

import json
import os
import sys

# ── Config ────────────────────────────────────────────────────────────────────

SUBSCRIPTION_ID  = os.environ.get("AZURE_SUBSCRIPTION_ID", "")
RESOURCE_GROUP   = os.environ.get("AZURE_RESOURCE_GROUP", "")
APP_INSIGHTS     = os.environ.get("APPLICATION_INSIGHTS_NAME", "")

EXPECTED_RETENTION_DAYS = int(os.environ.get("EXPECTED_RETENTION_DAYS", "30"))
EXPECTED_SAMPLING_RATIO = float(os.environ.get("EXPECTED_SAMPLING_RATIO", "0.1"))

# Roles that grant read access to trace content on an App Insights resource.
TRACE_READING_ROLES = {
    "Log Analytics Reader",
    "Monitoring Reader",
    "Reader",
    "Contributor",
    "Owner",
}

PASS, FAIL, WARN, SKIP, MANUAL = "PASS", "FAIL", "WARN", "SKIP", "MANUAL"


def _one_line(exc: Exception, limit: int = 110) -> str:
    """Azure errors are multi-line; the report reads better with one."""
    text = " ".join(str(exc).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class Result:
    def __init__(self, item: str, status: str, detail: str, fix: str = ""):
        self.item, self.status, self.detail, self.fix = item, status, detail, fix

    def as_dict(self) -> dict:
        return {"item": self.item, "status": self.status, "detail": self.detail, "fix": self.fix}


# ── 1. Content recording (local config) ───────────────────────────────────────

def check_content_recording() -> Result:
    from tracing_config import content_recording_enabled

    if content_recording_enabled():
        return Result(
            "Content recording",
            FAIL,
            "ENABLE_CONTENT_RECORDING is true — prompts and user messages will be logged",
            "Set ENABLE_CONTENT_RECORDING=false for production deployments",
        )
    return Result("Content recording", PASS, "disabled (production default)")


# ── 2 & 3. App Insights sampling + retention ──────────────────────────────────

def _app_insights_component(credential):
    from azure.mgmt.applicationinsights import ApplicationInsightsManagementClient

    client = ApplicationInsightsManagementClient(credential, SUBSCRIPTION_ID)
    return client.components.get(RESOURCE_GROUP, APP_INSIGHTS)


def check_sampling(component) -> Result:
    from tracing_config import sampling_ratio

    local = sampling_ratio()

    # Ingestion sampling on the resource. 100 means "keep everything".
    ingestion = getattr(component, "sampling_percentage", None)
    ingestion_note = "not set (100%)" if ingestion in (None, 100) else f"{ingestion}%"

    if local >= 1.0:
        return Result(
            "Sampling",
            FAIL,
            f"app exports 100% of traces (OTEL_TRACE_SAMPLING_RATIO unset or 1.0); "
            f"ingestion sampling: {ingestion_note}",
            f"Set OTEL_TRACE_SAMPLING_RATIO={EXPECTED_SAMPLING_RATIO} — sample in the app, "
            "not at ingestion (ingestion sampling causes broken traces)",
        )

    if local > EXPECTED_SAMPLING_RATIO:
        return Result(
            "Sampling",
            WARN,
            f"app sampling {local:.0%} is above target {EXPECTED_SAMPLING_RATIO:.0%}; "
            f"ingestion sampling: {ingestion_note}",
            "Lower OTEL_TRACE_SAMPLING_RATIO if trace volume is driving cost",
        )

    return Result("Sampling", PASS, f"app exports {local:.0%} of traces; ingestion sampling: {ingestion_note}")


def check_retention(component) -> Result:
    days = getattr(component, "retention_in_days", None)

    if days is None:
        return Result("Retention", SKIP, "could not read retention_in_days from the resource")

    if days > EXPECTED_RETENTION_DAYS:
        return Result(
            "Retention",
            WARN,
            f"{days} days (target {EXPECTED_RETENTION_DAYS})",
            f"App Insights → Usage and estimated costs → Data retention → {EXPECTED_RETENTION_DAYS} days",
        )

    return Result("Retention", PASS, f"{days} days")


# ── 4. RBAC ───────────────────────────────────────────────────────────────────

def check_rbac(credential, component) -> Result:
    from azure.mgmt.authorization import AuthorizationManagementClient

    client = AuthorizationManagementClient(credential, SUBSCRIPTION_ID)
    scope = component.id

    role_names: dict[str, str] = {}
    holders: list[str] = []

    for assignment in client.role_assignments.list_for_scope(scope):
        role_id = assignment.role_definition_id
        if role_id not in role_names:
            try:
                role_names[role_id] = client.role_definitions.get_by_id(role_id).role_name
            except Exception:
                role_names[role_id] = role_id.rsplit("/", 1)[-1]

        name = role_names[role_id]
        if name in TRACE_READING_ROLES:
            holders.append(name)

    if not holders:
        return Result("RBAC", PASS, "no direct trace-reading role assignments at this scope")

    summary = ", ".join(f"{n}×{holders.count(n)}" for n in sorted(set(holders)))
    return Result(
        "RBAC",
        WARN,
        f"{len(holders)} principal(s) can read trace content — {summary}",
        "Review these assignments. Anyone with these roles can read recorded prompt "
        "and response content in Log Analytics.",
    )


# ── 5. Content safety ─────────────────────────────────────────────────────────

def check_content_safety() -> Result:
    return Result(
        "Content safety",
        MANUAL,
        "not readable via this SDK path — verify by hand",
        "Foundry portal → your project → Guardrails + controls. Required for any "
        "public-facing agent.",
    )


# ── 6. max_output_tokens ──────────────────────────────────────────────────────

def check_max_output_tokens() -> Result:
    from tracing_config import max_output_tokens

    cap = max_output_tokens()
    if not cap:
        return Result(
            "max_output_tokens",
            FAIL,
            "no cap configured — a runaway loop can generate unbounded tokens",
            "Set MAX_OUTPUT_TOKENS and pass it to responses.create() "
            "(it is a per-request param, not an agent-definition field)",
        )

    if cap > 4096:
        return Result("max_output_tokens", WARN, f"{cap} — high for most agents",
                      "Consider a lower cap unless you genuinely need long outputs")

    return Result("max_output_tokens", PASS, f"{cap} tokens")


# ── Runner ────────────────────────────────────────────────────────────────────

def run_audit() -> list[Result]:
    results = [check_content_recording()]

    missing = [n for n, v in [
        ("AZURE_SUBSCRIPTION_ID", SUBSCRIPTION_ID),
        ("AZURE_RESOURCE_GROUP", RESOURCE_GROUP),
        ("APPLICATION_INSIGHTS_NAME", APP_INSIGHTS),
    ] if not v]

    if missing:
        reason = f"set {', '.join(missing)} in .env to enable"
        results += [
            Result("Sampling", SKIP, reason),
            Result("Retention", SKIP, reason),
            Result("RBAC", SKIP, reason),
        ]
    else:
        try:
            from azure.identity import DefaultAzureCredential

            credential = DefaultAzureCredential()
            component  = _app_insights_component(credential)

            results.append(check_sampling(component))
            results.append(check_retention(component))

            try:
                results.append(check_rbac(credential, component))
            except Exception as exc:
                results.append(Result("RBAC", SKIP, f"could not list role assignments: {_one_line(exc)}"))

        except Exception as exc:
            reason = f"Azure lookup failed: {_one_line(exc)}"
            results += [
                Result("Sampling", SKIP, reason),
                Result("Retention", SKIP, reason),
                Result("RBAC", SKIP, reason),
            ]

    results.append(check_content_safety())
    results.append(check_max_output_tokens())
    return results


_ICONS = {PASS: "PASS  ", FAIL: "FAIL  ", WARN: "WARN  ", SKIP: "SKIP  ", MANUAL: "MANUAL"}


def print_report(results: list[Result]) -> None:
    print("\n=== Foundry production pre-launch audit ===\n")

    for r in results:
        print(f"  [{_ICONS[r.status]}] {r.item:<20} {r.detail}")
        if r.fix and r.status in {FAIL, WARN, MANUAL}:
            print(f"            → {r.fix}")

    counts = {s: sum(1 for r in results if r.status == s) for s in (PASS, FAIL, WARN, SKIP, MANUAL)}
    print(
        f"\n  {counts[PASS]} passed · {counts[FAIL]} failed · {counts[WARN]} warnings · "
        f"{counts[MANUAL]} manual · {counts[SKIP]} skipped\n"
    )

    if counts[FAIL]:
        print("  Not ready for production — fix the failures above.\n")
    elif counts[WARN] or counts[MANUAL]:
        print("  No blockers, but review the warnings and manual items.\n")
    else:
        print("  All automated checks passed.\n")


def main():
    results = run_audit()

    if "--json" in sys.argv:
        print(json.dumps([r.as_dict() for r in results], indent=2))
    else:
        print_report(results)

    # Non-zero exit on failure so this can gate a deploy pipeline.
    sys.exit(1 if any(r.status == FAIL for r in results) else 0)


if __name__ == "__main__":
    main()
