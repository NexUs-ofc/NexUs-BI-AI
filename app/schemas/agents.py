"""Pydantic schemas exchanged inside the chat."""
from pydantic import BaseModel, Field


class SpecialistAnswer(BaseModel):
    answer: str
    context: str = Field(default="", description="What the tools returned (the number check compares against it)")
    tool_calls: list[str] = Field(default_factory=list, description="Tools called by the agent (for debug)")
    route: str = Field(default="faq", description="faq | analyst, from the tools used")


class GuardrailResult(BaseModel):
    allowed: bool
    reason: str = ""
    text: str = ""


class Result(BaseModel):
    answer: str
    route: str = ""
    steps: list[str] = Field(default_factory=list, description="Debug trace (debug=true)")
