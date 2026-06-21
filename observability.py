# observability.py — call init_observability() ONCE at backend startup
# (top of main.py, before anything else runs).
#
#   Arize  -> a trace of every Claude classification decision  (Arize prize)
#   Sentry -> catches every crash across the whole stack       (Sentry prize)
#
# IMPORTANT: Arize auto-tracing only captures calls made through the official
# `anthropic` Python SDK. So classify.py / suggest.py MUST use
# anthropic.Anthropic().messages.create(...) — NOT raw requests/httpx — or you'll
# get zero traces and waste an hour wondering why.

import os


def init_observability():
    # --- Sentry: error monitoring ------------------------------------------
    dsn = os.getenv("SENTRY_DSN")
    if dsn:
        import sentry_sdk
        sentry_sdk.init(dsn=dsn, traces_sample_rate=1.0, send_default_pii=False)
        print("[observability] Sentry on")

    # --- Arize: LLM tracing ------------------------------------------------
    space_id = os.getenv("ARIZE_SPACE_ID")
    api_key = os.getenv("ARIZE_API_KEY")
    if space_id and api_key:
        from arize.otel import register
        from openinference.instrumentation.anthropic import AnthropicInstrumentor
        tracer_provider = register(
            space_id=space_id,
            api_key=api_key,
            project_name="thought-galaxy",
        )
        AnthropicInstrumentor().instrument(tracer_provider=tracer_provider)
        print("[observability] Arize on — every Claude call is now traced")

    # --- Local, no-key alternative -----------------------------------------
    # Run `phoenix serve` in another terminal, then use this instead of the
    # Arize block above (same AnthropicInstrumentor line):
    #
    #   from phoenix.otel import register as px_register
    #   from openinference.instrumentation.anthropic import AnthropicInstrumentor
    #   tp = px_register(project_name="thought-galaxy", auto_instrument=True)
    #   AnthropicInstrumentor().instrument(tracer_provider=tp)
