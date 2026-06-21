"""Milestone 1 — Arize (what the AI is doing) + Sentry (what broke).

Both are deliberately low-lift. Sentry is three lines. Arize logs one record
per classification so you can show judges a live dashboard of the model's
decisions — that visible evidence is exactly what their prize asks for.

Everything here fails soft: if a key is missing, the app still runs. You do
NOT want your demo crashing because Arize hiccuped.
"""
import os
import time
import sentry_sdk

# ─── Sentry ───
_sentry_dsn = os.environ.get("SENTRY_DSN")
if _sentry_dsn:
    sentry_sdk.init(dsn=_sentry_dsn, traces_sample_rate=1.0)


# ─── Arize ───
_arize_client = None
try:
    from arize.pandas.logger import Client as ArizeClient

    _space = os.environ.get("ARIZE_SPACE_ID")
    _key = os.environ.get("ARIZE_API_KEY")
    if _space and _key:
        _arize_client = ArizeClient(space_id=_space, api_key=_key)
except Exception:  # arize not installed or misconfigured — degrade gracefully
    _arize_client = None


def log_classification(transcript: str, nodes) -> None:
    """Record one classification event to Arize.

    We log the input length, how many nodes came out, and the type mix. Over a
    session this becomes a dashboard you can point a judge at: "here's every
    decision the model made and how the distribution shifted."
    """
    if _arize_client is None:
        return
    try:
        import pandas as pd

        type_counts = {"task": 0, "emotion": 0, "idea": 0}
        for n in nodes:
            type_counts[n.type.value] += 1

        df = pd.DataFrame(
            [
                {
                    "prediction_id": str(time.time_ns()),
                    "transcript_chars": len(transcript),
                    "node_count": len(nodes),
                    "tasks": type_counts["task"],
                    "emotions": type_counts["emotion"],
                    "ideas": type_counts["idea"],
                    "ts": int(time.time()),
                }
            ]
        )
        # Schema kept minimal on purpose; expand if you have time.
        from arize.utils.types import Schema, Environments, ModelTypes

        _arize_client.log(
            dataframe=df,
            model_id="thought-galaxy-classifier",
            model_version="m1",
            model_type=ModelTypes.GENERATIVE_LLM,
            environment=Environments.PRODUCTION,
            schema=Schema(
                prediction_id_column_name="prediction_id",
                timestamp_column_name="ts",
            ),
        )
    except Exception as e:  # never let logging kill a request
        if _sentry_dsn:
            sentry_sdk.capture_exception(e)
