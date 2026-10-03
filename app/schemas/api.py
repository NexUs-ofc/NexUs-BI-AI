"""API contracts (what goes in and out of the endpoints)."""
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, examples=["Qual região vendeu mais?"])
    session_id: str | None = Field(
        default=None,
        description="Identifies the conversation. If empty, the API creates one and returns it.",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    debug: bool = Field(default=False, description="If true, returns the internal steps (route, judge, guardrails).")


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    route: str = Field(..., examples=["analyst"])
    steps: list[str] | None = None


class SessionClosedResponse(BaseModel):
    session_id: str
    closed: bool
