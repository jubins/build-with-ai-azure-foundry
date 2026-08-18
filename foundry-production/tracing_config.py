"""
File 1 — Production tracing configuration
==========================================
The two settings that decide what ends up in Application Insights:

  content recording  — whether prompts, user messages, and tool args are logged
  sampling ratio     — what fraction of traces are exported at all

Content recording is the one with real consequences. With it ON you get full
prompt and response text in your traces, which is exactly what you want when
debugging and exactly what you don't want sitting in Log Analytics with real
user data in it. Anyone with Log Analytics Reader can read all of it.

So it's driven by an env var that defaults to OFF, and it warns loudly when
you turn it on. There's no code path here that hardcodes it to True.

Run:
    python tracing_config.py             # show the resolved config
    ENABLE_CONTENT_RECORDING=true python tracing_config.py
"""

from dotenv import load_dotenv
load_dotenv()

import os

# Foundry/OpenAI instrumentation reads this env var to decide whether message
# content is attached to spans. Set it before the instrumentation initialises.
CONTENT_RECORDING_ENV = "AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED"


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def content_recording_enabled() -> bool:
    """Production default is False. You must opt in explicitly."""
    return _as_bool(os.environ.get("ENABLE_CONTENT_RECORDING"), default=False)


def sampling_ratio() -> float:
    """
    Fraction of traces exported, 0.0–1.0.

    Note the default: the Azure Monitor OpenTelemetry distro ships with
    sampling_ratio=1.0, i.e. 100% of traces are exported. That's fine in dev and
    expensive under production traffic, so set this explicitly.
    """
    raw = os.environ.get("OTEL_TRACE_SAMPLING_RATIO", "1.0")
    try:
        ratio = float(raw)
    except ValueError:
        raise SystemExit(f"OTEL_TRACE_SAMPLING_RATIO must be a number, got {raw!r}")

    if not 0.0 <= ratio <= 1.0:
        raise SystemExit(f"OTEL_TRACE_SAMPLING_RATIO must be between 0 and 1, got {ratio}")
    return ratio


def max_output_tokens() -> int | None:
    """
    Hard cap on generated tokens per response.

    This is a *per-request* parameter — see agent_guardrails.py. There is no
    field for it on the agent definition itself, so it cannot be set once and
    forgotten; every call site has to pass it.
    """
    raw = os.environ.get("MAX_OUTPUT_TOKENS")
    return int(raw) if raw else None


def configure_tracing(connection_string: str | None = None) -> None:
    """
    Wire up Azure Monitor with production-safe defaults.

    Call this once at process start, before creating any Foundry clients.
    """
    recording = content_recording_enabled()
    ratio     = sampling_ratio()

    # Must be set before instrumentation reads it.
    os.environ[CONTENT_RECORDING_ENV] = "true" if recording else "false"

    if recording:
        print(
            "WARNING: content recording is ON. Prompts, user messages, and tool\n"
            "         arguments will be written to Application Insights. Use this\n"
            "         only for a scoped debugging session on non-PII data."
        )

    conn = connection_string or os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not conn:
        print("APPLICATIONINSIGHTS_CONNECTION_STRING not set — tracing not configured.")
        return

    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor(
        connection_string=conn,
        sampling_ratio=ratio,
    )
    print(f"Azure Monitor configured — sampling {ratio:.0%}, content recording {'ON' if recording else 'OFF'}")


def describe() -> dict:
    """The resolved settings, for printing or asserting in tests."""
    return {
        "content_recording": content_recording_enabled(),
        "sampling_ratio":    sampling_ratio(),
        "max_output_tokens": max_output_tokens(),
    }


def main():
    cfg = describe()

    print("\n=== Resolved tracing configuration ===\n")
    print(f"  content recording : {'ON  ← PII risk' if cfg['content_recording'] else 'OFF (production default)'}")
    print(f"  sampling ratio    : {cfg['sampling_ratio']:.0%}")
    print(f"  max output tokens : {cfg['max_output_tokens'] or 'unset ← no cost guardrail'}")

    print("\nWhat gets logged either way:")
    print("  always  — run/thread IDs, agent + model name, tool names, token counts,")
    print("            span duration, status, finish reason")
    print("  only if content recording is ON — system prompt, user messages, model")
    print("            responses, tool arguments, tool results")
    print("  never   — API keys and secrets, payment data, content-safety-blocked text\n")

    if cfg["content_recording"]:
        print("This configuration is NOT safe for production traffic.\n")


if __name__ == "__main__":
    main()
