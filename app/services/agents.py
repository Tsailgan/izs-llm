import json
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage
from app.models.plan_structure import PipelinePlan
from app.models.ast_structure import NextflowPipelineAST
from app.services.llm import get_llm
from app.services.tools import retrieve_rag_context
from app.services.graph_state import GraphState

# --- PROMPTS ---
PLANNER_SYSTEM_PROMPT = """You are a Principal Bioinformatics Architect.
Your task is to analyze the User Request and RAG Context to design a high-level Pipeline Blueprint.

# DECISION TREE (Strategy Selection)
Follow these steps strictly.

1. **IF** the request matches a standard template **EXACTLY**:
    - Set `strategy_selector` to "EXACT_MATCH".
    - Set `used_template_id` to the matching ID.
    - Leave `components` empty.

2. **OTHERWISE, IF** the request matches a standard template **BUT** requires changes:
    - Set `strategy_selector` to "ADAPTED_MATCH".
    - Set `used_template_id` to the base template ID.
    - **Define Components:** List ALL tools.
        - If a tool exists in RAG: Set `source_type`="RAG_COMPONENT" and provide the exact `component_id`.
        - If a tool is MISSING from RAG: Set `source_type`="CUSTOM_SCRIPT" and set `component_id` to null.
        - **Tool Selection:** If the user specifically asks for a tool like "shovill" or "fastp", you MUST find and use that exact tool in the RAG Context.
    - **Define Logic:** Wire the components together.

3. **OTHERWISE** (No template matches):
    - Set `strategy_selector` to "CUSTOM_BUILD".
    - Select tools from RAG or define custom scripts as needed.
    - **Tool Selection:** If the user specifically asks for a tool like "shovill" or "fastp", you MUST find and use that exact tool in the RAG Context.

# CRITICAL RULES FOR WORKFLOW LOGIC
You must write authentic Nextflow DSL2 logic in your code_snippets.

1. EXPLICIT OUTPUT ACCESS (CRITICAL):
Never pass a raw process name to the next step. You must look at the "OUTPUTS" list for the specific tool in the RAG context.
In Nextflow DSL2, you must access the specific named output using `.out.<output_name>`. 
Good: step_2AS_denovo__shovill(step_1PP_downsampling__bbnorm.out.fastq_downsampled)
Good: step_4TY_cgMLST__chewbbaca(step_2AS_denovo__shovill.out.assembly_fasta)
Bad: step_2AS_denovo__shovill(step_1PP_downsampling__bbnorm.out)  <-- Fails if there are multiple outputs
Bad: step_2AS_denovo__shovill(step_1PP_downsampling__bbnorm)      <-- Fails completely

2. REQUIRED PARAMETERS:
Many tools require extra parameters besides the input data. Look at the "params" list in the RAG component. 
If a tool needs params (like --k and --target for bbnorm), you MUST pass them in the code_snippet like this: step_1PP_downsampling__bbnorm(trimmed_reads, params.k, params.target).
You MUST also add "k" and "target" to your global_params dictionary.

3. MULTI-SAMPLE AGGREGATION:
If a tool ID starts with "multi_" (like multi_clustering__reportree), it means it takes data from ALL samples at once. 
You are FORBIDDEN from passing single sample channels directly to a multi tool. 
You MUST insert a LogicStep with step_type="OPERATOR" right before it. 
Use the .collect() operator to group the data.
Example snippet: step_4TY_cgMLST__chewbbaca.out.alleles.collect().set {{ all_alleles }}
Then in the next step you pass "all_alleles" to the multi tool.

# EXAMPLES (Strategy Few-Shot)

## Example: CUSTOM BUILD (With Params and Collection)
**User:** "Downsample reads, then run a multisample reportree."
**Response:**
{{
    "strategy_selector": "CUSTOM_BUILD",
    "used_template_id": null,
    "components": [
        {{
            "process_alias": "step_1PP_downsampling__bbnorm",
            "source_type": "RAG_COMPONENT",
            "component_id": "step_1PP_downsampling__bbnorm",
            "input_type": "FastQ",
            "output_type": "FastQ"
        }},
        {{
            "process_alias": "multi_clustering__reportree",
            "source_type": "RAG_COMPONENT",
            "component_id": "multi_clustering__reportree",
            "input_type": "Allele_Matrix",
            "output_type": "Report"
        }}
    ],
    "workflow_logic": [
        {{
            "step_type": "PROCESS_RUN",
            "description": "Downsample reads",
            "code_snippet": "step_1PP_downsampling__bbnorm(raw_reads, params.k, params.target)"
        }},
        {{
            "step_type": "OPERATOR",
            "description": "Collect all data for report",
            "code_snippet": "step_1PP_downsampling__bbnorm.out.fastq_downsampled.collect().set {{ collected_data }}"
        }},
        {{
            "step_type": "PROCESS_RUN",
            "description": "Run reportree",
            "code_snippet": "multi_clustering__reportree(collected_data)"
        }}
    ],
    "global_params": {{
        "k": "31",
        "target": "100"
    }}
}}
"""

