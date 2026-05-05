"""
Consultant Tools — LangGraph @tool functions for the consultant agent.

These tools are bound to the consultant LLM via bind_tools(), allowing it to
dynamically verify IDs, search the catalog, and inspect template logic
instead of relying solely on bulk RAG context injection.
"""

import re
from langchain_core.tools import tool, ToolRuntime
from app.core.config import settings
from app.core.loader import data_loader
from app.services.query_normalizer import (
    IGNORE_WORDS,
    build_semantic_query,
    is_discovery_query,
    normalize_query,
)


# ──────────────────────────────────────────────────────────────────────────────
# TOOL 1: Verify a component or template ID
# ──────────────────────────────────────────────────────────────────────────────

@tool
def verify_component_id(component_id: str, runtime: ToolRuntime) -> dict:
    """Verify if a component or template ID exists in the knowledge base.
    Use this to confirm an ID is real before including it in a pipeline plan.
    Returns metadata if found, or error details if not found.
    
    Args:
        component_id: The exact ID to verify (e.g. 'step_2AS_mapping__ivar' or 'module_covid_emergency')
    """
    store = runtime.store
    
    # Check components namespace
    item = store.get(("components",), component_id)
    if item:
        data = item.value
        return {
            "valid": True,
            "namespace": "component",
            "id": component_id,
            "tool": data.get("tool"),
            "domain": data.get("domain"),
            "description": data.get("description"),
            "inputs": data.get("input_channels", data.get("input_types", [])),
            "outputs": data.get("output_channels", data.get("out", [])),
        }
    
    # Check templates namespace
    item = store.get(("templates",), component_id)
    if item:
        data = item.value
        return {
            "valid": True,
            "namespace": "template",
            "id": component_id,
            "description": data.get("description"),
            "steps_used": data.get("steps_used", []),
            "input_channels": data.get("input_channels", []),
            "output_channels": data.get("output_channels", []),
        }
    
    return {"valid": False, "error": f"ID '{component_id}' not found in catalog"}


# ──────────────────────────────────────────────────────────────────────────────
# TOOL 2: Search components/templates (Full Hybrid: Keyword + FAISS)
# ──────────────────────────────────────────────────────────────────────────────

