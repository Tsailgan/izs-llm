import os
import json
from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Literal, List, Optional, Dict

CATALOG_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'catalog', 'catalog_part1_components.json')
VALID_COMPONENT_IDS = set()

try:
    with open(CATALOG_PATH, 'r') as f:
        catalog_data = json.load(f)
        for comp in catalog_data.get('components', []):
            if 'id' in comp:
                VALID_COMPONENT_IDS.add(comp['id'])
except Exception as e:
    print(f"Warning: Could not load catalog for validation: {e}")

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

    @model_validator(mode='after')
    def validate_real_rag_id(self):
        if self.source_type == "RAG_COMPONENT":
            if not self.component_id:
                raise ValueError("VALIDATION ERROR: RAG_COMPONENT must have a component_id.")
            
            if VALID_COMPONENT_IDS and self.component_id not in VALID_COMPONENT_IDS:
                valid_list = "\n- ".join(sorted(VALID_COMPONENT_IDS))
                raise ValueError(
                    f"VALIDATION ERROR: '{self.component_id}' is a fake component_id. "
                    f"You MUST select the exact matching ID from this allowed list:\n- {valid_list}"
                )
        return self

    @model_validator(mode='after')
    def enforce_alias_matches_id(self):
        """Forces the alias to equal the component ID to stop the Architect from copying bad names."""
        if self.source_type == "RAG_COMPONENT" and self.component_id:
            if self.process_alias != self.component_id:
                raise ValueError(
                    f"VALIDATION ERROR: For RAG components, the process_alias ('{self.process_alias}') "
                    f"MUST exactly match the component_id ('{self.component_id}'). Do not invent a new alias."
                )
        return self

# --- Logic Definition ---
class LogicStep(BaseModel):
    step_type: Literal["PROCESS_RUN", "OPERATOR", "COMMENT"]
    description: str = Field(..., description="Brief explanation of intent.")
    code_snippet: str = Field(
        ..., 
        description="Authentic Nextflow logic. For processes you MUST use the exact component_id and access outputs with .out.output_name. For operators you can use .collect()."
    )

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
                        "process_alias": "step_1PP_downsampling__bbnorm", 
                        "source_type": "RAG_COMPONENT", 
                        "component_id": "step_1PP_downsampling__bbnorm",
                        "input_type": "FastQ",
                        "output_type": "FastQ"
                    },
                    {
                        "process_alias": "multi_clustering__reportree", 
                        "source_type": "RAG_COMPONENT", 
                        "component_id": "multi_clustering__reportree",
                        "input_type": "Allele_Matrix",
                        "output_type": "Report"
                    }
                ],
                "workflow_logic": [
                    {
                        "step_type": "PROCESS_RUN", 
                        "description": "Downsample reads", 
                        "code_snippet": "step_1PP_downsampling__bbnorm(raw_reads, params.k, params.target)"
                    },
                    {
                        "step_type": "OPERATOR", 
                        "description": "Collect all data for report", 
                        "code_snippet": "step_1PP_downsampling__bbnorm.out.fastq_downsampled.collect().set { collected_data }"
                    },
                    {
                        "step_type": "PROCESS_RUN", 
                        "description": "Run reportree", 
                        "code_snippet": "multi_clustering__reportree(collected_data)"
                    }
                ],
                "global_params": {
                    "k": "31",
                    "target": "100"
                }
            }]
        }
    )