from pydantic import BaseModel, Field
from typing import List, Optional

class ImportItem(BaseModel):
    module_path: str
    functions: List[str]

class GlobalDef(BaseModel):
    type: str
    name: str
    value: str

class InlineProcess(BaseModel):
    name: str
    container: Optional[str] = None
    input_declarations: List[str] = []
    output_declarations: List[str] = []
    script_block: str 

class WorkflowBlock(BaseModel):
    name: str
    take_channels: List[str] = []
    emit_channels: List[str] = []
    body_code: str 

class Entrypoint(BaseModel):
    body_code: str 

class NextflowPipelineAST(BaseModel):
    imports: List[ImportItem] = []
    globals: List[GlobalDef] = []
    inline_processes: List[InlineProcess] = []
    sub_workflows: List[WorkflowBlock] = []
    main_workflow: WorkflowBlock
    entrypoint: Entrypoint