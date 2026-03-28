from pydantic import BaseModel, Field, field_validator, model_validator
import re
from typing import List, Optional

class ImportItem(BaseModel):
    module_path: str = Field(
        description="Path to the module. MUST start with '../steps/' or '../functions/'. NEVER use 'nf-core'."
    )
    functions: List[str] = Field(description="List of process names to import.")

    @field_validator('functions')
    def validate_aliases(cls, v):
        """Enforce correct 'as' alias formatting."""
        cleaned = []
        for func in v:
            if ' as ' in func:
                parts = func.split(' as ')
                if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
                    raise ValueError(f"Invalid alias format: '{func}'. Use 'OriginalName as AliasName'")
            cleaned.append(func)
        return cleaned

    @field_validator('module_path')
    def forbid_nf_core(cls, v):
        if 'nf-core' in v:
            raise ValueError(
                f"HALLUCINATION DETECTED: 'nf-core' paths are strictly forbidden. "
                f"You MUST use local paths based on the tool prefix (e.g., '../steps/...' or '../modules/...'). Got: {v}"
            )
        return v
        
    @model_validator(mode='after')
    def auto_fix_module_paths(self):
        """Automatically correct paths based on the function prefix."""
        if "../functions/" in self.module_path:
            return self

        for func in self.functions:
            base_name = func.split(' as ')[0].strip()
            if base_name.startswith('multi_'):
                self.module_path = f"../multi/{base_name}"
            elif base_name.startswith('step_'):
                self.module_path = f"../steps/{base_name}"
            elif base_name.startswith('module_'):
                self.module_path = f"../modules/{base_name}"
        return self
    
class GlobalDef(BaseModel):
    type: str = Field(description="The definition keyword, usually 'def'.")
    name: str = Field(description="The variable name.")
    value: str = Field(description="The string value.")

class InlineProcess(BaseModel):
    name: str = Field(description="The name of the custom process.")
    container: Optional[str] = None
    input_declarations: List[str] = []
    output_declarations: List[str] = []
    script_block: str = Field(description="The raw bash script.")

    @field_validator('script_block')
    def validate_no_dsl(cls, v):
        """Forbid DSL2 logic inside bash scripts."""
        forbidden = ['workflow', '.cross(', '.join(', '.multiMap', '.map{', '.mix(']
        for kw in forbidden:
            if kw in v:
                raise ValueError(
                    f"INVALID PROCESS CONTENT: Found DSL2 keyword '{kw}' inside a Process script.\n"
                    f"Processes are for BASH/SHELL commands only. If you need logic, define a 'sub_workflow'."
                )
        return v
    
    @field_validator('name')
    def validate_name(cls, v):
        """Forbid RAG names or UPPERCASE names in inline processes."""
        if v.startswith("step_") or v.startswith("multi_"):
            raise ValueError(f"Process name '{v}' starts with a reserved prefix. Standard tools MUST be imported, not defined inline.")
        if v.isupper():
            raise ValueError(f"Process '{v}' is UPPERCASE. It should likely be a Global Constant, not a Process.")
        return v

class WorkflowBlock(BaseModel):
    name: str = Field(description="The name of the workflow.")
    take_channels: List[str] = Field(default=[], description="List of input channel names.")
    emit_channels: List[str] = Field(default=[], description="List of output channel names.")
    body_code: str = Field(description="The raw Groovy logic.")

    @model_validator(mode='before')
    @classmethod
    def rescue_and_heal_body(cls, data: dict) -> dict:
        if not isinstance(data, dict): return data
        
        body = data.get('body_code', '')
        if not isinstance(body, str): return data
        
        emit_match = re.search(r'^\s*emit:\s*([\s\S]*)$', body, flags=re.MULTILINE)
        if emit_match:
            emit_block = emit_match.group(1)
            assignments = re.findall(r'([a-zA-Z0-9_]+)\s*=\s*([a-zA-Z0-9_.\-\[\]]+)', emit_block)
            if assignments:
                data['emit_channels'] = [f"{k} = {v}" for k, v in assignments]

        match = re.search(r'^\s*workflow\s+[_a-zA-Z0-9]*\s*\{(.*)\}\s*$', body, re.DOTALL)
        if match: body = match.group(1)

        body = re.sub(r'^\s*take:.*?(?=^\s*main:|^\s*emit:|\Z)', '', body, flags=re.MULTILINE | re.DOTALL)
        body = re.sub(r'^\s*emit:[\s\S]*', '', body, flags=re.MULTILINE)
        body = re.sub(r'^\s*main:\s*', '', body, flags=re.MULTILINE)

        data['body_code'] = body.strip()
        return data

    @model_validator(mode='after')
    def enforce_take_channel_usage(self):
        if not self.take_channels:
            return self
            
        combined_text = self.body_code + " " + " ".join(self.emit_channels)
        
        for ch in self.take_channels:
            pattern = rf"\b{re.escape(ch)}\b"
            if not re.search(pattern, combined_text):
                raise ValueError(
                    f"LOGIC ERROR in workflow '{self.name}'. You defined '{ch}' in take_channels "
                    f"but you never used it in the body_code and never emitted it. "
                    f"Either use it, emit it directly, or remove it from take_channels."
                )
        return self

    @model_validator(mode='after')
    def forbid_recursion(self):
        if self.name and self.body_code:
            pattern = rf"\b{self.name}\b\s*\("
            if re.search(pattern, self.body_code):
                raise ValueError(f"RECURSION ERROR: Workflow '{self.name}' is trying to call itself. This is forbidden.")
        return self

    @model_validator(mode='after')
    def enforce_variable_existence(self):
        """Ensures that any variable emitted actually exists in the take_channels or body_code."""
        if not self.body_code:
            return self
            
        valid_vars = set(self.take_channels)

        assignments = re.findall(r'^[\s]*(?:def\s+)?([a-zA-Z0-9_]+)\s*=', self.body_code, re.MULTILINE)
        valid_vars.update(assignments)
      
        sets = re.findall(r'\.set\s*\{\s*([a-zA-Z0-9_]+)\s*\}', self.body_code)
        valid_vars.update(sets)

        for emit_str in self.emit_channels:
            rhs = emit_str.split('=')[-1].strip()
            
            base_var = re.split(r'[\.\[]', rhs)[0].strip()
            
            if not base_var or base_var.startswith("'") or base_var.startswith('"') or base_var in ['true', 'false', 'null']:
                continue
                
            if base_var not in valid_vars:
                raise ValueError(
                    f"HALLUCINATION DETECTED in workflow '{self.name}'. "
                    f"You are trying to emit '{emit_str}' but the variable '{base_var}' "
                    f"was NEVER DEFINED. It is not in your take_channels and you did not assign it in the body_code."
                )
        return self

