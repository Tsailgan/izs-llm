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

    @field_validator('value')
    def forbid_active_channels(cls, v):
        """Blocks the LLM from putting getSingleInput() or getReference() in the globals block."""
        if '(' in v and ')' in v and any(kw in v for kw in ['get', 'param', 'Channel']):
            raise ValueError(
                f"\n=======================================================\n"
                f"GLOBAL SCOPE ERROR: You placed an active function '{v}' in the `globals` list.\n"
                f"Active data channels WILL CRASH Nextflow if defined globally.\n"
                f"CRITICAL REPAIR INSTRUCTION: \n"
                f"1. DELETE this variable from the `globals` array.\n"
                f"2. Move '{v}' down into the `entrypoint` body_code!\n"
                f"=======================================================\n"
            )
        return v

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
                existing = data.get('emit_channels', [])
                for k, v in assignments:
                    emit_str = f"{k} = {v}"
                    if emit_str not in existing:
                        existing.append(emit_str)
                data['emit_channels'] = existing

        match = re.search(r'^\s*workflow\s+[_a-zA-Z0-9]*\s*\{(.*)\}\s*$', body, re.DOTALL)
        if match: body = match.group(1)

        body = re.sub(r'^\s*take:.*?(?=^\s*main:|^\s*emit:|\Z)', '', body, flags=re.MULTILINE | re.DOTALL)
        body = re.sub(r'^\s*emit:[\s\S]*', '', body, flags=re.MULTILINE)
        body = re.sub(r'^\s*main:\s*', '', body, flags=re.MULTILINE)

        data['body_code'] = body.strip()
        return data

    @field_validator('emit_channels')
    def validate_emit_format(cls, v):
        for emit_str in v:
            if '(' in emit_str or ')' in emit_str:
                raise ValueError(
                    f"STRICT EMIT FORMAT ERROR: '{emit_str}' contains parenthesis. "
                    f"DO NOT put function calls in the emit channels.\n"
                    f"CRITICAL REPAIR INSTRUCTION: Assign the process to a variable in your body_code, "
                    f"and only emit the variable name (e.g., 'depleted_reads') or property (e.g., 'consensus = out.consensus')."
                )
        return v

    @field_validator('emit_channels')
    def forbid_void_emits(cls, v):
        """Strictly prevents the LLM from trying to emit outputs from known Void tools."""
        void_keywords = [
            'pangolin', 'lineage_report', 'fastqc', 'quast', 'nanoplot', 'centrifuge', 
            'confindr', 'mash', 'resfinder', 'staramr', 'prokka', 
            'mlst', 'chewbbaca', 'flaa'
        ]
        for emit_str in v:
            lower_str = emit_str.lower()
            for kw in void_keywords:
                if kw in lower_str:
                    raise ValueError(
                        f"\n=======================================================\n"
                        f"FATAL ERROR: YOU ARE TRAPPED IN A HALLUCINATION LOOP!\n"
                        f"You are trying to emit '{emit_str}' which is related to '{kw}'.\n"
                        f"'{kw.upper()}' IS A VOID TOOL. IT HAS NO OUTPUTS TO EMIT.\n"
                        f"1. REMOVE '{emit_str}' from `emit_channels` completely.\n"
                        f"2. DO NOT assign {kw} to a variable in your body_code. (WRONG: `res = {kw}(...)` -> RIGHT: `{kw}(...)`)\n"
                        f"3. DO NOT rename the variable to trick the validator. JUST DELETE THE EMIT.\n"
                        f"=======================================================\n"
                    )
        return v

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
    def enforce_strict_data_shaping(self):
        """Strictly enforces that the LLM manually shapes data and never uses inline channel joins."""
        if not self.body_code:
            return self
            
        process_calls = re.finditer(r'\b(?:step_|multi_|module_|medaka|samtools|coverage|aggregate|staramr)[a-zA-Z0-9_]*\s*\(([^)]+)\)', self.body_code)
        for match in process_calls:
            args = match.group(1)
            # Allowed: | groupTuple. Forbidden: .cross, .combine
            if '.cross' in args or '.combine' in args:
                raise ValueError(
                    f"SYNTAX ERROR in '{self.name}': Inline channel joins are forbidden.\n"
                    f"Found: '{match.group(0)}'\n"
                    f"You MUST perform .cross() or .combine() on a separate line, "
                    f"flatten it with .map or .multiMap, assign it to a variable, and pass ONLY the variable."
                )

        ops_matches = re.finditer(r'\.(cross|combine)\s*\([^)]*\)', self.body_code)
        for match in ops_matches:
            post_op_text = self.body_code[match.end():]
            chain_pattern = re.compile(r'^\s*(?:\{[^}]*\}\s*)?\.(map|multiMap|set|branch)\b')
            if not chain_pattern.search(post_op_text):
                raise ValueError(
                    f"DATA SHAPING ERROR in '{self.name}': A '.{match.group(1)}()' operation was found without being flattened.\n"
                    f"In cohesive-ngsmanager, you MUST chain '.map {{ ... }}', '.multiMap {{ ... }}', or '.set {{ ... }}' "
                    f"after channel joins to ensure the tuple structure is correct."
                )

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

        process_calls = re.findall(r'\b([a-zA-Z0-9_]+)\s*\(', self.body_code)
        valid_vars.update(process_calls)

        for emit_str in self.emit_channels:
            rhs = emit_str.split('=')[-1].strip()
            
            base_var = re.split(r'[\.\[]', rhs)[0].strip()
            
            if not base_var or base_var.startswith("'") or base_var.startswith('"') or base_var in ['true', 'false', 'null']:
                continue
                
            if base_var not in valid_vars:
                raise ValueError(
                    f"HALLUCINATION DETECTED in workflow '{self.name}'. "
                    f"You are trying to emit '{emit_str}' but the variable '{base_var}' was NEVER DEFINED.\n\n"
                    f"CRITICAL REPAIR INSTRUCTION:\n"
                    f"1. If '{base_var}' is supposed to be the output of a Void tool (like Pangolin, FastQC, or reporting tools that use publishDir), "
                    f"it DOES NOT output a channel. You MUST completely REMOVE '{emit_str}' from your `emit_channels` list.\n"
                    f"2. DO NOT try to assign Void tools to variables (e.g. do not write `res = pangolin()`). Just call the process directly.\n"
                    f"3. Do not invent or guess variable names to make this error go away. Delete the emit entirely."
                )
        return self

    @model_validator(mode='after')
    def enforce_host_depletion_shape(self):
        """Traces the specific variable passed to Host Depletion to ensure it uses .map"""
        if not self.body_code:
            return self

        host_calls = re.findall(r'step_1PP_hostdepl__[a-zA-Z0-9_]+\s*\(([a-zA-Z0-9_]+)\)', self.body_code)
        
        for var_name in host_calls:
            bad_pattern = rf'\.multiMap\s*\{{[^}}]*\}}\s*\.set\s*\{{\s*{var_name}\s*\}}'
            
            if re.search(bad_pattern, self.body_code):
                raise ValueError(
                    f"\n=======================================================\n"
                    f"DATA SHAPING ERROR in '{self.name}': You used `.multiMap` to prepare the '{var_name}' channel for Host Depletion.\n"
                    f"Host depletion tools (`step_1PP_hostdepl__*`) require a SINGLE FLAT TUPLE.\n"
                    f"CRITICAL REPAIR INSTRUCTION:\n"
                    f"Change the preparation of '{var_name}' to use `.map` instead of `.multiMap`:\n"
                    f"`.map {{ [ it[0][0], it[0][1], it[1][1] ] }}.set {{ {var_name} }}`\n"
                    f"=======================================================\n"
                )
        return self

    @model_validator(mode='after')
    def forbid_set_on_processes(self):
        if not self.body_code:
            return self
            
        if re.search(r'\b(?:step_|multi_|module_)[a-zA-Z0-9_]+\s*\([^)]*\)\s*\.set\s*\{', self.body_code):
            raise ValueError(
                f"\n=======================================================\n"
                f"SYNTAX ERROR in '{self.name}': You appended `.set {{...}}` to a process call.\n"
                f"In Nextflow, `.set` is ONLY for channel shaping (like `.map`).\n"
                f"CRITICAL REPAIR INSTRUCTION:\n"
                f"1. If this is a standard process, use direct assignment: `var_name = process(...)`\n"
                f"2. If this is a VOID tool (like Pangolin or Prokka), DO NOT assign it to a variable at all. Just call `process(...)`.\n"
                f"=======================================================\n"
            )
        return self
    
    @model_validator(mode='after')
    def enforce_reference_slice(self):
        """Forces the LLM to slice references with [1..3] when preparing data for mapping."""
        if not self.body_code:
            return self

        if 'step_2AS_mapping__' in self.body_code and '.multiMap' in self.body_code:
            bad_pattern = r'\b[a-zA-Z0-9_]+\s*:\s*it\[1\](?!\s*\[)'
            
            if re.search(bad_pattern, self.body_code):
                raise ValueError(
                    f"\n=======================================================\n"
                    f"DATA SHAPING ERROR in '{self.name}': You forgot the `[1..3]` slice for the reference!\n"
                    f"When crossing reads with a reference for mapping tools (e.g., Bowtie, Minimap2, Ivar), "
                    f"you MUST extract the riscd, code, and path using `it[1][1..3]`.\n"
                    f"CRITICAL REPAIR INSTRUCTION:\n"
                    f"Inside your `.multiMap {{ ... }}` block, change `it[1]` to `it[1][1..3]`.\n"
                    f"=======================================================\n"
                )
        return self

    @model_validator(mode='after')
    def forbid_void_tool_assignment(self):
        """Physically blocks the LLM from assigning Void tools to variables using '='."""
        if not self.body_code:
            return self

        void_keywords = [
            'pangolin', 'fastqc', 'quast', 'nanoplot', 'centrifuge', 
            'confindr', 'mash', 'resfinder', 'staramr', 'prokka', 
            'mlst', 'chewbbaca', 'flaa'
        ]

        for kw in void_keywords:
            bad_pattern = rf'\b[a-zA-Z0-9_]+\s*=\s*(?:step_|multi_|module_)[a-zA-Z0-9_]*{kw}[a-zA-Z0-9_]*\s*\('
            
            if re.search(bad_pattern, self.body_code.lower()):
                raise ValueError(
                    f"\n=======================================================\n"
                    f"VOID TOOL ERROR in '{self.name}': You assigned a VOID TOOL ('{kw}') to a variable.\n"
                    f"Void tools use `publishDir` and return NOTHING. Assigning them to a variable causes a runtime crash.\n"
                    f"CRITICAL REPAIR INSTRUCTION:\n"
                    f"1. Remove the `variable = ` assignment completely.\n"
                    f"2. Just call the process directly on its own line: `step_..._{kw}(...)`\n"
                    f"3. Make sure you delete that variable from your `emit_channels` entirely!\n"
                    f"=======================================================\n"
                )
        return self

    @model_validator(mode='after')
    def forbid_naked_process_calls(self):
        if not self.body_code:
            return self

        valid_prefixes = ('step_', 'multi_', 'module_')
        
        valid_funcs = {
            'extractKey', 'getEmpty', 'extractDsRef', 'groupTuple', 'tuple', 
            'file', 'println', 'log', 'exit', 'Channel', 'getSingleInput', 
            'getInput', 'getReference', 'getReferences', 'getHostUnkeyed', 
            'param', 'optional', 'checkEnum'
        }

        calls = re.finditer(r'(?<!\.)\b([a-zA-Z0-9_]+)\s*\(', self.body_code)
        for match in calls:
            func_name = match.group(1)
            
            if not func_name.startswith(valid_prefixes) and func_name not in valid_funcs:
                raise ValueError(
                    f"\n=======================================================\n"
                    f"HALLUCINATED PROCESS ERROR in '{self.name}': You called `{func_name}()` directly.\n"
                    f"In cohesive-ngsmanager, you CANNOT call naked process names. All external tools MUST be called via their wrapper steps.\n"
                    f"CRITICAL REPAIR INSTRUCTION:\n"
                    f"Find the correct `step_` wrapper for `{func_name}` (e.g., `step_..._{func_name}`) and use that instead.\n"
                    f"=======================================================\n"
                )

        pipes = re.finditer(r'\|\s*([a-zA-Z0-9_]+)\b', self.body_code)
        for match in pipes:
            pipe_target = match.group(1)
            if not pipe_target.startswith(valid_prefixes) and pipe_target not in valid_funcs:
                 raise ValueError(
                    f"\n=======================================================\n"
                    f"PIPING ERROR in '{self.name}': You piped into `{pipe_target}`.\n"
                    f"You MUST pipe into a valid `step_` wrapper. Raw naked processes are forbidden.\n"
                    f"CRITICAL REPAIR INSTRUCTION:\n"
                    f"Replace `{pipe_target}` with its full `step_..._{pipe_target}` wrapper name.\n"
                    f"=======================================================\n"
                )
        return self

