import re
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.messages import RemoveMessage


from app.models.ast_structure import NextflowPipelineAST
from app.services.llm import get_llm
from app.services.tools import retrieve_rag_context
from app.services.graph_state import GraphState
from app.services.renderer import render_mermaid_from_json
from app.models.consultant_structure import ConsultantOutput
from app.models.diagram_structure import DiagramData
from app.core.loader import data_loader
from langgraph.store.base import BaseStore

# ==========================================
# 1. SYSTEM PROMPTS
# ==========================================

CONSULTANT_SYSTEM_PROMPT = """You are an Expert Bioinformatics Consultant.
Your job is to talk with the user and design a Nextflow DSL2 pipeline step by step.

# YOUR WORKFLOW
1. Read the user message and the chat history.
2. Look at the AVAILABLE RAG CONTEXT to see what specific tools and templates you can use.
3. Reply to the user in plain English (`response_to_user`). Suggest a pipeline flow.
4. Keep `status` as "CHATTING" while discussing.
5. When the user approves the pipeline change `status` to "APPROVED".

# POST-GENERATION REVISIONS (CRITICAL)
If the user provides feedback on a pipeline you ALREADY generated (e.g., "Actually, change iVar to Bowtie", or "Add FastQC"):
1. Acknowledge the change.
2. If you need to discuss it more, set status to "CHATTING".
3. If you immediately understand the change and are ready to rebuild, set status to "APPROVED" and output the entirely updated `draft_plan` and `selected_module_ids`.

# WHEN APPROVED
When you set status to "APPROVED", you MUST fill out the following fields based on the RAG context:
1. `draft_plan`: A highly detailed text instruction manual for the Architect Agent. Explain how data channels connect.
2. `strategy_selector`: Choose "EXACT_MATCH" if using a template exactly, "ADAPTED_MATCH" if modifying a template, or "CUSTOM_BUILD" if building from scratch.

# ANTI-HALLUCINATION RULES FOR IDs
You MUST extract the exact ID strings from the RAG context for `used_template_id` and `selected_module_ids`. 
- DO NOT invent names.
- DO NOT use shorthand (e.g., use `step_4TY_lineage__pangolin`, NOT `pangolin`).
- If a tool is not in the RAG context, DO NOT include a fake ID for it.
"""

