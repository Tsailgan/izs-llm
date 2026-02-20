from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Literal, List, Optional, Dict

# --- Component Definition ---
class ComponentDef(BaseModel):
    process_alias: str = Field(..., description="The unique variable name for this step (e.g. 'custom_filter').")
    source_type: Literal["RAG_COMPONENT", "CUSTOM_SCRIPT"] = Field(..., description="If the tool is not in RAG, select CUSTOM_SCRIPT.")
    source_description: Optional[str] = Field(None, description="Brief description of what this component does.")
    component_id: Optional[str] = Field(None, description="The RAG ID. REQUIRED if source_type is RAG_COMPONENT. Must be NULL if source_type is CUSTOM_SCRIPT.")

    input_type: Optional[str] = Field(None, description="The primary input data format (e.g., 'FastQ', 'BAM', 'VCF').")
    output_type: Optional[str] = Field(None, description="The primary output data format (e.g., 'BAM', 'HTML', 'TXT').")

    @model_validator(mode='after')
    def enforce_rag_for_standard_tools(self):
        if self.source_type == "CUSTOM_SCRIPT":
            description_text = str(self.process_alias) + " " + str(self.source_description)
            description_text = description_text.lower()
            
            standard_tools = [
                # QC & Preprocessing
                "fastp", "fastqc", "nanoplot", "trimmomatic", "chopper", "bbnorm", "downsampl", "trimming",
                # Mapping & Filtering
                "bowtie", "minimap", "samtools", "krakentools",
                # Assembly
                "shovill", "spades", "unicycler", 
                # Variant Calling & Consensus
                "snippy", "ivar", "medaka",
                # Taxonomy & Classification
                "kraken", "bracken", "centrifuge", "confindr", "kmerfinder", "mash",
                # AMR, Genes & Annotation
                "abricate", "resfinder", "staramr", "prokka",
                # Typing & Lineage
                "mlst", "cgmlst", "chewbbaca", "flaa", "pangolin", "mobsuite", "westnile",
                # Multi-sample
                "panaroo", "augur", "reportree"
            ]
            
            for tool in standard_tools:
                if tool in description_text:
                    raise ValueError(
                        f"VALIDATION ERROR. You marked '{self.process_alias}' as a CUSTOM_SCRIPT. "
                        f"However '{tool}' is a standard tool. "
                        f"You must find its exact component_id in the provided RAG context and set source_type to RAG_COMPONENT."
                    )
        return self

# --- Logic Definition ---
class LogicStep(BaseModel):
    step_type: Literal["PROCESS_RUN", "OPERATOR", "COMMENT"]
    description: str = Field(..., description="Brief explanation of intent.")
    code_snippet: str = Field(..., description="Simplified logic string.")

# --- The Blueprint ---
class PipelinePlan(BaseModel):
    strategy_selector: Literal["EXACT_MATCH", "ADAPTED_MATCH", "CUSTOM_BUILD"] = Field(...)
    used_template_id: Optional[str] = Field(None, description="Parent template ID if applicable.")
    components: List[ComponentDef] = Field(default=[], description="List of tools.")
    workflow_logic: List[LogicStep] = Field(default=[], description="Logic flow.")
    global_params: Dict[str, str] = Field(default={})

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{
                "strategy_selector": "CUSTOM_BUILD",
                "used_template_id": None,
                "components": [
                    {
                        "process_alias": "fastqc_check", 
                        "source_type": "RAG_COMPONENT", 
                        "component_id": "step_1PP_qc__fastqc",
                        "input_type": "FastQ",
                        "output_type": "HTML"
                    },
                    {
                        "process_alias": "custom_parser", 
                        "source_type": "CUSTOM_SCRIPT", 
                        "component_id": None,
                        "input_type": "HTML",
                        "output_type": "JSON"
                    }
                ],
                "workflow_logic": [
                    {"step_type": "PROCESS_RUN", "description": "Run QC", "code_snippet": "step_1PP_qc__fastqc(input)"},
                    {"step_type": "PROCESS_RUN", "description": "Parse stats", "code_snippet": "custom_parser(step_1PP_qc__fastqc.out)"}
                ]
            }]
        }
    )