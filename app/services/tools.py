import json
import re
from app.core.loader import data_loader
from app.services.graph_state import GraphState
from collections import defaultdict

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
TOOL: {comp_data.get('tool', 'Unknown')}
DOMAIN: {comp_data.get('domain', 'Unknown')}
DESCRIPTION: {comp_data.get('description', 'No description')}
CONTAINER: {comp_data.get('container', 'None')}
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
    tmpl_data = tmpl_item.value

    block = f"""
--- TEMPLATE: {template_id} ---
NAME: {tmpl_data.get('template_name', 'Unknown')}
DESCRIPTION: {tmpl_data.get('description', 'No description')}
COMPATIBLE SQS: {', '.join(tmpl_data.get('compatible_seq_types', []))}
INPUTS: {', '.join(tmpl_data.get('accepted_inputs', []))}
OUTPUTS: {', '.join(tmpl_data.get('outputs', []))}
"""

    if embed_code:
        code_item = store.get(("code",), template_id)
        code_snippet = code_item.value.get("content", "// Code not found") if code_item else "// Code not found in repository"
        block += f"\n**SOURCE CODE ({template_id}.nf):**\n```groovy\n{code_snippet}\n```\n"

    context_blocks.append(block)

def retrieve_rag_context(user_query, store: BaseStore, embed_code=False):
    """Retrieves context using a Hybrid Approach: Keyword/Metadata Matching + FAISS Semantic Search."""
    if not data_loader.vector_store:
        return "Vector Store not loaded."
    
    found_ids = set()
    context_blocks = []
    query_lower = user_query.lower()

    # ==========================================
    # 0. DISCOVERY / SUGGESTION INTENT
    # ==========================================
    clean_query = query_lower.strip()
    is_discovery = False
    
    # 1. Very short generic queries
    if len(clean_query) < 15 and clean_query != "":
        is_discovery = True
        
    # 2. Strong conversational multi-word phrases
    strong_phrases = [
        "what can i", "what can you do", "what do you have", "what do we have", 
        "what tools", "which tools", "what pipelines", "what modules", 
        "what's supported", "what is supported", "available options", 
        "available tools", "available pipelines", "system capabilities"
    ]
    if not is_discovery and any(p in clean_query for p in strong_phrases):
        is_discovery = True
        
    # 3. Contextual Combinations (Verb/Noun pairing)
    # Prevents lone words like "list" or "search" from triggering a massive catalog dump
    action_words = ["suggest", "list", "show", "recommend", "overview", "catalog", "options", "give", "help"]
    target_nouns = ["tool", "tools", "pipeline", "pipelines", "module", "modules", "capability", "capabilities", "system"]
    
    if not is_discovery:
        has_action = any(re.search(rf'\b{v}\b', clean_query) for v in action_words)
        has_target = any(re.search(rf'\b{n}\b', clean_query) for n in target_nouns)
        if has_action and has_target:
            is_discovery = True

    # If the user query is determined to be exploring the catalog, inject the capability map
    if is_discovery:
        try:
            suggestion_block = "### SYSTEM CATALOG OVERVIEW (For user suggestions)\n"
            suggestion_block += "The user's query implies they want to know what is available or need a suggestion. Use this capabilities map to suggest tools that generate specific reports or outputs.\n\n"
            suggestion_block += "**Available Pipelines (Templates):**\n"
            
            for tmpl in store.search(("templates",)):
                t_data = tmpl.value
                t_name = t_data.get('template_name', tmpl.key)
                t_desc = t_data.get('description', 'No description.')
                short_desc = t_desc.split('.')[0] + '.' if '.' in t_desc else (t_desc[:100] + ("..." if len(t_desc) > 100 else ""))
                outputs = t_data.get('outputs', [])
                out_str = f"*(Generates: {', '.join(outputs)})*" if outputs else "*(No primary outputs defined)*"
                suggestion_block += f"- **{t_name}**: {short_desc} {out_str}\n"
            
            domain_groups = defaultdict(list)
            for comp in store.search(("components",)):
                c_data = comp.value
                tool_name = c_data.get("tool")
                domain = c_data.get("domain", "Other")
                c_desc = c_data.get("description", "")
                short_desc = c_desc.split('.')[0] + '.' if '.' in c_desc else (c_desc[:100] + ("..." if len(c_desc) > 100 else ""))
                
                outputs = c_data.get("out", [])
                out_str = f"*(Outputs: {', '.join(outputs)})*" if outputs else "*(No primary outputs defined)*"
                
                if tool_name and str(tool_name).strip() and str(tool_name).lower() != "none":
                    formatted_tool = f"**{str(tool_name).strip()}**: {short_desc} {out_str}"
                    domain_groups[domain].append(formatted_tool)
            
            if domain_groups:
                suggestion_block += "\n**Supported Individual Tools (Grouped by Domain):**\n"
                for domain_name, tools_list in sorted(domain_groups.items()):
                    suggestion_block += f"\n*{domain_name}:*\n"
                    # Remove exact duplicates that might arise from formatting
                    for tool_item in sorted(list(set(tools_list))):
                        suggestion_block += f"- {tool_item}\n"
            
            suggestion_block += "\nUse this capabilities map explicitly to answer questions about what reports/outputs are generated or what tools are available.\n"
            context_blocks.append(suggestion_block)
        except Exception as e:
            print(f"Catalog suggestion error: {e}")

    # ==========================================
    # 1. HYBRID KEYWORD & METADATA SEARCH
    # ==========================================
    ignore_words = {
        'step', 'mapping', 'module', 'genes', 'denovo', 'assembly', 'tool', 
        'pipeline', 'workflow', 'build', 'create', 'make', 'run', 'using',
        'file', 'data', 'reads', 'fastq', 'fasta', 'generate', 'process',
        'custom', 'script', 'and', 'plus', 'with'
    }
    # Tokenize query into a set of whole words to prevent substring false positives
    # e.g. "not illumina" will not match "illumina" correctly with `in` substring check
    query_tokens = set(re.findall(r'\b\w+\b', query_lower))

    # --- SCAN TEMPLATES ---
    try:
        template_scores = {}
        for tmpl in store.search(("templates",)):
            tmpl_id = tmpl.key.lower()
            tmpl_data = tmpl.value
            
            tmpl_name = str(tmpl_data.get('name', tmpl_data.get('template_name', ''))).lower()
            keywords = [str(k).lower() for k in tmpl_data.get('keywords', [])]
            seq_types = [str(s).lower() for s in tmpl_data.get('compatible_seq_types', [])]
            inputs = [str(i).lower() for i in tmpl_data.get('accepted_inputs', [])]
            outputs = [str(o).lower() for o in tmpl_data.get('outputs', [])]
            params = [str(p).lower() for p in tmpl_data.get('params', [])]
            
            score = 0
            
            # Word-by-word ID scoring (e.g. 'covid' alone matches 'module_covid_emergency')
            clean_id_words = tmpl_id.replace("module_", "").replace("_", " ").split()
            for id_word in clean_id_words:
                if len(id_word) > 3 and id_word in query_tokens and id_word not in ignore_words:
                    score += 8
                
            for kw in keywords:
                if kw and len(kw) > 3 and kw in query_tokens:
                    score += 5
            
            for st in seq_types:
                for st_word in st.replace('_', ' ').split():
                    if st_word and len(st_word) > 3 and st_word in query_tokens:
                        score += 3
            
            for io_val in inputs + outputs:
                for io_word in io_val.replace('_', ' ').split():
                    if len(io_word) > 3 and io_word in query_tokens and io_word not in ignore_words:
                        score += 5
            
            for param in params:
                clean_param = param.replace('-', '')
                if len(clean_param) > 3 and clean_param in query_tokens and clean_param not in ignore_words:
                    score += 1

            if score > 0:
                template_scores[tmpl.key] = score
                
        # Sort and inject top 2 scoring templates
        sorted_tmpls = sorted(template_scores.items(), key=lambda x: x[1], reverse=True)[:2]
        for tmpl_key, t_score in sorted_tmpls:
            # Guard: only add header if template hasn't already been injected
            if tmpl_key not in found_ids:
                context_blocks.append(f"### PIPELINE BLUEPRINT (Score {t_score}): {tmpl_key}")
            _inject_template(tmpl_key, found_ids, context_blocks, store, embed_code=True)
            
            tmpl_data = store.get(("templates",), tmpl_key).value
            for flow_step in tmpl_data.get('logic_flow', []):
                if 'step' in flow_step: 
                    _inject_component(flow_step['step'], found_ids, context_blocks, store, embed_code)
                for sub_key in ['parallel_execution', 'branches', 'options']:
                    if sub_key in flow_step:
                        for item in flow_step[sub_key]:
                            if 'step' in item: _inject_component(item['step'], found_ids, context_blocks, store, embed_code)
                            if 'next' in item:
                                for sub_item in item['next']:
                                    if 'step' in sub_item: _inject_component(sub_item['step'], found_ids, context_blocks, store, embed_code)
    except Exception as e:
        print(f"Template hybrid search error: {e}")

    # --- SCAN COMPONENTS ---
    try:
        component_scores = {}
        for comp in store.search(("components",)):
            comp_id = comp.key.lower()
            comp_data = comp.value
            
            tool_name = str(comp_data.get('tool', '')).lower()
            domain_name = str(comp_data.get('domain', '')).lower()
            seq_types = [str(s).lower() for s in comp_data.get('compatible_seq_types', [])]
            inputs = [str(i).lower() for i in comp_data.get('input_types', [])]
            outputs = [str(o).lower() for o in comp_data.get('out', [])]
            params = [str(p).lower() for p in comp_data.get('params', [])]
            
            score = 0
            
            # Check 1: Suffix/ID words (e.g., step_4TY_lineage__westnile -> 'westnile')
            if '__' in comp_id:
                suffix = comp_id.split('__')[-1]
                for sw in suffix.split('_'):
                    if sw and len(sw) > 3 and sw in query_tokens and sw not in ignore_words:
                        score += 10

            # Check 2: Break down complex tool names (tokenized)
            if tool_name:
                for word in re.split(r'[^a-z0-9]', tool_name):
                    if len(word) > 3 and word in query_tokens and word not in ignore_words:
                        score += 10
                        
            # Check 3: Domain match (tokenized per word)
            if domain_name:
                for part in re.split(r'[^a-z0-9]', domain_name):
                    if len(part) > 3 and part in query_tokens and part not in ignore_words:
                        score += 3

            # Check 4: Compatible Sequence Types (tokenized)
            for st in seq_types:
                for st_word in st.replace('_', ' ').split():
                    if st_word and len(st_word) > 3 and st_word in query_tokens:
                        score += 3
                        
            # Check 5: Precise Inputs or Outputs match (tokenized)
            for io_val in inputs + outputs:
                for io_word in io_val.replace('_', ' ').split():
                    if len(io_word) > 3 and io_word in query_tokens and io_word not in ignore_words:
                        score += 5
            
            # Check 6: Parameters Match (tokenized)
            for param in params:
                clean_param = param.replace('-', '')
                if len(clean_param) > 3 and clean_param in query_tokens and clean_param not in ignore_words:
                    score += 1

            # Check 7: Structural keyword in ID
            if 'lineage' in query_tokens and 'lineage' in comp_id:
                score += 5
                    
            if score > 0:
                component_scores[comp.key] = score
                
        # Sort and inject top 5 scoring individual components
        sorted_comps = sorted(component_scores.items(), key=lambda x: x[1], reverse=True)[:5]
        for comp_key, c_score in sorted_comps:
            _inject_component(comp_key, found_ids, context_blocks, store, embed_code)
            
    except Exception as e:
        print(f"Component hybrid search error: {e}")

    # --- SCAN RESOURCES (Helper Functions) — Scored Top-3 ---
    try:
        res_item = store.get(("resources",), "helper_functions")
        if res_item and isinstance(res_item.value, dict):
            helpers = res_item.value.get("list", [])
            resource_scores = {}
            for i, helper in enumerate(helpers):
                h_name = str(helper.get("name", ""))
                h_score = 0
                
                # Direct full-name match (highest signal)
                if h_name and h_name.lower() in query_tokens:
                    h_score += 10
                
                # Break camelCase into tokens and match each word
                h_words = set(re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)', h_name))
                h_words = {w.lower() for w in h_words if len(w) > 3 and w.lower() not in ignore_words}
                for w in h_words:
                    if w in query_tokens:
                        h_score += 5
                
                if h_score > 0:
                    resource_scores[i] = (h_score, helper)
            
            # Inject top 3 highest-scoring helper functions
            top_resources = sorted(resource_scores.values(), key=lambda x: x[0], reverse=True)[:5]
            for _, helper in top_resources:
                context_blocks.append(
                    f"### GROOVY HELPER FUNCTION: {helper.get('name')}\n"
                    f"DESCRIPTION: {helper.get('description')}\n"
                    f"USAGE: `{helper.get('usage')}`\n"
                    f"DEFINED IN: {helper.get('path')}\n"
                )
    except Exception as e:
        print(f"Resource search error: {e}")

    # --- SCAN CONTAINERS (from catalog_part3 resources) ---
    try:
        containers_item = store.get(("resources",), "containers")
        if containers_item and isinstance(containers_item.value, dict):
            containers = containers_item.value.get("list", [])
            matched_containers = []
            for container in containers:
                c_name = str(container.get("name", "")).lower()
                if c_name and len(c_name) > 2 and c_name in query_tokens:
                    matched_containers.append(container)
            
            if matched_containers:
                container_block = "### DOCKER CONTAINER REGISTRY LOOKUP\n"
                for c in matched_containers:
                    container_block += f"- **{c.get('name')}**: `{c.get('url')}`\n"
                context_blocks.append(container_block)
    except Exception as e:
        print(f"Container search error: {e}")


    # ==========================================
    # 2. SEMANTIC SEARCH (FAISS)
    # ==========================================
    try:
        # Get distances along with docs
        docs_and_scores = data_loader.vector_store.similarity_search_with_score(user_query, k=10)
    except Exception as e:
        docs_and_scores = []
        print(f"FAISS search err: {e}")
        
    for doc, l2_dist in docs_and_scores:
        # Strict Semantic Filter: FAISS L2 distance cutoff
        # (Lower L2 distance means higher cosine similarity/closer match)
        if l2_dist > 1.3:
            continue
            
        meta = doc.metadata
        item_id = meta.get('id')
        item_type = meta.get('type')

        if item_id in found_ids:
            continue

        if item_type == 'template':
            tmpl_item = store.get(("templates",), item_id)
            if tmpl_item:
                tmpl = tmpl_item.value
                context_blocks.append(f"### PIPELINE BLUEPRINT (Semantic Match): {item_id}\n{doc.page_content}")
                _inject_template(tmpl['id'], found_ids, context_blocks, store, embed_code=True)

                found_ids.add(item_id)

                # Recursive Expansion
                for flow_step in tmpl.get('logic_flow', []):
                    if 'step' in flow_step:
                        _inject_component(flow_step['step'], found_ids, context_blocks, store, embed_code)
                    for sub_key in ['parallel_execution', 'branches', 'options']:
                        if sub_key in flow_step:
                            for item in flow_step[sub_key]:
                                if 'step' in item:
                                    _inject_component(item['step'], found_ids, context_blocks, store, embed_code)
                                if 'next' in item:
                                    for sub_item in item['next']:
                                        if 'step' in sub_item:
                                            _inject_component(sub_item['step'], found_ids, context_blocks, store, embed_code)

        elif item_type == 'component':
            _inject_component(item_id, found_ids, context_blocks, store, embed_code)

    final_context = "\n".join(context_blocks) + "\n\n"

    return final_context