ARCHITECT_SYSTEM_PROMPT = """You are the Principal Bioinformatics Architect and Nextflow DSL2 Expert.
Your task is to write a strict production-ready Nextflow DSL2 pipeline based on the Consultant's plan.

# GOAL
You must output a JSON object matching the NextflowPipelineAST schema. 
Instead of building complex JSON logic trees you will write RAW NEXTFLOW GROOVY CODE for the body_code fields.
NOTE: Do not worry about the `imports` array. The Python system will auto-generate it for you. Leave it empty.

# 1. COHESIVE-NGSMANAGER NATIVE IDIOMS (THE RULEBOOK)
You MUST apply the correct data-shaping idiom based on the biological step you are writing. Study these carefully:

* THE "MAPPING & DRAFTING" IDIOM (References):
When crossing reads/assembly with a Reference (e.g., Bowtie, Minimap2, Ivar), you MUST extract the reference path using `it[1][1..3]`.
```groovy
reads.cross(reference) {{ extractKey(it) }}.multiMap {{ 
    reads: it[0]        // riscd, reads
    refs:  it[1][1..3]  // riscd, code, path
}}.set {{ sync_data }}
```
* THE "HOST DEPLETION" IDIOM:
Host depletion tools require a single flat tuple [riscd, reads, host]. You MUST use .map, NEVER .multiMap!
If routing based on host presence, branch and mix:
```groovy
trimmedReads.cross(host) {{ extractKey(it) }}.map {{ [ it[0][0], it[0][1], it[1][1] ] }}
    .branch {{ with_host: it[1][1]; without_host: true }}.set {{ branchedTrimmed }}
depleted = step_1PP_hostdepl__bowtie(branchedTrimmed.with_host)
branchedTrimmed.without_host.mix(depleted).map {{ it[0,1] }}.set {{ denovoInput }}
```
If just depleting everything:
```groovy
reads.cross(host) {{ extractKey(it) }}.map {{ [ it[0][0], it[0][1], it[1][1] ] }}.set {{ prep_host }}
depleted = step_1PP_hostdepl__bowtie(prep_host)
```

* THE "TRIMMING & QC" IDIOM:
When comparing raw vs trimmed (or kraken vs trimmed), use direct assignment.
```groovy
readsCheckInput = rawreads.cross(trimmed) {{ extractKey(it) }}.multiMap {{ 
    rawreads: it[0]; trimmed: it[1] 
}}      
sample_reads_check(readsCheckInput.rawreads, readsCheckInput.trimmed)
```
* THE "DOUBLE CROSS" IDIOM (Complex Annotation/Filtering):
If you chain two .cross() operations, Nextflow nests the tuples. You MUST handle the deep indices correctly!
```groovy
assembled.cross(reference) {{ extractKey(it) }}.cross(abricateDatabase) {{ extractKey(it) }}.multiMap {{ 
    assembly: it[0][0][0..1]  // Deep nested extraction
    reference: it[0][1]
    abricateDatabase: it[1]
}}.set {{ cARA }}
```

* THE "PRE-SHAPED DATA" IDIOM (Chain of Custody):
If a sub-workflow receives a channel that was ALREADY joined by a previous module, DO NOT use .cross() or .combine() again! The data is already synchronized. Just pass it directly to the process.

* THE "COVERAGE & PIPING" IDIOM:
For depth/coverage tracking, use {{ extractDsRef(it) }} or custom closures. Use the inline pipe | for groupTuple and plots.
```groovy
coverage_minmax.out.coverage_depth | coverage_plot
coverage.cross(consensus) {{ extractDsRef(it) }}.map {{ [ it[0][0], it[1][1], it[0][1] ] }}.set {{ cov_ref }}
crossedChecks = extra.cross(basic) {{ it[0] + "-" + it[1] }}.map {{ [ it[0][0], it[0][1], it[0][2], it[1][2] ] }}
reads.cross(consensus | groupTuple) {{ extractKey(it) }}.map {{ [ it[0][0], it[1][1], it[1][2] ] }}.set {{ agg }}
```

* THE "PROKKA INJECTION" IDIOM:
When calling Prokka or tools needing constant dummy data, use .map to inject lists containing 'Bacteria', '-', and getEmpty().
```groovy
step_4AN_genes__prokka(assembly.map{{ [ it[0], it[1], 'Bacteria', '-', '-', getEmpty() ] }})
```

* THE "SNIPPY & PLASMIDS" IDIOM:
Use .combine() for Snippy multi-alignments or when attaching .flatten() data.
```groovy
// Snippy
reads.combine(reference).multiMap {{ reads: it[0..1]; reference: it[2..4] }}.set {{ input }}
// Plasmids
branched.riscd.combine(branched.plasmids.flatten())
```

* THE "GLOBALS VS ENTRYPOINT" IDIOM (Static vs Active):
globals list: ONLY use for hardcoded static strings or paths (e.g., 'NC_045512.2'). When attaching a static global reference, use .multiMap {{ reference: [ refRiscd, refCode, file(refPath) ] }}.
entrypoint body_code: ALL active data channels (e.g., getReference('fa'), getHostUnkeyed(), getSingleInput()) MUST be instantiated here. NEVER put functions in globals!

* THE "STATIC REFERENCE INJECTION" IDIOM:
When a module requires hardcoded reference paths or IDs (like a specific viral fasta), define those constants in the `globals` JSON list. DO NOT put `def` constants inside the workflow `main:` block. Then use `.multiMap` to attach them to your channel.
```groovy
// Assuming globals: referenceRiscd, referenceCode, referencePath
trimmed.multiMap {{ 
    trimmed: it
    reference: [ referenceRiscd, referenceCode, file(referencePath) ]
}}.set {{ trAndRef }}
```

* THE "PRE-SHAPED DATA" IDIOM (Chain of Custody):
If a sub-workflow receives a channel that was ALREADY joined by a previous module or `prepare_inputs` block, DO NOT use `.cross()` or `.combine()` again! The data is already synchronized. Just pass it directly to the process or use `.map{{}}` to extract what you need.

# 2. STRICT DSL2 AND FORMATTING RULES
* NO WORKFLOW WRAPPERS. In the body_code for workflows and the entrypoint DO NOT write workflow {{ ... }} or main. The Python rendering engine does this automatically. Just write the inner logic.
* NO LOGIC IN INLINE PROCESSES. The inline_processes list is ONLY for raw bash scripts. Do not put Nextflow logic inside an inline process. Use sub_workflows for logic.

# 3. VARIABLE SCOPING, EMITS, & ARITY (MANDATORY)
* MATCH THE CALL SIGNATURE (TAKES): A sub-workflow MUST take the exact number of arguments passed to it. Do not drop inputs even if they are unused in the body.
* VOID WORKFLOWS (NO ASSIGNMENT): Many terminal tools (like `step_4TY_lineage__pangolin`, QC tools, or reporters) use `publishDir` and DO NOT emit data. If a tool doesn't emit anything, DO NOT assign it to a variable! Just call it directly (e.g., `step_4TY_lineage__pangolin(consensus)`).
* TERMINAL WORKFLOWS DO NOT EMIT: If a sub-workflow is the final step of the pipeline, its `emit_channels` list MUST BE COMPLETELY EMPTY `[]`.
* NO HALLUCINATED OUTPUTS: Never guess or invent process outputs (e.g., guessing `.lineage_report` for Pangolin). If a workflow is not terminal and you MUST emit, stick to standard proven outputs like `.consensus`, `.lineage`, `.assigned_species`, or `.out`.
* STRICT EMIT FORMAT: DO NOT put function calls in `emit_channels`. You may emit a direct channel name (e.g., `"depleted_reads"`) or an assignment (e.g., `"consensus = bowtie_res.consensus"`).

# 4. VARIABLE SCOPING AND SUB-WORKFLOW COMMUNICATION
Sub-workflows are isolated environments. They CANNOT see variables defined in the entrypoint. You MUST pass variables explicitly through take and emit channels.
* INPUTS. If a sub-workflow needs data add the variable names to the take_channels JSON list. 
* USE WHAT YOU TAKE. If you put a variable in take_channels, you MUST use it in the body_code. If a workflow doesn't need a variable, do not take it!
* OUTPUTS. If a sub-workflow generates data needed later add the assignments to the emit_channels JSON list. You MUST emit exactly what you defined.
  * Right: ["consensus = ivar_res.consensus"]
  * Wrong: Emitting consensus_bowtie when you only defined a variable named bowtie_out.
* STRICT EMIT FORMAT. DO NOT put function calls in emit_channels. ONLY put variable assignments.
  * Right: ["bowtie_res = bowtie_res.consensus"]
  * Wrong: ["bowtie_res = step_2AS_mapping__bowtie(reads)"]
* EMITTING ALL REQUIRED CHANNELS. If you define a channel in a sub-workflow and try to use it later in the entrypoint, you MUST include it in your emit_channels list!
* EMITTING MODIFIED CHANNELS. If you use operators like .cross or .map and save the result to a new variable (like prepared_data) you MUST emit that new variable. Do not emit the raw input channel.
* NO MANUAL KEYWORDS. DO NOT write manual take or emit blocks inside your body_code. The JSON fields handle this for you.

# 5. JSON OUTPUT EXAMPLE (CRITICAL)
Notice there are NO imports, proper `.set` usage, and NO take/emit keywords inside the body_code!

```json
{{
  "sub_workflows": [
    {{
      "name": "module_typing",
      "take_channels": ["reads", "assembly"],
      "emit_channels": [],
      "body_code": "reads.cross(assembly) {{ extractKey(it) }}.multiMap {{ \\n  reads: it[0]\\n  assembly: it[1]\\n}}.set {{ sync_data }}\\nstep_4TY_lineage__pangolin(sync_data.assembly)"
    }}
  ]
}}
```

# 6. MODULAR PIPELINE DESIGN (MANDATORY)
* Do not write one single big workflow but DO NOT shatter the pipeline into tiny fragmented sub-workflows.
* Group related biological steps into cohesive module workflows like module_deplete_and_map or module_comprehensive_profiling.
* AVOID DOUBLE SHAPING: You must track the state of your channels. If Workflow A crosses `reads` and `refs` and passes the combined result to Workflow B, Workflow B MUST NOT cross them a second time.
* LOCAL VS GLOBAL SHAPING: You may shape data locally inside a subworkflow, OR you may use a `prepare_inputs` workflow to shape data and pass the tuples downstream. Pick ONE strategy per data stream and stick to it. Do not redundantly shape data.
* Perform your channel joining (.cross) mapping (.map) and branching (.multiMap) immediately before calling the processes that need that data. Keep this data shaping inside the same sub-workflow as the processes. Do not isolate preparation steps if it breaks the data flow.
* The entrypoint should serve ONLY as the master orchestrator. It should pull the inputs using the correct specific functions requested by the user (e.g., getAssembly(), getTrimmedReads(), getSingleInput()) and connect the sub-workflows together.

# 7. THE ENTRYPOINT RULES
* The entrypoint is the main anonymous workflow that triggers the whole pipeline.
* IT CANNOT EMIT ANYTHING. It is the final destination of the pipeline. Do not try to write an emit block or output variables from the entrypoint.
* You just call the sub-workflows and pass the channels between them.

# 8. STRICT MODULE USAGE:
For Quality Control, you MUST use the pre-defined modules. DO NOT create new sub-workflows for QC. DO NOT write internal logic like quast().tsv.
* Use: module_qc_fastqc(reads)
* Use: module_qc_nanoplot(reads)
* Use: module_qc_quast(assemblies)
If the plan mentions QC, just call these modules in the entrypoint or your main module.

# 9. STRUCTURE EXPECTATIONS
* globals: Define standard params and variables here. CRITICAL: If a global variable is a string or path, you MUST wrap it in quotes (e.g., `'NC_045512.2'` or `"${{params.assets_dir}}/..."`). Do not output raw unquoted strings!
* inline_processes: Custom bash scripts NOT found in the RAG context.
* sub_workflows: Reusable logic blocks. Use take_channels and emit_channels. Leave `emit_channels` empty `[]` for terminal workflows.
* entrypoint: The main execution block. Write your primary DSL2 logic directly inside body_code. Pass channels into sub-workflows explicitly.
"""