@tool
def search_components(query: str, runtime: ToolRuntime) -> list:
    """Search for available components and templates by keyword with semantic matching.
    Use this to find what tools are available for a specific bioinformatics task.
    ALWAYS call this first when the user asks about a new analysis type.
    
    Args:
        query: Search terms describing the analysis need (e.g. 'illumina trimming', 'amr resistance detection', 'nanopore assembly')
    """
    store = runtime.store
    results = []
    warnings = []
    found_ids = set()
    query_info = normalize_query(query)
    query_tokens = query_info["query_tokens"]
    clean_query = query_info["clean_query"]
    query_lower = query_info["query_lower"]
    
    EXCLUDED_TEMPLATES = settings.RAG_EXCLUDED_TEMPLATES

    if is_discovery_query(clean_query) and len(query_tokens) < 2:
        return [
            {
                "type": "meta",
                "warning": "Query is too broad for targeted search.",
                "hint": "Add organism, sequencing type, and analysis goal to refine results.",
            }
        ]

    # ── Keyword: Template Scan ──
    try:
        for tmpl in store.search(("templates",)):
            tmpl_id = tmpl.key.lower()
            tmpl_data = tmpl.value
            score = 0
            
            clean_id_words = tmpl_id.replace("module_", "").replace("_", " ").split()
            for id_word in clean_id_words:
                if len(id_word) > 3 and id_word in query_tokens and id_word not in IGNORE_WORDS:
                    score += 8
            
            for kw in tmpl_data.get('keywords', []):
                if str(kw).lower() in query_tokens:
                    score += 5
            
            for st in tmpl_data.get('compatible_seq_types', []):
                if str(st).lower().replace('_', ' ') in query_lower:
                    score += 3
            
            if score >= settings.RAG_KEYWORD_TEMPLATE_MIN_SCORE and tmpl.key not in EXCLUDED_TEMPLATES:
                found_ids.add(tmpl.key)
                results.append({
                    "id": tmpl.key,
                    "type": "template",
                    "description": tmpl_data.get("description", "")[:150],
                    "steps_used": tmpl_data.get("steps_used", []),
                    "_score": score,
                })
    except Exception as e:
        print(f"[search_components] Template scan error: {e}")

    # ── Keyword: Component Scan ──
    try:
        component_scores = {}
        for comp in store.search(("components",)):
            comp_id = comp.key.lower()
            comp_data = comp.value
            score = 0
            
            tool_name = str(comp_data.get('tool', '')).lower()
            domain_name = str(comp_data.get('domain', '')).lower()
            
            if '__' in comp_id:
                suffix = comp_id.split('__')[-1]
                for sw in suffix.split('_'):
                    if sw and len(sw) > 3 and sw in query_tokens and sw not in IGNORE_WORDS:
                        score += 50
            
            if tool_name:
                for word in re.split(r'[^a-z0-9]', tool_name):
                    if len(word) > 3 and word in query_tokens and word not in IGNORE_WORDS:
                        score += 50
            
            if domain_name:
                for part in re.split(r'[^a-z0-9]', domain_name):
                    if len(part) > 3 and part in query_tokens and part not in IGNORE_WORDS:
                        score += 5
            
            for st in comp_data.get('compatible_seq_types', []):
                for st_word in str(st).lower().replace('_', ' ').split():
                    if st_word and len(st_word) > 3 and st_word in query_tokens:
                        score += 5
            
            structural_keywords = [
                'lineage', 'denovo', 'trimming', 'mapping', 'qc', 'clustering',
                'class', 'hostdepl', 'filtering', 'typing', 'annotation',
                'pangenome', 'phylogeny', 'metagenomics', 'amr', 'plasmid',
                'polishing', 'consensus', 'alignment', 'surveillance',
            ]
            for kw in structural_keywords:
                if kw in query_tokens and kw in comp_id:
                    score += 15
            
            if score > 0:
                component_scores[comp.key] = (score, comp_data)
        
        if component_scores:
            max_score = max(s for s, _ in component_scores.values())
            threshold = max_score * settings.RAG_KEYWORD_COMPONENT_THRESHOLD
            for comp_key, (score, comp_data) in sorted(component_scores.items(), key=lambda x: x[1][0], reverse=True):
                if score >= threshold and comp_key not in found_ids:
                    found_ids.add(comp_key)
                    results.append({
                        "id": comp_key,
                        "type": "component",
                        "tool": comp_data.get("tool"),
                        "domain": comp_data.get("domain"),
                        "description": comp_data.get("description", "")[:120],
                        "inputs": comp_data.get("input_channels", comp_data.get("input_types", [])),
                        "outputs": comp_data.get("output_channels", comp_data.get("out", [])),
                        "_score": score,
                    })
    except Exception as e:
        print(f"[search_components] Component scan error: {e}")

    # ── Semantic Search (FAISS) ──
    try:
        if not data_loader.vector_store:
            warnings.append("Vector store not loaded; semantic search skipped.")
        if data_loader.vector_store:
            semantic_query = build_semantic_query(clean_query, query_tokens)
            if not semantic_query:
                warnings.append("Semantic search skipped because the query was empty after normalization.")
                semantic_query = clean_query
            
            docs_and_scores = data_loader.vector_store.similarity_search_with_score(
                semantic_query, k=settings.RAG_FAISS_K
            )
            
            if docs_and_scores:
                best_l2 = docs_and_scores[0][1]
                for doc, l2_dist in docs_and_scores:
                    if l2_dist > settings.RAG_FAISS_MAX_L2_DISTANCE:
                        continue
                    if l2_dist > (best_l2 + settings.RAG_FAISS_RELATIVE_MARGIN):
                        continue
                    
                    meta = doc.metadata
                    item_id = meta.get('id')
                    item_type = meta.get('type')
                    
                    if item_id in found_ids or item_id in EXCLUDED_TEMPLATES:
                        continue
                    
                    found_ids.add(item_id)
                    
                    if item_type == 'template':
                        tmpl_item = store.get(("templates",), item_id)
                        if tmpl_item:
                            tmpl_data = tmpl_item.value
                            results.append({
                                "id": item_id,
                                "type": "template",
                                "description": tmpl_data.get("description", "")[:150],
                                "steps_used": tmpl_data.get("steps_used", []),
                                "_score": 0,
                                "_semantic": True,
                            })
                    elif item_type == 'component':
                        comp_item = store.get(("components",), item_id)
                        if comp_item:
                            comp_data = comp_item.value
                            results.append({
                                "id": item_id,
                                "type": "component",
                                "tool": comp_data.get("tool"),
                                "domain": comp_data.get("domain"),
                                "description": comp_data.get("description", "")[:120],
                                "inputs": comp_data.get("input_channels", comp_data.get("input_types", [])),
                                "outputs": comp_data.get("output_channels", comp_data.get("out", [])),
                                "_score": 0,
                                "_semantic": True,
                            })
    except Exception as e:
        warnings.append("Semantic search failed; returning keyword matches only.")
        print(f"[search_components] FAISS search error: {e}")

    # Sort keyword hits first (by score), then semantic hits
    results.sort(key=lambda x: x.get("_score", 0), reverse=True)
    
    # Clean internal scoring fields
    for r in results:
        r.pop("_score", None)
        r.pop("_semantic", None)
    
    final_results = results[:15]
    if warnings:
        final_results.append({"type": "meta", "warnings": warnings})
    return final_results


