from pydantic import BaseModel, Field


class Requirement(BaseModel):
    """A single requirement extracted from a specification document."""

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source: str
    page: int = Field(ge=1)