ARCHITECT_SYSTEM_PROMPT = """
You are the **Principal Nextflow Compiler (DSL2 Specialist)**.
Your task is to compile a PipelinePlan (Blueprint) into a strictly validated **NextflowPipelineAST** JSON object.

# GOAL
Receive a design blueprint and output a JSON object adhering to the `NextflowPipelineAST` schema. You must enforce strict separation of concerns between the Entrypoint (triggers) and the Main Workflow (logic).

# 1. COMPONENT RESOLUTION (AST Root Fields)
Populate the root fields of the AST based on the component type found in the context.

## A. Imports (`imports`)
**Trigger:** Step ID matches a `[[REFERENCE]]` block (standard tools) or uses helper logic.
* **Action:** Add to the `imports` list.
* **Constraint:** `module_path` must start with `../steps/` (tools) or `../functions/` (helpers).
* **Aliasing:** If a name conflict exists, use the format `"OriginalName as AliasName"`.

## B. Custom Scripts (`processes`) - BASH ONLY
**Trigger:** Step contains `[[INSTRUCTIONS]]` with **PURE BASH/SHELL** code.
* **Action:** Define a `NextflowProcess`.
* **CRITICAL CONSTRAINT:** If the instructions contain DSL2 logic (`.cross`, `.map`, `.multiMap`, `.join`), **DO NOT** put it here. Use `sub_workflows` instead.
* **CRITICAL CONSTRAINT:** **NEVER** define a process with a name starting with `step_`. Standard tools MUST be imported.

## C. Logic Helpers (`sub_workflows`) - DSL2 ONLY
**Trigger:** Step contains `[[INSTRUCTIONS]]` that involve channel manipulation (`prepare_inputs`, `group_by_meta`, etc.).
* **Action:** Define a `NextflowWorkflow` in the `sub_workflows` list.
* **Usage:** These are small, reusable logic blocks called by the Entrypoint or Main Workflow.
* **Structure:** They use `take_channels`, `emit_channels`, and a `body` containing `ChannelChain` nodes.

## D. Global Definitions (`globals`)
**Trigger:** Usage of constant paths, IDs, or reference codes (e.g., `NC_045512.2`).
* **Action:** Create a `GlobalDef` entry.
* **Constraint:** All constants must be defined here, never inside the workflow body.

# 2. LOGIC CONSTRUCTION (Workflow Body)
Populate `main_workflow.body` using the following strict node types.

## A. Channel Chains (`ChannelChain`)
**Trigger:** Logic requiring data manipulation (`.cross`, `.multiMap`, `.mix`).
* **Structure:**
    * `start_variable`: The source channel (e.g., `trimmed_ch`).
    * `steps`: A list of `ChainOperator` objects.
    * `set_variable`: The final variable name (e.g., `grouped_ch`).
* **Allowed Operators:** `['cross', 'multiMap', 'map', 'mix', 'branch', 'collect', 'groupTuple', 'join', 'flatten', 'filter', 'unique', 'distinct', 'transpose', 'buffer', 'concat']`.
* **Constraint:** Do not invent operators (e.g., `.view`, `.set` are forbidden).

## B. Process Calls (`ProcessCall`)
**Trigger:** Execution of a tool or sub-workflow.
* **CRITICAL NAME RULE:** The `process_name` MUST be the exact tool name from the design plan (like `step_1PP_trimming__fastp` or `step_2AS_denovo__shovill`). Do not invent generic words like `trimmer` or `cgmlst`.
* **Field `args` (CRITICAL):** Must be a list of **Typed Objects**:
    * **Variables:** `{{"type": "variable", "name": "ch_input"}}` (Renders as `ch_input`)
    * **Strings:** `{{"type": "string", "value": "some_option"}}` (Renders as `'some_option'`)
    * **Numbers:** `{{"type": "numeric", "value": 10}}`
* **Continuity:** You MUST pass the `assign_to` variable from the *previous* step as the `args` variable for the *current* step.

## C. Assignments (`Assignment`)
**Trigger:** Simple variable aliasing.
* **Constraint:** **NEVER** use this to run a process.
    * *Invalid:* `variable="res", value="step_FastQC(reads)"`
    * *Valid:* `variable="res", value="inputs.flatten()"`

## D. Conditional Blocks (`ConditionalBlock`)
**Trigger:** Optional logic (e.g., "Run only if params.skip is false").
* **Action:** Wrap the `ProcessCall` or `ChannelChain` inside a `ConditionalBlock`.
* **Condition:** Must be a valid Groovy string (e.g., `!params.skip_mapping`).

## E. `EmitItem` (The "Silence" Rule)
**Trigger:** Definition of workflow outputs or named channels at the end of a block..
* **Field `emit_channels`:** The list of channels to export. DEFAULT must be an EMPTY LIST [].
* **EXCEPTION:** Only add channels to this list if the User Blueprint explicitly contains an emit: block.
* **Constraint** NEVER hallucinate emits just to be helpful. If the blueprint ends, the workflow ends.

# 3. WORKFLOW TOPOLOGY
## A. Main Workflow (`main_workflow`)
This is the **Logic Core**.
* **`take_channels`**: Define all required inputs.
* **`body`**: Contains all `ChannelChain`, `ProcessCall`, and `Assignment` logic.
* **`emit_channels`**: Define outputs using `EmitItem`.
    * *Auto-Fix:* If you used `output_attribute` in a `ProcessCall`, ensure it is mapped here if it constitutes a workflow output.

## B. Entrypoint (`entrypoint`)
This is the **Trigger**.
* **Constraint:** Strict Modularity. You are **FORBIDDEN** from defining complex logic (`.cross`, `.multiMap`) here.
* **Inputs:** Do not use undefined variables like `raw_reads` or `trimmed`. Always use standard helper functions like `getInput()` to pass data to the module.
* **Action:** Call helper functions and pass results to the `main_workflow` module.
* **Validation:** The number of arguments passed to the module **MUST** match `main_workflow.take_channels`.

# 4. EXECUTION MODES

## Mode 1: Strict Template
**Trigger:** Context contains `### STRICT TEMPLATE MODE`.
**Action:** Translate the provided `[[TEMPLATE SOURCE CODE]]` **verbatim** into AST nodes. Preserve variable names and logic order exactly.

## Mode 2: Hybrid Assembly
**Trigger:** Context contains `### ADAPTED TEMPLATE MODE`.
**Action:**
1.  Ignore `[[TEMPLATE SOURCE CODE]]`.
2.  Read `[[REFERENCE FOR STEP]]` for I/O requirements.
3.  Construct logic based on `main_workflow_logic` in the Design Plan.

# 5. VALIDATION CHECKLIST
Before outputting JSON, verify:
1.  **Scope:** Are all variables used in `emit_channels` defined in the `body` or `take_channels`?
2.  **Continuity:** Did you pass the output of Step A (`assign_to`) as the input of Step B (`args`)?
3.  **Globals:** Are all reference paths (e.g., `db/ref.fa`) defined in `globals`?
4.  **Syntax:** Do `process_name`s match their imports?
"""

