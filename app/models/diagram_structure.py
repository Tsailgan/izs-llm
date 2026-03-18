from pydantic import BaseModel, Field, field_validator
import re

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
            raise ValueError("Do NOT wrap the output in markdown backticks. Return ONLY the raw code.")
            
        # 1. Catch unquoted special characters in node labels
        if re.search(r'\{[^"]*[\.\(\)\[\]][^"]*\}', v):
            raise ValueError(
                "SYNTAX ERROR. Node labels with dots or parentheses MUST be wrapped in quotes. "
                "Change node{.cross} to node{\".cross\"}."
            )
            
        # 2. Catch unquoted special characters in edge labels
        if re.search(r'-->\|[^"]*[\(\)\[\]\.\{][^"]*\|', v):
            raise ValueError(
                "SYNTAX ERROR. Edge labels with parentheses or dots MUST be wrapped in quotes. "
                "Change -->|text(args)| to -->|\"text(args)\"|."
            )

        # 3. Catch mixed parentheses and curly braces for Rhombus shapes
        if re.search(r'\(\s*\{[^\}]+\}\s*\)', v) or re.search(r'\{\s*\([^\)]+\)\s*\}', v):
            raise ValueError(
                "SYNTAX ERROR. Do not mix parentheses and curly braces for Rhombus shapes. "
                "Use exactly node_id{\"label\"}."
            )

        # 4. Catch extra brackets for Stadium shapes
        if re.search(r'\(\[\s*\([^\)]+\)\s*\]\)', v):
            raise ValueError(
                "SYNTAX ERROR. Too many brackets for a stadium shape. "
                "Use exactly node_id([\"label\"])."
            )

        return v