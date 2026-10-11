"""API contracts (what goes in and out of the endpoints)."""
from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    # Example shown in /docs. It has no session_id on purpose: a fixed example id would make every
    # request sent from Swagger share the same conversation history.
    model_config = ConfigDict(json_schema_extra={"examples": [{"question": "Qual região vendeu mais?", "debug": False}]})

    question: str = Field(..., min_length=1, max_length=2000, examples=["Qual região vendeu mais?"])
    session_id: str | None = Field(
        default=None,
        description="Identifies the conversation. Leave empty to start a new one; send the returned id to continue it.",
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


class CurrentUser(BaseModel):
    """Who is calling: profile id from the JWT ("sub") and company id confirmed in PostgreSQL."""

    profile_id: int
    company_id: int