# ──────────────────────────────────────────────────────────────────────────────
# TOOL 3: Get template logic and source code
# ──────────────────────────────────────────────────────────────────────────────

@tool
def get_template_logic(template_id: str, runtime: ToolRuntime) -> dict:
    """Fetch the detailed logic flow and source code for a specific template.
    Use this when you need to understand HOW a template works to decide
    if it can be used as EXACT_MATCH or needs ADAPTED_MATCH.
    Also use this to verify how components connect in an existing template.
    
    Args:
        template_id: The exact template ID (e.g. 'module_covid_emergency')
    """
    store = runtime.store
    tmpl = store.get(("templates",), template_id)
    if not tmpl:
        return {"error": f"Template '{template_id}' not found"}
    
    tmpl_data = tmpl.value
    code_item = store.get(("code",), template_id)
    
    result = {
        "id": template_id,
        "description": tmpl_data.get("description"),
        "logic_flow": tmpl_data.get("logic_flow", []),
        "steps_used": tmpl_data.get("steps_used", []),
        "input_channels": tmpl_data.get("input_channels", []),
        "output_channels": tmpl_data.get("output_channels", []),
        "compatible_seq_types": tmpl_data.get("compatible_seq_types", []),
    }
    
    if code_item:
        code = code_item.value.get("content", "")
        result["code_available"] = bool(code)
        # Truncate very long code to avoid context explosion
        if len(code) > 3000:
            result["code_snippet"] = code[:3000] + "\n// ... (truncated)"
        else:
            result["code_snippet"] = code
    else:
        result["code_available"] = False
        result["code_snippet"] = None
        result["warning"] = "Template code not found in the code store."
    
    return result


# ──────────────────────────────────────────────────────────────────────────────
# TOOL 4: Get component source code (for verifying connection logic)
# ──────────────────────────────────────────────────────────────────────────────