class Entrypoint(BaseModel):
    body_code: str = Field(
        description="The code inside the main unnamed workflow. Do not write 'workflow { }'."
    )

    @field_validator('body_code', mode='before')
    def auto_heal_entrypoint(cls, v):
        """Silently cleans up the entrypoint logic."""
        if not isinstance(v, str): return v

        match = re.search(r'^\s*workflow\s*\{(.*)\}\s*$', v, re.DOTALL)
        if match: v = match.group(1)

        v = re.sub(r'^\s*main:\s*', '', v, flags=re.MULTILINE)

        v = re.sub(r'^\s*emit:[\s\S]*', '', v, flags=re.MULTILINE)

        return v.strip()

class NextflowPipelineAST(BaseModel):
    imports: List[ImportItem] = []
    globals: List[GlobalDef] = []
    inline_processes: List[InlineProcess] = []
    sub_workflows: List[WorkflowBlock] = []
    entrypoint: Entrypoint

    @model_validator(mode='after')
    def auto_generate_imports(self):
        all_code = self.entrypoint.body_code
        for sw in self.sub_workflows:
            all_code += "\n" + sw.body_code
        for ip in self.inline_processes:
            all_code += "\n" + ip.script_block
        for g in self.globals:
            all_code += "\n" + g.value

        pattern = re.compile(r'(?<!\.)\b((?:step_|multi_|module_|prepare_|get[A-Z]|extract[A-Z]|is[A-Z]|parse[A-Z]|execution[A-Z]|task[A-Z]|check[A-Z])[a-zA-Z0-9_]*)\s*\(')
        used_callables = set(match.group(1) for match in pattern.finditer(all_code))
        
        defined_sws = {sw.name for sw in self.sub_workflows}
        used_callables = used_callables - defined_sws

        common_funcs = {'extractDsRef', 'parseMetadataFromFileName', 'executionMetadata', 'extractKey', 'taskMemory', 'getEmpty', 'stepInputs', 'getRisCd', 'flattenPath'}
        param_funcs = {'getSingleInput', 'getReference', 'getReferenceOptional', 'isIlluminaPaired', 'isCompatibleWithSeqType', 'isIonTorrent', 'getInput', 'getKingdom', 'checkEnum', 'getTrimmedReads', 'getAssembly'}

        import_map = {}
        for func in used_callables:
            if func.startswith('step_'):
                path = f"../steps/{func}.nf"
            elif func.startswith('multi_'):
                path = f"../multi/{func}.nf"
            elif func.startswith('module_'):
                path = f"../modules/{func}.nf"
            elif func in common_funcs:
                path = "../functions/common.nf"
            elif func in param_funcs:
                path = "../functions/parameters.nf"
            else:
                continue
                
            if path not in import_map:
                import_map[path] = []
            import_map[path].append(func)

        new_imports = []
        for path, funcs in import_map.items():
            new_imports.append(ImportItem(module_path=path, functions=sorted(funcs)))
            
        self.imports = new_imports
        return self

    @model_validator(mode='after')
    def enforce_workflow_usage(self):
        """If you define a sub_workflow, you must actually use it."""
        all_code = self.entrypoint.body_code
        for sw in self.sub_workflows:
            pattern = rf"\b{sw.name}\b\s*\("
            if not re.search(pattern, all_code):
                raise ValueError(
                    f"VALIDATION ERROR: The sub_workflow '{sw.name}' is defined but NEVER CALLED in the pipeline. "
                    f"Either call it in the entrypoint workflow or remove it."
                )
        return self