import re
from pydantic import BaseModel, Field, field_validator

class MermaidOutput(BaseModel):
    mermaid_code: str = Field(
        description="The raw Mermaid flowchart TD code."
    )

    @field_validator('mermaid_code')
    def validate_mermaid_syntax(cls, v):
        v = v.strip()
        
        if not v.startswith("flowchart TD"):
            raise ValueError("Diagram MUST start with 'flowchart TD'")
        
        if "```" in v:
            raise ValueError("Do NOT wrap the output in markdown backticks (```). Return ONLY the raw code.")
        
        # 1. Catch unquoted special characters in node definitions (e.g., node_name{.cross})
        if re.search(r'\{[^\"]*[\.\(\)\[\]][^\"]*\}', v):
            raise ValueError(
                "SYNTAX ERROR: Node labels with dots or parentheses MUST be wrapped in quotes. "
                "Change node{.cross} to node{\".cross\"}."
            )
            
        # 2. Catch unquoted special characters in edge labels (e.g., A -->|text()| B)
        if re.search(r'-->\|[^\"]*[\(\)\[\]][^\"]*\|', v):
            raise ValueError(
                "SYNTAX ERROR: Edge labels with parentheses or brackets MUST be wrapped in quotes. "
                "Change -->|text(args)| to -->|\"text(args)\"|."
            )

        return v