import json
import re
from app.core.loader import data_loader
from app.services.graph_state import GraphState

from langgraph.store.base import BaseStore

def _inject_component(comp_id, found_ids, context_blocks, store: BaseStore, embed_code=True):
    if comp_id in found_ids: return
    
    comp_item = store.get(("components",), comp_id)
    if not comp_item: return
    comp_data = comp_item.value

    found_ids.add(comp_id)
    
    code_item = store.get(("code",), comp_id)
    code_snippet = code_item.value.get("content", "// Code not found") if code_item else "// Code not found in repository"

    block = f"""
--- COMPONENT: {comp_id} ---
TOOL: {comp_data.get('tool')}
DESCRIPTION: {comp_data.get('description')}
CONTAINER: {comp_data.get('container')}
INPUTS: {', '.join(comp_data.get('input_types', []))}
OUTPUTS: {', '.join(comp_data.get('out', []))}
"""

    if embed_code:
        block += f"\n**SOURCE CODE ({comp_id}.nf):**\n```groovy\n{code_snippet}\n```\n"

    context_blocks.append(block)

def _inject_template(template_id, found_ids, context_blocks, store: BaseStore, embed_code=True):
    if template_id in found_ids: return
    
    tmpl_item = store.get(("templates",), template_id)
    if not tmpl_item: return

    found_ids.add(template_id)

    block = ""

    if embed_code:
        code_item = store.get(("code",), template_id)
        code_snippet = code_item.value.get("content", "// Code not found") if code_item else "// Code not found in repository"
        block += f"\n**SOURCE CODE ({template_id}.nf):**\n```groovy\n{code_snippet}\n```\n"

    context_blocks.append(block)

def retrieve_rag_context(user_query, store: BaseStore, embed_code=False):
    """Retrieves similar documents from Vector Store."""
    if not data_loader.vector_store:
        return "Vector Store not loaded."
    
    docs = data_loader.vector_store.similarity_search(user_query, k=10)

    print(docs)

    found_ids = set()
    context_blocks = []
    
    for doc in docs:
        meta = doc.metadata
        item_id = meta.get('id')
        item_type = meta.get('type')

        # Deduplicate at document level
        if item_id in found_ids:
            continue

        # --- PATH 1: TEMPLATE (Pipeline Blueprint) ---
        if item_type == 'template':
            tmpl_item = store.get(("templates",), item_id)
            if tmpl_item:
                tmpl = tmpl_item.value
                context_blocks.append(f"### PIPELINE BLUEPRINT: {item_id}\n{doc.page_content}")
                _inject_template(tmpl['id'], found_ids, context_blocks, store, embed_code=True)

            found_ids.add(item_id)

            # Recursive Expansion: Fetch all children components
            for flow_step in tmpl.get('logic_flow', []):

                # Direct Steps
                if 'step' in flow_step:
                    _inject_component(flow_step['step'], found_ids, context_blocks, store, embed_code)

                # Complex Logic (Parallel/Branching/Next)
                for sub_key in ['parallel_execution', 'branches', 'options']:
                    if sub_key in flow_step:
                        for item in flow_step[sub_key]:
                            if 'step' in item:
                                _inject_component(item['step'], found_ids, context_blocks, store, embed_code)

                            # Handle 'next' chaining
                            if 'next' in item:
                                for sub_item in item['next']:
                                    if 'step' in sub_item:
                                        _inject_component(sub_item['step'], found_ids, context_blocks, store, embed_code)

        # --- PATH 2: COMPONENT (Direct Hit) ---
        elif item_type == 'component':
            # Always embed code for direct hits too
            _inject_component(item_id, found_ids, context_blocks, store, embed_code)

    final_context = "\n".join(context_blocks) + "\n\n"

    return final_context

