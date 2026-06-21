"""Shared LLM helpers — Claude when configured."""
from __future__ import annotations

import json
import os
from typing import Any

DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"


def clean_json(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 1)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]
    return raw.strip()


def claude_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def claude_model() -> str:
    return os.environ.get("CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL)


def list_extractors() -> list[str]:
    out: list[str] = []
    if claude_configured():
        out.append("claude")
    out.append("local")
    return out


def chat_claude(system: str, user: str, *, max_tokens: int = 1000) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=20)
    msg = client.messages.create(
        model=claude_model(),
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text


def chat_json(
    system: str,
    user: str,
    *,
    max_tokens: int = 1000,
) -> tuple[dict[str, Any], str, str]:
    """Try Claude. Returns (parsed JSON, source, model name)."""
    if not claude_configured():
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    try:
        raw = chat_claude(system, user, max_tokens=max_tokens)
        return json.loads(clean_json(raw)), "claude", claude_model()
    except Exception as exc:
        raise RuntimeError(f"claude: {exc}") from exc