@tool
def get_component_code(component_id: str, runtime: ToolRuntime) -> dict:
    """Fetch the source code for a specific component/step.
    Use this to verify HOW a component works — its inputs, outputs, 
    and channel structure — so you can plan correct data connections.
    
    Args:
        component_id: The exact component ID (e.g. 'step_1PP_trimming__fastp')
    """
    store = runtime.store
    
    # Get metadata
    comp_item = store.get(("components",), component_id)
    if not comp_item:
        return {"error": f"Component '{component_id}' not found"}
    
    comp_data = comp_item.value
    code_item = store.get(("code",), component_id)
    
    result = {
        "id": component_id,
        "tool": comp_data.get("tool"),
        "domain": comp_data.get("domain"),
        "description": comp_data.get("description"),
        "inputs": comp_data.get("input_channels", comp_data.get("input_types", [])),
        "outputs": comp_data.get("output_channels", comp_data.get("out", [])),
        "container": comp_data.get("container"),
    }
    
    if code_item:
        code = code_item.value.get("content", "")
        result["code_available"] = bool(code)
        if len(code) > 3000:
            result["source_code"] = code[:3000] + "\n// ... (truncated)"
        else:
            result["source_code"] = code
    else:
        result["code_available"] = False
        result["source_code"] = "// Source code not available"
        result["warning"] = "Component code not found in the code store."
    
    return result


# ──────────────────────────────────────────────────────────────────────────────
# TOOL 5: Check channel compatibility between two components
# ──────────────────────────────────────────────────────────────────────────────

def _parse_nextflow_channels(code: str) -> dict:
    """Parse take: and emit: blocks from Nextflow DSL2 workflow code.
    Returns {"takes": [...], "emits": [...], "partial": bool}
    """
    takes = []
    emits = []
    partial = False
    
    if not code or not code.strip():
        return {"takes": [], "emits": [], "partial": True}
    
    # Check for truncation indicators
    if "// ... (truncated)" in code or code.strip().endswith("..."):
        partial = True
    
    # Parse take: block — lines after "take:" until "main:" or "emit:" or "}"
    take_match = re.search(
        r'\btake\s*:\s*\n(.*?)(?=\bmain\s*:|$)',
        code, re.DOTALL
    )
    if take_match:
        take_block = take_match.group(1)
        # Each non-empty, non-comment line in the take block is a channel name
        for line in take_block.strip().split('\n'):
            line = line.strip()
            if line and not line.startswith('//') and not line.startswith('*'):
                # Clean up any trailing comments
                clean = re.split(r'\s*//', line)[0].strip()
                if clean:
                    takes.append(clean)
    
    # Parse emit: block — lines after "emit:" until "}" or end
    emit_match = re.search(
        r'\bemit\s*:\s*\n(.*?)(?=\}\s*$|\bworkflow\s*\{|$)',
        code, re.DOTALL
    )
    if emit_match:
        emit_block = emit_match.group(1)
        for line in emit_block.strip().split('\n'):
            line = line.strip()
            if line and not line.startswith('//') and not line.startswith('*') and not line.startswith('}'):
                # Handle "channel_name = expression" and "channel_name" forms
                clean = re.split(r'\s*//', line)[0].strip()
                # Extract the channel name (left side of = or the whole line)
                if '=' in clean:
                    chan_name = clean.split('=')[0].strip()
                else:
                    chan_name = clean.split('.')[0].strip()  # e.g. "trimmed_out.reads" → "trimmed_out"
                if chan_name and not chan_name.startswith('}'):
                    emits.append(chan_name)
    
    return {"takes": takes, "emits": emits, "partial": partial}


def _parse_include_statements(code: str) -> list:
    """Parse 'include { step_xxx } from ...' statements from Nextflow code.
    Returns list of included component IDs.
    """
    includes = []
    if not code:
        return includes
    
    # Match: include { step_xxx } from '...'  or  include { step_xxx; step_yyy } from '...'
    for match in re.finditer(r"include\s*\{([^}]+)\}\s*from", code):
        block = match.group(1)
        for item in block.split(';'):
            item = item.strip()
            # Handle "step_xxx as alias" patterns
            name = item.split(' as ')[0].strip() if ' as ' in item else item.strip()
            # Only keep identifiers that look like step_/module_/multi_ IDs or function names
            if name and re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
                includes.append(name)
    
    return includes


