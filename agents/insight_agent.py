"""Milestone 2 — Insight Agent (Fetch.ai uAgent).

This is your first real agent and the easiest to demo. It takes a bubble the
user tapped, reaches into past-session memory, and returns one grounded
suggestion. Registering it on Agentverse is what makes the Fetch.ai prize
real — the judges want to see an actual discoverable agent, not just an API
call dressed up as one.

Run:  python agents/insight_agent.py
It prints its address on startup — copy that into your .env as
INSIGHT_AGENT_ADDRESS so the backend can reach it.
"""
import os
from uagents import Agent, Context, Model


# ─── message contract ───
class SuggestQuery(Model):
    node_text: str
    node_detail: str
    map_summary: str       # the rest of the current bubbles, as text
    past_context: str      # related past moments, pre-fetched by backend


class SuggestReply(Model):
    suggestion: str
    used_past: bool


insight_agent = Agent(
    name="thought_galaxy_insight",
    seed=os.environ.get("INSIGHT_AGENT_SEED", "insight-dev-seed"),
    port=8001,
    endpoint=["http://127.0.0.1:8001/submit"],
)


@insight_agent.on_event("startup")
async def announce(ctx: Context):
    ctx.logger.info(f"Insight Agent address: {insight_agent.address}")


@insight_agent.on_message(model=SuggestQuery, replies=SuggestReply)
async def on_query(ctx: Context, sender: str, msg: SuggestQuery):
    """Ask Claude for one grounded next step, given map + past context."""
    from anthropic import Anthropic

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

    prompt = f"""The person tapped this bubble and wants one concrete next step.

TAPPED: {msg.node_text} — {msg.node_detail}

REST OF THEIR MAP:
{msg.map_summary}

RELATED PAST MOMENTS:
{msg.past_context}

Give ONE grounded next step in 2-4 warm sentences. Reference something real \
from the map or past. Not a therapist; offer a small doable action or gentle \
reframe. No lists."""

    resp = client.messages.create(
        model=model, max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    await ctx.send(
        sender,
        SuggestReply(
            suggestion=resp.content[0].text.strip(),
            used_past=bool(msg.past_context.strip()),
        ),
    )


if __name__ == "__main__":
    insight_agent.run()
