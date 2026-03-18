import re
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.messages import RemoveMessage


from app.models.ast_structure import NextflowPipelineAST
from app.services.llm import get_llm
from app.services.tools import retrieve_rag_context
from app.services.graph_state import GraphState
from app.models.consultant_structure import ConsultantOutput
from app.models.diagram_structure import MermaidOutput
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

ARCHITECT_SYSTEM_PROMPT = """You are the Principal Nextflow Developer.
Your task is to write a strict Nextflow DSL2 pipeline based on the Consultant's plan.

# GOAL
You must output a JSON object matching the NextflowPipelineAST schema.
Instead of building complex JSON logic trees, you will write RAW NEXTFLOW GROOVY CODE for the `body_code` fields.

# STRICT DSL2 & FORMATTING RULES
1. **IMPORTS ARE CRITICAL:** You MUST import every `step_...` or `multi_...` tool you use. 
   - NEVER use 'nf-core' paths. 
   - Use local paths based on the prefix: `../steps/<name>`, `../multi/<name>`, or `../functions/<name>.nf`.
2. **NO WORKFLOW WRAPPERS:** In the `body_code` for workflows and the entrypoint, DO NOT write `workflow {{ ... }}` or `main:`. The rendering engine does this automatically. Just write the inner logic (e.g., `ch_out = step_tool(inputs)`).
3. **NO LOGIC IN PROCESSES:** The `inline_processes` list is ONLY for raw bash scripts. Do not put Nextflow logic (`.cross`, `.map`) inside an inline process. Use `sub_workflows` for logic.
4. **CHANNELS & TUPLES:** Nextflow data often flows in tuples like `tuple val(meta), path(reads)`. If you use operators like `.multiMap`, handle the meta map correctly.

# STRUCTURE EXPECTATIONS
- `imports`: List the tools to include with their correct local paths.
- `globals`: Define standard params and variables used in the pipeline.
- `inline_processes`: Custom bash scripts not found in the RAG context.
- `sub_workflows`: Reusable logic blocks. Write the DSL2 logic inside `body_code`.
- `main_workflow`: The primary execution block. Write the DSL2 logic inside `body_code`.
- `entrypoint`: The trigger block. Keep it simple and just invoke the `main_workflow`.
"""

DIAGRAM_SYSTEM_PROMPT = """You are a Technical Documentation Expert.
Your ONLY job is to read a final Nextflow DSL2 script and create an extremely comprehensive, low-level Mermaid flowchart.

# STRICT MERMAID RULES
1. Output ONLY valid Mermaid code starting with `flowchart TD`. 
2. DO NOT add markdown backticks (```) around your output.
3. **Map EVERYTHING:** You must visually capture every global parameter, input channel, process call, sub-workflow, and Nextflow operator.

# VISUAL VOCABULARY (Node Shapes)
You MUST use these exact shapes to differentiate the architecture:
- **Inputs & Params:** Use stadium shapes `([])` for inputs and global variables. (e.g., `param_ref([params.reference_genome])`)
- **Processes & Workflows:** Use standard rectangles `[]` for tools and scripts. (e.g., `step_ivar[step_2AS_mapping__ivar]`)
- **Operators:** Use rhombuses `{{}}` for Nextflow data operators like `.multiMap`, `.map`, `.mix`, `.cross`, or `.branch`. (e.g., `op_multimap{{multiMap}}`)
- **Outputs:** Use cylinders `[()]` for final emitted channels. (e.g., `emit_results[(Emit: results)]`)

# DATA FLOW (Edges & Labels)
- Draw arrows `-->` to show the exact flow of data.
- **CRITICAL:** EVERY single arrow MUST have a label `|text|` showing the exact channel name or data structure being passed. 
- Example: `op_multimap -->|trAndRef.trimmed| step_ivar`
- Example: `param_ref -->|referenceCode| op_multimap`

# SCOPE (Subgraphs)
- Group the logic using Mermaid `subgraph` blocks to match the Nextflow `workflow` definitions.
- Example:
  ```mermaid
  subgraph module_covid_emergency
      op_multimap{{multiMap}}
      step_ivar[step_2AS_mapping__ivar]
  end
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

    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT (Tools & Templates):\n{context}"),
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
            
            if result.used_template_id:
                tmpl_item = store.get(("templates",), result.used_template_id)
                if not tmpl_item:
                    print(f"⚠️ Consultant Hallucinated Template ID: '{result.used_template_id}'. Stripping from plan.")
                    result.used_template_id = None
                
            verified_modules = []
            for mod_id in result.selected_module_ids:
                comp_item = store.get(("components",), mod_id)
                if comp_item:
                    verified_modules.append(mod_id)
                else:
                    tmpl_fallback = store.get(("templates",), mod_id)
                    if tmpl_fallback:
                        pass 
                    else:
                        print(f"⚠️ Consultant Hallucinated Module ID: '{mod_id}'. Stripping from plan.")
            
            result.selected_module_ids = verified_modules

        return {
            "messages": [AIMessage(content=result.response_to_user)],
            "consultant_status": result.status,
            "design_plan": result.draft_plan if result.status == "APPROVED" else state.get("design_plan"),
            "strategy_selector": result.strategy_selector if result.status == "APPROVED" else state.get("strategy_selector", "CUSTOM_BUILD"),
            "used_template_id": result.used_template_id if result.status == "APPROVED" else state.get("used_template_id"),
            "selected_module_ids": result.selected_module_ids if result.status == "APPROVED" else state.get("selected_module_ids", []),
            "error": None
        }
        
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
    print("--- [NODE] DIAGRAM AGENT (Mermaid Sync) ---")
    if state.get("error"): return {"error": state['error']}
    
    final_code = state.get("nextflow_code", "")
    
    if not final_code:
        print("[Diagram] Warning: No Nextflow code found. Skipping diagram.")
        return {"mermaid_code": "flowchart TD\n    Empty[No code generated]"}

    llm = get_llm()
    diagram_agent = llm.with_structured_output(MermaidOutput)

    prompt = ChatPromptTemplate.from_messages([
        ("system", DIAGRAM_SYSTEM_PROMPT),
        ("human", "Generate a Mermaid diagram for this final Nextflow code:\n\n{code}")
    ])
        
    messages = prompt.invoke({"code": final_code}).to_messages()

    try:
        result = diagram_agent.invoke(messages)
        print("[Diagram] Successfully generated Mermaid map.")
        return {
            "mermaid_code": result.mermaid_code
        }
    except Exception as e:
        print(f"Diagram Node Failed: {str(e)}")
        return {
            "mermaid_code": "flowchart TD\n    Error[Diagram generation failed]"
        }
    
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

            print("code_item", code_item)

            tmpl_code = code_item.value.get("content") if code_item else None

            print("tmpl_code", tmpl_code)
            
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
    print(f"technical_context: {full_context}")

    return {"technical_context": full_context}