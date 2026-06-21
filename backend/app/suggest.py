"""Milestone 2 — on-demand guidance.

The key design rule from the team: this NEVER nags. It only runs when the user
taps a bubble and asks "what should I do?" The agent then:
  1. looks at the bubble and its neighbors in the current map,
  2. pulls semantically related moments from past sessions (Redis),
  3. asks Claude for ONE concrete, grounded next step.

"Grounded" matters: a suggestion should reference what's actually on the map or
in history ("you have Friday open in your schedule bubble — that's a real study
block") rather than generic advice ("try to manage your time").
"""
import os
from anthropic import Anthropic
from .memory import search_past, get_session
from .schemas import Suggestion

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

SYSTEM = """You are a calm, practical thinking partner inside a thought-mapping \
app. The person tapped one bubble and asked for guidance.

You get: the bubble they tapped, the other bubbles currently on their map, and \
related moments from their past sessions.

Give exactly ONE next step. Rules:
- Ground it in what's actually present. Reference a real task, a real open day, \
a real pattern from their past. Never generic ("manage your stress").
- If it's an emotion bubble, you are NOT a therapist. Offer a small, doable \
action or a reframe, and if their past sessions show a real pattern, name it \
gently ("this is the third week the same friend group has come up").
- Two to four sentences. Warm, not clinical. No lists.
- If past context genuinely helps, lean on it; if not, work from the current map."""


def _format_map(session: dict, tapped_name: str) -> str:
    """Format the current session's topics as the 'map' context for Claude.
    session is an extraction dict: {title, summary, topics[], concerns[], ...}
    """
    lines = []
    for tp in session.get("topics", []):
        mark = "→ TAPPED: " if tp.get("name") == tapped_name else "  "
        contrib = tp.get("contribution", "")
        excerpts = tp.get("excerpts", [])
        line = f"{mark}[{tp.get('kind', 'topic')}] {tp['name']}"
        if contrib:
            line += f" — {contrib}"
        if excerpts:
            line += f" (e.g. \"{excerpts[0]}\")"
        lines.append(line)
    return "\n".join(lines) or "(no topics on map)"


def suggest_for_node(node_id: str, session_id: str, fallback=None) -> Suggestion:
    """node_id is a topic name (e.g. 'calc'). Session is extraction-dict shape."""
    session = get_session(session_id)
    if not session and fallback is not None:
        session = fallback if isinstance(fallback, dict) else fallback.model_dump()
    if not session:
        return Suggestion(node_id=node_id, text="I couldn't find that session.")

    # node_id is the topic name; find it in the topics list
    topics = session.get("topics", [])
    tapped = next((tp for tp in topics if tp.get("name") == node_id), None)
    if not tapped:
        return Suggestion(node_id=node_id, text="I couldn't find that thought.")

    # Build a rich search query from the topic's contribution + verbatim excerpts
    query_parts = [tapped["name"]]
    if tapped.get("contribution"):
        query_parts.append(tapped["contribution"])
    query_parts.extend(tapped.get("excerpts", [])[:2])
    query = ". ".join(query_parts)

    past = search_past(query, k=4, exclude_session=session_id)
    past_block = (
        "\n".join(
            f"- [{p['kind']}] {p['name']}: {p['contribution']}"
            for p in past
        )
        if past else "(no closely related past sessions)"
    )

    user = f"""CURRENT MAP:
{_format_map(session, node_id)}

RELATED PAST MOMENTS:
{past_block}

Give one grounded next step for the tapped bubble: "{node_id}"."""

    msg = client.messages.create(
        model=MODEL, max_tokens=400, system=SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    return Suggestion(
        node_id=node_id,
        text=msg.content[0].text.strip(),
        drawn_from=[p["name"] for p in past],
    )