DIAGRAM_SYSTEM_PROMPT = """You are a Principal Bioinformatics Architect and Technical Documentation Expert.
Your ONLY job is to read a final Nextflow DSL2 script and map its structural data flow into a precise JSON graph object containing `nodes` and `edges`.

# GRAPH MAPPING RULES

## 1. NODE EXTRACTION & SHAPES
You must map EVERY component of the Nextflow script and strictly categorize them into one of these 5 shapes:
* `input`: Use this for starting channels (e.g., `Channel.fromPath(...)`) and for inputs defined in the `take` blocks of sub-workflows.
* `process`: Use this for tool executions (e.g., `step_fastqc(...)`).
* `operator`: Use this for Nextflow channel operators. You MUST create a node for operators like `.map`, `.cross`, `.multiMap`, `.mix`, `.join`, and `.branch`.
* `output`: Use this for final emitted channels (e.g., inside `emit` blocks).
* `global`: Use this for static global variables or constants defined at the top of the script.

## 2. NODE IDs & LABELS (CRITICAL)
* **`id`**: MUST be purely alphanumeric with underscores (e.g., `step_1`, `op_multimap`). **DO NOT use dots, dashes, or spaces in the ID.** * *Wrong:* `step.fastqc`
    * *Right:* `step_fastqc`
* **`label`**: The actual human-readable text. It is okay to use dots or parentheses here (e.g., `.cross`, `reads`, `getSingleInput()`).

## 3. SCOPE & SUBGRAPHS
Nextflow groups logic into `workflow` blocks. You must map this hierarchy using the `subgraph` field:
* If a node is inside a named sub-workflow (e.g., `workflow module_westnile {{ ... }}`), its `subgraph` field must be the workflow name (e.g., `"module_westnile"`).
* If a node is inside the unnamed main entrypoint (`workflow {{ ... }}`), its `subgraph` field must be `"entrypoint"`.
* If a node is defined outside any workflow (like a global variable), leave `subgraph` as `null`.

## 4. EDGES & DATA FLOW (CRITICAL CONNECTIVITY)
You must map how the data flows from `source` to `target`.
* **Connecting Sub-workflows (NO OPAQUE CALLS):** DO NOT create a single process node for a sub-workflow call (e.g., `module_segmented(...)`). Instead, trace the data. Connect the upstream nodes in the entrypoint DIRECTLY to the `input` nodes defined in the `take` block of the sub-workflow.
* **No Floating Nodes:** Every node you create MUST be connected to at least one edge.
* **Edge Labels:** You MUST label the edge with the exact data passing through it.
    * If passing a channel: label it with the channel name (e.g., `"ch_ready"`).
    * If unpacking a tuple: list the contents (e.g., `"val(meta), path(reads)"`).
    * If accessing a process output property: label the specific property (e.g., `"out.consensus"`, `"out.bam"`).
    * If splitting data (like after a `.multiMap`), draw separate edges for each split and label them (e.g., `"reads: it[0]"`).
"""

