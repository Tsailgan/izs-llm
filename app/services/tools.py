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
    
    docs = data_loader.vector_store.similarity_search(user_query, k=15)

    # print(docs)

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