class Entrypoint(BaseModel):
    body_code: str = Field(
        description="The code inside the main unnamed workflow. Do not write 'workflow {{ }}'."
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

        common_funcs = {
            'parseMetadataFromFileName', 'executionMetadata', 'taskMemory', 'taskTime',
            'getRisCd', 'extractKey', 'stepInputs', 'extractDsRef', 'getBaseName',
            'getGB', 'getEmpty', 'parseRISCD', 'isFastqRiscd', 'isFastaRiscd',
            'isSpeciesSupported', 'csv2map', 'flattenPath', 'logHeader'
        }

        param_funcs = {
            'getTrimmedReads', 'getAssembly', 'getDepletedReads', 'getReferenceCodes',
            'getNCBICodes', 'getReferences', 'getReference', 'getReferenceUnkeyed',
            'getReferenceOptional', 'getHost', 'getGenusSpecies', 'getModule',
            'getAbricateDatabase', 'getBlastDatabase', 'getParamTaxaId', '_getParamAsValue',
            '_getParam', 'getDS', 'isFullOutput', 'getResult', 'getKrakenResults',
            'getInput', 'getVCFs', 'hasEnoughFastqData', 'hasFastqData', 'param',
            'optional', 'optionalOrDefault', 'isIonTorrent', 'isNanopore', 'isIlluminaPaired',
            'isCompatibleWithSeqType', 'isSegmentedMapping', 'checkEnum', 'getHostReference',
            'getLongReads', 'paramWrap', 'optWrap', '_getReferences', '_getSingleReference',
            'getHostOptional', 'getHostUnkeyed', 'getGenusSpeciesOptionalUnkeyed',
            'getGenusSpeciesOptional', 'getSpecies', 'getBlastDatabaseUnkeyed', 'getKingdom',
            'getTaxIdsUnkeyed', 'getParamIncludeParents', 'getParamIncludeChildren',
            '_getAlleles', 'getParam', 'getInputOf', 'getInputFolders', 'getSingleInput'
        }
        
        import_map = {}
        for func in used_callables:
            if func.startswith('step_'):
                path = f"../steps/{func}"
            elif func.startswith('multi_'):
                path = f"../multi/{func}"
            elif func.startswith('module_'):
                path = f"../modules/{func}"
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