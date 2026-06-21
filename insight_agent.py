# insight_agent.py — Milestone 2. Tap a bubble -> ONE grounded next step.
#
# Run it:   python insight_agent.py        (listens on :8001)
# Backend calls it:
#   POST http://localhost:8001/insight   {"topic": "the trip", "session_id": "abc"}
#   -> {"suggestion": "...", "grounded_in": ["...", "..."]}
#
# Using uAgents' on_rest_post keeps this decoupled from Person A's FastAPI
# backend — the backend just POSTs to it like any other service. No agent-address
# wrangling needed for the demo.

import os
import sys
import anthropic
from uagents import Agent, Context, Model

# reuse your own memory.py (it lives in backend/app/). Simplest hackathon path:
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend", "app"))
from memory import search  # noqa: E402


class InsightRequest(Model):
    topic: str
    session_id: str = ""


class InsightResponse(Model):
    suggestion: str
    grounded_in: list[str]


agent = Agent(
    name="insight",
    seed="thought-galaxy-insight-seed-change-me",
    port=8001,
    endpoint=["http://localhost:8001/submit"],
)

_claude = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY


@agent.on_rest_post("/insight", InsightRequest, InsightResponse)
async def give_insight(ctx: Context, req: InsightRequest) -> InsightResponse:
    # 1. recall related moments from past sessions (vector search in Redis)
    hits = search(req.topic, k=5)
    context = [h["text"] for h in hits]

    # 2. ask Claude for ONE concrete next step, grounded in what they actually said
    if context:
        body = "Things they've said before:\n- " + "\n- ".join(context)
    else:
        body = "You don't have past context yet — give a gentle, concrete first step."

    prompt = (
        f"The user is thinking about: {req.topic}\n\n{body}\n\n"
        "Suggest ONE concrete next step, grounded in what they've said. "
        "One or two sentences. Specific, warm, no fluff."
    )

    msg = _claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return InsightResponse(suggestion=msg.content[0].text, grounded_in=context)


if __name__ == "__main__":
    ctx_note = "insight agent up on :8001  ->  POST /insight"
    print(ctx_note)
    agent.run()
