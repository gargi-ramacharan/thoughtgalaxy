"""Milestone 1 — Claude turns a raw transcript into bubble nodes.

This is the brain of the map. A messy 2-minute ramble goes in; a clean,
connected set of typed nodes comes out. The whole quality of the demo
lives in this prompt, so it's worth tuning carefully.
"""
import json
import os
import uuid
from anthropic import Anthropic
from .schemas import Node, NodeType
from .observability import log_classification

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

SYSTEM = """You map a person's spoken stream-of-consciousness into a small \
constellation of distinct thoughts.

You will receive a raw voice transcript of someone talking through their day. \
Break it into 3-7 DISTINCT nodes. Do not over-split: one coherent worry is one \
node even if they circled it three times. Do not merge unrelated things.

For each node decide a type:
- "task": a concrete thing they need to do ("submit CS homework", "email professor")
- "emotion": a feeling or interpersonal worry ("stressed about midterm", "friend drama")
- "idea": a want, plan, or curiosity, not urgent ("learn guitar", "start a side project")

Then find connections: if two nodes are causally or thematically linked (the \
midterm stress is *because of* the homework pileup), list the connection. \
Connections are what make the map feel insightful rather than a flat list.

Assign priority 0-3 (3 = urgent/time-sensitive, 0 = no time pressure).

Return ONLY valid JSON, no markdown, no preamble:
{
  "nodes": [
    {
      "ref": "n1",
      "text": "short 3-8 word label",
      "type": "task|emotion|idea",
      "detail": "the fuller thought in their words",
      "priority": 0,
      "connects_to": ["n2"]
    }
  ]
}
Use the "ref" field for connections (connects_to references other refs)."""


def classify_transcript(transcript: str) -> list[Node]:
    """Transcript → list of Node. Logs the decision to Arize."""
    msg = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=SYSTEM,
        messages=[{"role": "user", "content": transcript}],
    )
    raw = msg.content[0].text.strip()
    # Claude is told no markdown, but strip fences defensively
    if raw.startswith("```"):
        raw = raw.split("```")[1].replace("json", "", 1).strip()

    data = json.loads(raw)

    # Map model refs → real uuids so connections survive
    ref_to_id: dict[str, str] = {}
    for n in data["nodes"]:
        ref_to_id[n["ref"]] = str(uuid.uuid4())

    nodes: list[Node] = []
    for n in data["nodes"]:
        nodes.append(
            Node(
                id=ref_to_id[n["ref"]],
                text=n["text"],
                type=NodeType(n["type"]),
                detail=n.get("detail", ""),
                priority=n.get("priority", 0),
                connections=[
                    ref_to_id[r] for r in n.get("connects_to", []) if r in ref_to_id
                ],
            )
        )

    log_classification(transcript=transcript, nodes=nodes)
    return nodes