@tool
def check_channel_compatibility(source_component_id: str, target_component_id: str, runtime: ToolRuntime) -> dict:
    """Check if two components can be connected by comparing output channels
    of the source with input channels of the target. Inspects actual Nextflow
    source code from the code store to detect declared channel names in
    take/emit blocks.
    
    Use this to verify data flow between consecutive pipeline steps.
    
    Args:
        source_component_id: The upstream component ID (e.g. 'step_1PP_trimming__fastp')
        target_component_id: The downstream component ID (e.g. 'step_2AS_mapping__bowtie')
    """
    store = runtime.store
    warnings = []
    
    # Load source component
    source_comp = store.get(("components",), source_component_id)
    source_tmpl = store.get(("templates",), source_component_id) if not source_comp else None
    if not source_comp and not source_tmpl:
        return {"error": f"Source '{source_component_id}' not found in catalog"}
    
    # Load target component
    target_comp = store.get(("components",), target_component_id)
    target_tmpl = store.get(("templates",), target_component_id) if not target_comp else None
    if not target_comp and not target_tmpl:
        return {"error": f"Target '{target_component_id}' not found in catalog"}
    
    # Get catalog-level channel info
    if source_comp:
        source_data = source_comp.value
        source_outputs_catalog = source_data.get("output_channels", source_data.get("out", []))
    else:
        source_data = source_tmpl.value
        source_outputs_catalog = source_data.get("output_channels", [])
    
    if target_comp:
        target_data = target_comp.value
        target_inputs_catalog = target_data.get("input_channels", target_data.get("input_types", []))
    else:
        target_data = target_tmpl.value
        target_inputs_catalog = target_data.get("input_channels", [])
    
    # Parse actual source code for precise channel info
    source_code_item = store.get(("code",), source_component_id)
    target_code_item = store.get(("code",), target_component_id)
    
    source_code = source_code_item.value.get("content", "") if source_code_item else ""
    target_code = target_code_item.value.get("content", "") if target_code_item else ""
    
    source_parsed = _parse_nextflow_channels(source_code)
    target_parsed = _parse_nextflow_channels(target_code)
    
    if source_parsed["partial"]:
        warnings.append(f"Source '{source_component_id}' code may be partial/truncated — channel analysis may be incomplete")
    if target_parsed["partial"]:
        warnings.append(f"Target '{target_component_id}' code may be partial/truncated — channel analysis may be incomplete")
    if not source_code:
        warnings.append(f"No source code found for '{source_component_id}' — using catalog metadata only")
    if not target_code:
        warnings.append(f"No source code found for '{target_component_id}' — using catalog metadata only")
    
    # Use parsed channels if available, fall back to catalog
    source_emits = source_parsed["emits"] if source_parsed["emits"] else source_outputs_catalog
    target_takes = target_parsed["takes"] if target_parsed["takes"] else target_inputs_catalog
    
    # Check compatibility: look for matching or compatible channel names
    source_emit_lower = {ch.lower() for ch in source_emits}
    target_take_lower = {ch.lower() for ch in target_takes}
    
    exact_matches = source_emit_lower & target_take_lower
    
    # Fuzzy match: check if channel types are semantically compatible
    # e.g. "trimmed" output → "reads" input (common pattern)
    READ_COMPATIBLE = {"reads", "rawreads", "trimmed", "fastq", "filtered"}
    ASSEMBLY_COMPATIBLE = {"assembly", "contigs", "scaffolds", "consensus"}
    
    fuzzy_matches = []
    for s_ch in source_emit_lower:
        for t_ch in target_take_lower:
            if s_ch == t_ch:
                continue
            if (s_ch in READ_COMPATIBLE and t_ch in READ_COMPATIBLE) or \
               (s_ch in ASSEMBLY_COMPATIBLE and t_ch in ASSEMBLY_COMPATIBLE):
                fuzzy_matches.append({"source_emit": s_ch, "target_take": t_ch, "reason": "type-compatible"})
    
    compatible = bool(exact_matches) or bool(fuzzy_matches) or (len(source_emits) > 0 and len(target_takes) > 0 and len(target_takes) == 1)
    
    if not compatible and len(target_takes) == 1:
        warnings.append(f"Target takes a single channel '{target_takes[0]}' — may accept any upstream output by convention")
        compatible = True
    
    return {
        "compatible": compatible,
        "source_id": source_component_id,
        "target_id": target_component_id,
        "source_emits": source_emits,
        "target_takes": target_takes,
        "exact_matches": list(exact_matches),
        "fuzzy_matches": fuzzy_matches,
        "warnings": warnings,
    }


