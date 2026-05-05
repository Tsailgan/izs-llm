"""
Architect Tools — tools for the architect to verify code logic during generation.

These tools let the architect look up component source code and validate
channel connections when it needs to double-check during code generation.
Token-efficient: only used on retries, not on first attempt.
"""

from langchain_core.tools import tool
from langchain.tools import ToolRuntime
from app.services.consultant_tools import _parse_nextflow_channels


@tool
def lookup_component_code(component_id: str, runtime: ToolRuntime) -> dict:
    """Look up a component's Nextflow source code from the knowledge base.
    Use this to verify HOW a component works — its take/emit channels,
    internal logic, and connection patterns — before writing code that uses it.
    
    Args:
        component_id: The exact component or template ID (e.g. 'step_1PP_trimming__fastp')
    """
    store = runtime.store
    
    # Get metadata
    comp_item = store.get(("components",), component_id)
    tmpl_item = store.get(("templates",), component_id) if not comp_item else None
    
    if not comp_item and not tmpl_item:
        return {"error": f"'{component_id}' not found in catalog"}
    
    meta = (comp_item or tmpl_item).value
    code_item = store.get(("code",), component_id)
    code = code_item.value.get("content", "") if code_item else ""
    
    # Parse channels from actual code
    parsed = _parse_nextflow_channels(code) if code else {"takes": [], "emits": [], "partial": True}
    
    result = {
        "id": component_id,
        "type": "template" if tmpl_item else "component",
        "takes": parsed["takes"] or meta.get("input_channels", meta.get("input_types", [])),
        "emits": parsed["emits"] or meta.get("output_channels", meta.get("out", [])),
    }
    
    if code:
        # Truncate to keep context small
        result["code"] = code[:2000] + ("\n// ... (truncated)" if len(code) > 2000 else "")
    else:
        result["warning"] = "Source code not available in code store"
    
    return result


@tool
def verify_channel_connection(source_id: str, target_id: str, runtime: ToolRuntime) -> dict:
    """Quick check if two components can connect based on their emit/take channels.
    Use this to verify a specific connection before writing it in the workflow code.
    
    Args:
        source_id: The upstream component ID
        target_id: The downstream component ID
    """
    store = runtime.store
    
    for cid in (source_id, target_id):
        if not store.get(("components",), cid) and not store.get(("templates",), cid):
            return {"error": f"'{cid}' not found in catalog"}
    
    src_code_item = store.get(("code",), source_id)
    tgt_code_item = store.get(("code",), target_id)
    
    src_code = src_code_item.value.get("content", "") if src_code_item else ""
    tgt_code = tgt_code_item.value.get("content", "") if tgt_code_item else ""
    
    src_parsed = _parse_nextflow_channels(src_code)
    tgt_parsed = _parse_nextflow_channels(tgt_code)
    
    # Fallback to catalog metadata
    if not src_parsed["emits"]:
        src_meta = (store.get(("components",), source_id) or store.get(("templates",), source_id)).value
        src_parsed["emits"] = src_meta.get("output_channels", src_meta.get("out", []))
    if not tgt_parsed["takes"]:
        tgt_meta = (store.get(("components",), target_id) or store.get(("templates",), target_id)).value
        tgt_parsed["takes"] = tgt_meta.get("input_channels", tgt_meta.get("input_types", []))
    
    src_lower = {ch.lower() for ch in src_parsed["emits"]}
    tgt_lower = {ch.lower() for ch in tgt_parsed["takes"]}
    exact = src_lower & tgt_lower
    
    return {
        "source": source_id,
        "target": target_id,
        "source_emits": src_parsed["emits"],
        "target_takes": tgt_parsed["takes"],
        "exact_matches": list(exact),
        "compatible": bool(exact) or len(tgt_parsed["takes"]) == 1,
    }


ARCHITECT_TOOLS = [
    lookup_component_code,
    verify_channel_connection,
]
