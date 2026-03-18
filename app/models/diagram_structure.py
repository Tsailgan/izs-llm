from pydantic import BaseModel, Field


class MermaidOutput(BaseModel):
    mermaid_code: str = Field(
        description="The raw Mermaid flowchart TD code."
    )