# ──────────────────────────────────────────────────────────────────────────────
# TOOL 6: Validate a complete pipeline plan
# ──────────────────────────────────────────────────────────────────────────────

@tool
def check_plan_logic(component_ids: list, template_id: str, runtime: ToolRuntime) -> dict:
    """Validate a proposed pipeline plan by checking:
    1. All component IDs exist in the catalog
    2. Channel flow is consistent between consecutive steps
    3. If a template is referenced, compare the plan against the template's declared steps
    4. Parse template source code to detect include statements and find missing components
    
    Call this BEFORE finalizing any APPROVED plan to catch issues early.
    Pass template_id as empty string "" if no template is used.
    
    Args:
        component_ids: List of component IDs in proposed execution order (e.g. ['step_1PP_trimming__fastp', 'step_2AS_mapping__bowtie'])
        template_id: Template ID to compare against, or empty string if none
    """
    store = runtime.store
    issues = []
    warnings = []
    
    if not component_ids:
        return {
            "valid": False,
            "issues": ["No component IDs provided"],
            "warnings": [],
        }
    
    # 1. Batch-validate all IDs exist
    valid_ids = []
    invalid_ids = []
    for comp_id in component_ids:
        comp = store.get(("components",), comp_id)
        tmpl = store.get(("templates",), comp_id) if not comp else None
        if comp or tmpl:
            valid_ids.append(comp_id)
        else:
            invalid_ids.append(comp_id)
            issues.append(f"Component '{comp_id}' not found in catalog")
    
    # 2. Check channel flow between consecutive pairs
    channel_report = []
    for i in range(len(valid_ids) - 1):
        src_id = valid_ids[i]
        tgt_id = valid_ids[i + 1]
        
        # Get channel info from catalog
        src_comp = store.get(("components",), src_id)
        tgt_comp = store.get(("components",), tgt_id)
        
        src_outputs = []
        tgt_inputs = []
        
        if src_comp:
            src_data = src_comp.value
            src_outputs = src_data.get("output_channels", src_data.get("out", []))
        else:
            src_tmpl = store.get(("templates",), src_id)
            if src_tmpl:
                src_outputs = src_tmpl.value.get("output_channels", [])
        
        if tgt_comp:
            tgt_data = tgt_comp.value
            tgt_inputs = tgt_data.get("input_channels", tgt_data.get("input_types", []))
        else:
            tgt_tmpl = store.get(("templates",), tgt_id)
            if tgt_tmpl:
                tgt_inputs = tgt_tmpl.value.get("input_channels", [])
        
        # Parse actual code for precise channel info
        src_code_item = store.get(("code",), src_id)
        tgt_code_item = store.get(("code",), tgt_id)
        
        src_code = src_code_item.value.get("content", "") if src_code_item else ""
        tgt_code = tgt_code_item.value.get("content", "") if tgt_code_item else ""
        
        src_parsed = _parse_nextflow_channels(src_code)
        tgt_parsed = _parse_nextflow_channels(tgt_code)
        
        effective_outputs = src_parsed["emits"] if src_parsed["emits"] else src_outputs
        effective_inputs = tgt_parsed["takes"] if tgt_parsed["takes"] else tgt_inputs
        
        if src_parsed["partial"] or tgt_parsed["partial"]:
            warnings.append(f"Code for '{src_id}' → '{tgt_id}' may be partial — channel analysis approximate")
        
        pair_info = {
            "source": src_id,
            "target": tgt_id,
            "source_emits": effective_outputs,
            "target_takes": effective_inputs,
        }
        
        if not effective_outputs:
            warnings.append(f"No output channels detected for '{src_id}' — cannot verify connection to '{tgt_id}'")
        elif not effective_inputs:
            warnings.append(f"No input channels detected for '{tgt_id}' — cannot verify connection from '{src_id}'")
        else:
            # Check for any overlap
            out_lower = {ch.lower() for ch in effective_outputs}
            in_lower = {ch.lower() for ch in effective_inputs}
            if not (out_lower & in_lower):
                pair_info["mismatch"] = True
                warnings.append(
                    f"Channel mismatch: '{src_id}' emits {effective_outputs} "
                    f"but '{tgt_id}' takes {effective_inputs} — may need channel adaptation"
                )
        
        channel_report.append(pair_info)
    
    # 3. Template comparison
    template_coverage = None
    if template_id:
        tmpl_item = store.get(("templates",), template_id)
        if not tmpl_item:
            issues.append(f"Template '{template_id}' not found in catalog")
        else:
            tmpl_data = tmpl_item.value
            tmpl_steps = set(tmpl_data.get("steps_used", []))
            plan_steps = set(component_ids)
            
            missing_from_plan = tmpl_steps - plan_steps
            extra_in_plan = plan_steps - tmpl_steps
            
            # Also check include statements in template source code
            code_item = store.get(("code",), template_id)
            includes_from_code = []
            if code_item:
                tmpl_code = code_item.value.get("content", "")
                includes_from_code = _parse_include_statements(tmpl_code)
                
                # Filter to only step_/module_/multi_ prefixed includes
                code_steps = {inc for inc in includes_from_code 
                             if inc.startswith(("step_", "module_", "multi_"))}
                
                # Steps referenced in code but not in catalog steps_used
                code_only = code_steps - tmpl_steps
                if code_only:
                    warnings.append(
                        f"Template code includes {list(code_only)} which are not in "
                        f"the template's 'steps_used' metadata — may be helper dependencies"
                    )
                
                # Steps in code but missing from the plan
                code_missing = code_steps - plan_steps
                if code_missing:
                    warnings.append(
                        f"Template code references {list(code_missing)} which are "
                        f"not in your plan — verify these aren't needed"
                    )
            else:
                warnings.append(f"No source code found for template '{template_id}' — include analysis skipped")
            
            template_coverage = {
                "template_id": template_id,
                "template_steps": list(tmpl_steps),
                "plan_steps": list(plan_steps),
                "missing_from_plan": list(missing_from_plan),
                "extra_in_plan": list(extra_in_plan),
                "code_includes": includes_from_code,
            }
            
            if missing_from_plan:
                warnings.append(
                    f"Plan is missing template steps: {list(missing_from_plan)} — "
                    f"these may be needed for correct pipeline logic"
                )
    
    is_valid = len(issues) == 0
    
    result = {
        "valid": is_valid,
        "checked_ids": len(component_ids),
        "valid_ids": valid_ids,
        "invalid_ids": invalid_ids,
        "channel_flow": channel_report,
        "issues": issues,
        "warnings": warnings,
    }
    
    if template_coverage:
        result["template_coverage"] = template_coverage
    
    return result


# ──────────────────────────────────────────────────────────────────────────────
# EXPORT: Tool list for ToolNode registration
# ──────────────────────────────────────────────────────────────────────────────

CONSULTANT_TOOLS = [
    verify_component_id,
    search_components,
    get_template_logic,
    get_component_code,
    check_channel_compatibility,
    check_plan_logic,
]