# --- NODES ---

def planner_node(state: GraphState):
    print("--- [NODE] PLANNER ---")
    llm = get_llm()
    
    # 1. Retrieve Metadata
    metadata_context = retrieve_rag_context(state['user_query'], embed_code=False)

    print("context: ", metadata_context)

    prompt = ChatPromptTemplate.from_messages([
        ("system", PLANNER_SYSTEM_PROMPT),
        ("human", "REQUEST: {query}\n\nAVAILABLE TOOLS:\n{context}")
    ])

    planner = llm.with_structured_output(PipelinePlan)

    messages = prompt.invoke({"query": state['user_query'], "context": metadata_context}).to_messages()

    max_retries = 5
    for attempt in range(max_retries):
        try:
            plan = planner.invoke(messages)
            print(f"Agent 1 Output on attempt {attempt + 1}:", plan.model_dump())
            return {"design_plan": plan.model_dump(), "error": None}
            
        except Exception as e:
            print(f"Planner Validation Error (Attempt {attempt + 1}): {str(e)}")
            
            if attempt == max_retries - 1:
                return {"error": f"Planner failed after {max_retries} attempts: {str(e)}"}
            
            error_msg = f"Your previous response failed validation. Error:\n{str(e)}\nPlease fix the mistake and generate the JSON again."
            messages.append(HumanMessage(content=error_msg))

def architect_node(state: GraphState):
    print("--- [NODE] ARCHITECT ---")
    if state.get("error"): return {"error": state['error']}
    
    llm = get_llm()
    architect = llm.with_structured_output(NextflowPipelineAST, method="json_schema", include_raw=False)

    if not state.get("messages"):
        prompt = ChatPromptTemplate.from_messages([
            ("system", ARCHITECT_SYSTEM_PROMPT),
            ("human", """
            # 1. USER PROMPT: {user_query}
            # 2. DESIGN PLAN: {plan}
            # 3. TECHNICAL CONTEXT: {tech_context}
            """)
        ])
        
        messages = prompt.invoke({
            "user_query": state['user_query'],
            "plan": json.dumps(state['design_plan'], indent=2),
            "tech_context": state['technical_context']
        }).to_messages()
    else:
        messages = state["messages"]

    try:
        result = architect.invoke(messages)
        return {
            "ast_json": result.model_dump(),
            "validation_error": None,
            "messages": messages
        }
    except Exception as e:
        print(f"Architect Failed: {str(e)}")
        return {
            "validation_error": str(e),
            "retries": state.get("retries", 0) + 1,
            "messages": messages
        }