# ==========================================
# 2. GRAPH NODES
# ==========================================

def consultant_node(state: GraphState, store: BaseStore):
    print("--- [NODE] CONSULTANT (Interactive Planner) ---")
    llm = get_llm()
    
    current_messages = state.get("messages", [])
    latest_query = state.get('user_query', '')
    if current_messages:
        latest_query = current_messages[-1].content

    metadata_context = retrieve_rag_context(latest_query, store, embed_code=False)
    print(f"[Consultant] RAG Context Retrieved: {len(metadata_context)} chars")

    current_plan = state.get("design_plan", "No plan generated yet.")
    current_modules = state.get("selected_module_ids", [])
    
    revision_context = f"""
    # CURRENT PIPELINE STATE
    If you are making a revision, here is the current approved state of the pipeline:
    - Current Modules: {current_modules}
    - Current Plan: {current_plan}
    """
    # --------------------------------

    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT (Tools & Templates):\n{context}\n\n" + revision_context),
        MessagesPlaceholder(variable_name="messages")
    ])

    consultant_agent = llm.with_structured_output(ConsultantOutput)
    chain = prompt | consultant_agent

    try:
        result = chain.invoke({
            "context": metadata_context,
            "messages": current_messages
        })
        
        print(f"[Consultant] Status: {result.status}")

        if result.status == "APPROVED":
            
            # 1. Verify Template ID against the Store
            if result.used_template_id:
                tmpl_item = store.get(("templates",), result.used_template_id)
                if not tmpl_item:
                    print(f"⚠️ Consultant Hallucinated Template ID: '{result.used_template_id}'. Stripping from plan.")
                    result.used_template_id = None
                
            # 2. Verify Component IDs against the Store
            verified_modules = []
            for mod_id in result.selected_module_ids:
                comp_item = store.get(("components",), mod_id)
                if comp_item:
                    verified_modules.append(mod_id)
                else:
                    # Check if they accidentally put a template ID in the module list
                    tmpl_fallback = store.get(("templates",), mod_id)
                    if tmpl_fallback:
                        pass 
                    else:
                        print(f"⚠️ Consultant Hallucinated Module ID: '{mod_id}'. Stripping from plan.")
            
            result.selected_module_ids = verified_modules

        # Detect a "Hard Reset" from the LLM (user asked to start over completely)
        is_hard_reset = (result.status == "CHATTING" and result.draft_plan == "" and len(result.selected_module_ids) == 0)

        # Prepare the baseline state updates
        state_updates = {
            "messages": [AIMessage(content=result.response_to_user)],
            "consultant_status": result.status,
            "design_plan": result.draft_plan if (result.status == "APPROVED" or is_hard_reset) else state.get("design_plan"),
            "strategy_selector": result.strategy_selector if result.status == "APPROVED" else state.get("strategy_selector", "CUSTOM_BUILD"),
            "used_template_id": result.used_template_id if (result.status == "APPROVED" or is_hard_reset) else state.get("used_template_id"),
            "selected_module_ids": result.selected_module_ids if (result.status == "APPROVED" or is_hard_reset) else state.get("selected_module_ids", []),
            "error": None
        }

        # POST-GENERATION REVISION TRIGGER
        # Wipe the old execution data so the frontend knows we are rebuilding or resetting
        if result.status == "CHATTING" or (result.status == "APPROVED" and state.get("nextflow_code")):
            state_updates["nextflow_code"] = None
            state_updates["mermaid_code"] = None
            state_updates["ast_json"] = None

        return state_updates
        
    except Exception as e:
        print(f"💥 Consultant Node Failed: {str(e)}")
        return {"error": f"Consultant Agent Failed: {str(e)}"}