def hydrator_node(state: GraphState, store: BaseStore):
    print("--- [NODE] HYDRATOR (Context Assembly) ---")

    if state.get("error"):
        return {"error": state["error"]}
    
    # Extract the plan 
    plan = state['design_plan']

    context_parts = []
    detected_helpers = set()

    # Extract Plan Fields
    strategy = plan.get('strategy_selector', 'CUSTOM_BUILD')
    used_template_id = plan.get('used_template_id')
    components = plan.get('components', [])
    workflow_logic = plan.get('workflow_logic', [])

    # Access Store
    RES_ITEM = store.get(("resources",), "helper_functions")
    RES_LIST = RES_ITEM.value.get("list", []) if RES_ITEM else []
    HELPER_NAMES = {r['name'] for r in RES_LIST}

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
            
            # 1. Get Template Source
            code_item = store.get(("code",), tmpl_id)
            tmpl_code = code_item.value.get("content") if code_item else None
            if tmpl_code:
                context_parts.append(f"[[TEMPLATE SOURCE CODE: {tmpl_id}]]")
                context_parts.append("INSTRUCTION: Use the logic in this workflow block exactly.")
                context_parts.append(f"```groovy\n{tmpl_code.strip()}\n```")
                context_parts.append(f"[[END TEMPLATE SOURCE]]")
                
                for h in HELPER_NAMES:
                    if h in tmpl_code: detected_helpers.add(h)
            
            # 2. Get Dependencies (Reference Tools inside the template)
            for step in template_def.get('logic_flow', []):
                if 'step' in step:
                    comp_id = step['step']
                    c_item = store.get(("code",), comp_id)
                    code = c_item.value.get("content") if c_item else None
                    if code:
                        context_parts.append(f"[[REFERENCE FOR STEP: {comp_id}]]")
                        context_parts.append(f"```groovy\n{code.strip()}\n```")
                        context_parts.append(f"[[END REFERENCE]]")
                        
                        for h in HELPER_NAMES:
                            if h in code: detected_helpers.add(h)

    # ==========================================
    # PATH B: CUSTOM ASSEMBLY MODE
    # ==========================================
    else:
        # 1. Handle Template Inheritance (Adapted Mode)
        if strategy == "ADAPTED_MATCH" and used_template_id:
            context_parts.append(f"### ADAPTED TEMPLATE MODE: Based on {used_template_id}")
            t_item = store.get(("code",), used_template_id)
            tmpl_code = t_item.value.get("content") if t_item else None

            if tmpl_code:
                allowed_ids = {used_template_id}
                
                for comp in components:
                    if comp.get('component_id'): 
                        allowed_ids.add(comp.get('component_id'))
                    if comp.get('process_alias'):
                        allowed_ids.add(comp.get('process_alias'))
                
                filtered_code = filter_template_logic(tmpl_code, allowed_ids)

                context_parts.append(f"[[TEMPLATE SOURCE CODE: {used_template_id}]]")
                context_parts.append("INFO: Some steps in this template have been commented out because they are not in your Design Plan.")
                context_parts.append("INSTRUCTION: Reuse the logic that remains, but FILL THE GAPS using your new components.")
                context_parts.append(f"```groovy\n{filtered_code.strip()}\n```")
                
                for h in HELPER_NAMES:
                    if h in tmpl_code: detected_helpers.add(h)        
        else:
            context_parts.append("### CUSTOM BUILD MODE")

        for comp in components:
            step_alias = comp.get('process_alias')
            source_type = comp.get('source_type')
            
            if source_type == "RAG_COMPONENT":
                comp_id = comp.get('component_id')

                if comp_id == used_template_id and strategy == "ADAPTED_MATCH":
                    continue

                code_item = store.get(("code",), comp_id)
                source_code = code_item.value.get("content") if code_item else None
                
                if source_code:
                    context_parts.append(f"[[REFERENCE FOR STEP: {step_alias}]]")
                    context_parts.append(f"Component ID: {comp_id}")
                    context_parts.append(f"```groovy\n{source_code.strip()}\n```")
                    context_parts.append(f"[[END REFERENCE: {step_alias}]]")
                    for h in HELPER_NAMES:
                        if h in source_code: detected_helpers.add(h)
            
            elif source_type == "CUSTOM_SCRIPT":

                # We provide instructions so the Agent 2 can write the script.
                description = comp.get('source_description', 'No description provided.')
                
                context_parts.append(f"[[INSTRUCTIONS FOR STEP: {step_alias}]]")
                context_parts.append("INSTRUCTION: Create a new Nextflow code for this logic.")
                context_parts.append(f"Requirement: {description}")
                context_parts.append(f"[[END INSTRUCTIONS: {step_alias}]]")
                pass

    # ==========================================
    # RESOURCE INJECTION
    # ==========================================
    plan_str = json.dumps(plan)
    if "cross" in plan_str or "multiMap" in plan_str:
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