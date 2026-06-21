"""Shared data shapes used across the backend.

A "node" is one bubble on the galaxy. A "session" is one recording.
Keeping these in one place means the frontend, classifier, and agents
all agree on the contract.
"""
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field


class NodeType(str, Enum):
    TASK = "task"        # something to do  → blue, executable
    EMOTION = "emotion"  # a feeling        → warm, reflectable
    IDEA = "idea"        # future intent    → purple, parked


class Node(BaseModel):
    id: str
    text: str = Field(description="short label, ~3-8 words, the bubble caption")
    type: NodeType
    detail: str = Field(default="", description="the fuller thought this came from")
    # ids of other nodes this connects to (shared theme / cause-effect)
    connections: list[str] = Field(default_factory=list)
    priority: int = Field(default=0, ge=0, le=3, description="0 none .. 3 urgent")
    # M3: filled once an agent acts on a task node
    status: Literal["open", "running", "done", "failed"] = "open"


class Session(BaseModel):
    id: str
    created_at: str
    transcript: str
    nodes: list[Node]


class SuggestRequest(BaseModel):
    """Milestone 2 — user taps a bubble and asks for guidance."""
    node_id: str
    session_id: str
    aliases: list[str] = Field(default_factory=list,
        description="prior names for this bubble (rename chain), used to match the saved topic name")


class Suggestion(BaseModel):
    node_id: str
    text: str = Field(description="grounded, concrete next step")
    drawn_from: list[str] = Field(
        default_factory=list,
        description="snippets of past sessions this drew on, for transparency",
    )


class ExecuteRequest(BaseModel):
    """Milestone 3 — run an agent on a task node."""
    node_id: str
    session_id: str
