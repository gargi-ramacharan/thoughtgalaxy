# schemas.py — the ONE true data contract.
# Person A's classify.py must OUTPUT a GalaxyState. Your agents CONSUME it.
# Both backend/ and agents/ import from this file so nobody drifts.

from pydantic import BaseModel, Field
from typing import List, Literal


class Topic(BaseModel):
    name: str
    status: Literal["new", "ongoing", "done"] = "new"
    kind: Literal["task", "emotion", "idea", "place", "person", "other"] = "other"
    connects: List[str] = Field(default_factory=list)  # names of related topics


class ActionItem(BaseModel):
    text: str
    topic: str   # which topic.name this belongs to


class Event(BaseModel):
    title: str
    date: str    # keep it loose for the hackathon ("Sunday", "next week", etc.)
    topic: str


class GalaxyState(BaseModel):
    summary: str = ""
    topics: List[Topic] = Field(default_factory=list)
    concerns: List[str] = Field(default_factory=list)
    actionItems: List[ActionItem] = Field(default_factory=list)
    events: List[Event] = Field(default_factory=list)