def architect_node(state: GraphState):
    print("--- [NODE] ARCHITECT (Hybrid Code Generator) ---")
    if state.get("error"): return {"error": state['error']}
    
    llm = get_llm()
    architect_agent = llm.with_structured_output(NextflowPipelineAST, method="json_schema", include_raw=False)

    prompt = ChatPromptTemplate.from_messages([
        ("system", ARCHITECT_SYSTEM_PROMPT),
        ("human", "APPROVED PLAN:\n{plan}\n\nTECHNICAL CONTEXT (Available Tools & Code):\n{tech_context}")
    ])
        
    messages = prompt.invoke({
        "plan": state.get('design_plan', 'No plan provided.'),
        "tech_context": state.get('technical_context', 'No context provided.')
    }).to_messages()

    try:
        result = architect_agent.invoke(messages)
        print("[Architect] Successfully generated Hybrid AST.")
        return {
            "ast_json": result.model_dump(),
            "validation_error": None
        }
    except Exception as e:
        print(f"⚠️ Architect Validation Failed: {str(e)}")
        return {
            "validation_error": str(e),
            "retries": state.get("retries", 0) + 1
        }
    

def diagram_node(state: GraphState):
    print("--- [NODE] DIAGRAM AGENT (JSON -> Python Compiler) ---")
    if state.get("error"): return {"error": state['error']}
    
    final_code = state.get("nextflow_code", "")
    if not final_code:
        print("[Diagram] Warning: No Nextflow code found.")
        return {"mermaid_code": "flowchart TD\n    Empty[No code generated]"}

    llm = get_llm()
    diagram_agent = llm.with_structured_output(DiagramData, method="json_schema", include_raw=False)

    prompt = ChatPromptTemplate.from_messages([
        ("system", DIAGRAM_SYSTEM_PROMPT),
        ("human", "Map this Nextflow code into a JSON Node/Edge Graph:\n\n{code}")
    ])
        
    messages = prompt.invoke({"code": final_code}).to_messages()

    max_retries = 3
    for attempt in range(max_retries):
        try:
            result = diagram_agent.invoke(messages)
            
            if not result or not result.nodes:
                raise ValueError("LLM returned empty graph data.")

            mermaid_string = render_mermaid_from_json(result)
            
            print(f"[Diagram] Successfully compiled Mermaid graph on attempt {attempt + 1}.")
            return {"mermaid_code": mermaid_string}
            
        except Exception as e:
            print(f"⚠️ Diagram Data Error (Attempt {attempt + 1}): {str(e)}")
            messages.append(AIMessage(content="I generated an invalid JSON graph structure."))
            messages.append(HumanMessage(content=f"Validation Error: {str(e)}\nFix the data and try again."))
    
    return {"mermaid_code": "flowchart TD\n    Error[\"Diagram generation failed after 3 attempts. See logs for details.\"]"}
    
