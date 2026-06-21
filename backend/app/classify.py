"""Milestone 1 — transcript → bubble nodes.

Primary: Claude (when ANTHROPIC_API_KEY is set).
Fallback: rule-based sentence splitter when Claude fails.
"""
from __future__ import annotations

import re
import uuid

from .llm import chat_json
from .observability import log_classification
from .schemas import Node, NodeType

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

TASK_HINTS = (
    "need to", "have to", "must", "should", "submit", "email", "call",
    "finish", "complete", "pack", "study", "deadline", "due", "meeting",
)
EMOTION_HINTS = (
    "stressed", "stress", "worried", "worry", "anxious", "anxiety",
    "overwhelmed", "tired", "exhausted", "nervous", "scared", "upset",
    "frustrated", "sad", "lonely", "angry",
)


def _nodes_from_data(data: dict) -> list[Node]:
    ref_to_id: dict[str, str] = {}
    for n in data["nodes"]:
        ref_to_id[n["ref"]] = str(uuid.uuid4())

    nodes: list[Node] = []
    for n in data["nodes"]:
        ntype = n["type"]
        if ntype not in ("task", "emotion", "idea"):
            ntype = "idea"
        nodes.append(
            Node(
                id=ref_to_id[n["ref"]],
                text=n["text"],
                type=NodeType(ntype),
                detail=n.get("detail", ""),
                priority=min(3, max(0, int(n.get("priority", 0)))),
                connections=[
                    ref_to_id[r] for r in n.get("connects_to", []) if r in ref_to_id
                ],
            )
        )
    return nodes


def classify_local(transcript: str) -> list[Node]:
    """Rule-based fallback — split into sentences and guess node types."""
    sentences = [
        s.strip()
        for s in re.split(r"[.!?;\n]+", transcript)
        if len(s.strip()) > 12
    ]
    if not sentences:
        text = transcript.strip()
        sentences = [text] if text else ["(empty transcript)"]

    chunks = sentences[:7]
    ref_to_id = {f"n{i + 1}": str(uuid.uuid4()) for i in range(len(chunks))}
    nodes: list[Node] = []

    for i, chunk in enumerate(chunks):
        lower = chunk.lower()
        if any(h in lower for h in TASK_HINTS):
            ntype = NodeType.TASK
            priority = 2 if "deadline" in lower or "due" in lower else 1
        elif any(h in lower for h in EMOTION_HINTS):
            ntype = NodeType.EMOTION
            priority = 1
        else:
            ntype = NodeType.IDEA
            priority = 0

        words = chunk.split()
        label = " ".join(words[:8])
        if len(words) > 8:
            label += "…"

        ref = f"n{i + 1}"
        connects: list[str] = []
        if i > 0:
            connects.append(ref_to_id[f"n{i}"])
        if i + 1 < len(chunks):
            connects.append(ref_to_id[f"n{i + 2}"])

        nodes.append(
            Node(
                id=ref_to_id[ref],
                text=label,
                type=ntype,
                detail=chunk,
                priority=priority,
                connections=[c for c in connects if c != ref_to_id[ref]],
            )
        )

    return nodes


def classify_transcript(transcript: str) -> list[Node]:
    """Transcript → list of Node. Claude → local rules."""
    try:
        data, _source, _model = chat_json(SYSTEM, transcript, max_tokens=1500)
        nodes = _nodes_from_data(data)
    except Exception:
        nodes = classify_local(transcript)

    log_classification(transcript=transcript, nodes=nodes)
    return nodes