def filter_template_logic(code: str, allowed_components: set) -> str:
    lines = code.split('\n')
    filtered_lines = []
    
    pattern = re.compile(r'\b((?:step_|module_|multi_)[a-zA-Z0-9_]+)\s*\(')
    
    for line in lines:
        match = pattern.search(line)
        if match:
            func_name = match.group(1)
            
            if func_name not in allowed_components:
                filtered_lines.append(f"    // [REMOVED BY PLAN] {line.strip()}")
                continue
        
        filtered_lines.append(line)
        
    return "\n".join(filtered_lines)

def hydrator_node(state: GraphState, store: BaseStore):
    print("--- [NODE] HYDRATOR (Context Assembly) ---")

    if state.get("error"):
        return {"error": state["error"]}
    
    context_parts = []
    detected_helpers = set()

    strategy = state.get('strategy_selector', 'CUSTOM_BUILD')
    used_template_id = state.get('used_template_id')
    module_ids = state.get('selected_module_ids', [])
    plan_text = state.get('design_plan', '')

    # Access Data from Store
    RES_ITEM = store.get(("resources",), "helper_functions")

    RES_LIST = RES_ITEM.value.get("list", []) if RES_ITEM else []

    helper_names = [r['name'] for r in RES_LIST]

    # ==========================================
    # PATH A: STRICT TEMPLATE MODE
    # ==========================================
    if strategy == "EXACT_MATCH" and used_template_id:
        tmpl_id = used_template_id
        tmpl_item = store.get(("templates",), tmpl_id)
        template_def = tmpl_item.value if tmpl_item else None

        context_parts.append(f"### STRICT TEMPLATE MODE: {tmpl_id}")
        if template_def:
            context_parts.append(f"Description: {template_def.get('description')}")
            
            code_item = store.get(("code",), tmpl_id)

            # print("code_item", code_item)

            tmpl_code = code_item.value.get("content") if code_item else None

            # print("tmpl_code", tmpl_code)
            
            if tmpl_code:
                context_parts.append(f"[[TEMPLATE SOURCE CODE: {tmpl_id}]]")
                context_parts.append("INSTRUCTION: Use the logic in this workflow block exactly.")
                context_parts.append(f"```groovy\n{tmpl_code.strip()}\n```")
                context_parts.append(f"[[END TEMPLATE SOURCE]]")
                
                for h in helper_names:
                    if h in tmpl_code: detected_helpers.add(h)
            
            for step in template_def.get('logic_flow', []):
                if 'step' in step:
                    comp_id = step['step']
                    c_item = store.get(("code",), comp_id)
                    code = c_item.value.get("content") if c_item else None
                    if code:
                        context_parts.append(f"[[REFERENCE FOR STEP: {comp_id}]]")
                        context_parts.append(f"```groovy\n{code.strip()}\n```")
                        context_parts.append(f"[[END REFERENCE]]")
                        
                        for h in helper_names:
                            if h in code: detected_helpers.add(h)

    # ==========================================
    # PATH B: ADAPTED OR CUSTOM MODE
    # ==========================================
    else:
        if strategy == "ADAPTED_MATCH" and used_template_id:
            context_parts.append(f"### ADAPTED TEMPLATE MODE: Based on {used_template_id}")
            t_item = store.get(("code",), used_template_id)
            tmpl_code = t_item.value.get("content") if t_item else None

            if tmpl_code:
                # We combine the template ID and the new module IDs into the allowed list
                allowed_ids = set([used_template_id] + module_ids)
                
                filtered_code = filter_template_logic(tmpl_code, allowed_ids)

                context_parts.append(f"[[TEMPLATE SOURCE CODE: {used_template_id}]]")
                context_parts.append("INFO: Some steps in this template have been commented out because they are not in your Design Plan.")
                context_parts.append("INSTRUCTION: Reuse the logic that remains, but FILL THE GAPS using your new components.")
                context_parts.append(f"```groovy\n{filtered_code.strip()}\n```")
                
                for h in helper_names:
                    if h in tmpl_code: detected_helpers.add(h)        
        else:
            context_parts.append("### CUSTOM BUILD MODE")

        # We loop through the simple list of strings now
        for comp_id in module_ids:
            if comp_id == used_template_id and strategy == "ADAPTED_MATCH":
                continue

            code_item = store.get(("code",), comp_id)
            source_code = code_item.value.get("content") if code_item else None
            
            if source_code:
                context_parts.append(f"[[REFERENCE FOR STEP: {comp_id}]]")
                context_parts.append(f"Component ID: {comp_id}")
                context_parts.append(f"```groovy\n{source_code.strip()}\n```")
                context_parts.append(f"[[END REFERENCE: {comp_id}]]")
                for h in helper_names:
                    if h in source_code: detected_helpers.add(h)

    # ==========================================
    # RESOURCE INJECTION
    # ==========================================
    if plan_text and ("cross" in plan_text or "multiMap" in plan_text):
        detected_helpers.add("extractKey")
    
    if detected_helpers:
        context_parts.append("\n### AVAILABLE HELPER FUNCTIONS")
        for h_name in detected_helpers:
            res_def = next((r for r in RES_LIST if r['name'] == h_name), None)
            if res_def:
                context_parts.append(f"- {h_name}: {res_def.get('description')}")
                context_parts.append(f"  Usage: `{res_def.get('usage')}`")
                
    full_context = "\n\n".join(context_parts)
    # print(f"technical_context: {full_context}")

    return {"technical_context": full_context}