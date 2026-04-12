"""
tests/test_recreation.py
Level 5 — Code Recreation Tests

Tests that the Architect/execution subgraph can reconstruct specific modules
from the codebase exactly as they appear in code_store_hollow.jsonl.

Iterates over recreation scenarios. Bypasses RAG and Consultant.
"""
import uuid
import pytest

from tests.helpers import (
    build_test_execution_graph,
    rate_limit_pause,
)
from tests.nf_validation import validate_nextflow
from tests.scenarios.level5_recreation import LEVEL5_SCENARIOS, REFERENCE_CODE
from tests.report import report

@pytest.mark.parametrize(
    "scenario",
    LEVEL5_SCENARIOS,
    ids=[s["id"] for s in LEVEL5_SCENARIOS],
)
def test_code_recreation(scenario, store, judge_llm):
    """Verify the execution subgraph can reproduce a known module's code."""

    module_id = scenario.get("module_id")
    reference_code = REFERENCE_CODE.get(module_id)

    if not reference_code:
        pytest.skip(f"No reference code found for {module_id} in code_store_hollow.jsonl")

    # ── Build execution subgraph ──
    exec_graph = build_test_execution_graph(store)

    # ── Pre-baked initial state ──
    initial_state = {
        "user_query": f"Recreate {module_id}",
        "messages": [],
        "consultant_status": "APPROVED",
        "design_plan": scenario["design_plan"],
        "strategy_selector": scenario.get("expect_strategy", "EXACT_MATCH"),
        "used_template_id": scenario.get("used_template_id"),
        "selected_module_ids": scenario.get("selected_module_ids", []),
        "nextflow_code": None,
        "mermaid_agent": None,
        "mermaid_deterministic": None,
        "ast_json": None,
        "technical_context": None,
        "validation_error": None,
        "retries": 0,
        "error": None,
    }

    config = {"configurable": {"thread_id": f"test_{scenario['id']}_{uuid.uuid4().hex[:8]}"}}

    # ── Invoke execution subgraph ──
    final_state = exec_graph.invoke(initial_state, config=config)

    # ── Extract outputs ──
    nf_code = final_state.get("nextflow_code", "")
    mermaid_agent = final_state.get("mermaid_agent", "")
    mermaid_det = final_state.get("mermaid_deterministic", "")
    ast_json = final_state.get("ast_json", {})
    error = final_state.get("error")

    passed = True
    errors = []
    
    details = {
        "module_id": module_id,
        "strategy": initial_state.get("strategy_selector"),
        "nf_code_length": len(nf_code) if nf_code else 0,
        "nf_code": nf_code,
        "reference_length": len(reference_code),
        "has_ast": bool(ast_json),
        "mermaid_agent_length": len(mermaid_agent) if mermaid_agent else 0,
        "mermaid_agent": mermaid_agent,
        "mermaid_deterministic_length": len(mermaid_det) if mermaid_det else 0,
        "mermaid_deterministic": mermaid_det,
        "error": error,
    }
    scores = {}

    if error:
        errors.append(f"Execution subgraph error: {error}")
        passed = False
    if not nf_code or len(nf_code) <= 50:
        errors.append(f"No Nextflow code generated for {module_id}")
        passed = False

    # ── Nextflow validation ──
    try:
        # Run stub for recreation (Level 5)
        val_res = validate_nextflow(nf_code, run_stub=True)
        details.update(val_res)
        if val_res.get("nf_syntax_passed") == False or val_res.get("nf_stub_passed") == False:
            passed = False
    except Exception as e:
        details["nf_validation_error"] = f"Skipped: {str(e)[:100]}"

    # ── LLM Judge: Code Recreation ──
    if judge_llm:
        from tests.helpers import run_recreation_judge, run_diagram_judge
        try:
            judge_result = run_recreation_judge(
                judge_llm=judge_llm,
                reference_code=reference_code,
                generated_code=nf_code,
            )
            if judge_result:
                scores = {k: v for k, v in judge_result.items() if "score" in k}
                details["judge_scores"] = scores
                for k, v in scores.items():
                    if v < 3:
                        passed = False
                        details[f"{k}_low"] = v
        except Exception as e:
            details["judge_error"] = str(e)[:200]
            
        # ── LLM Judge: Diagrams (BOTH) ──
        ast_json = final_state.get("ast_json", {})
        mermaid_agent = final_state.get("mermaid_agent")
        mermaid_det = final_state.get("mermaid_deterministic")
        
        details["has_ast"] = bool(ast_json)
        details["has_mermaid_agent"] = bool(mermaid_agent)
        details["has_mermaid_det"] = bool(mermaid_det)
        
        for code_variant, source in [(mermaid_det, "deterministic"), (mermaid_agent, "agentic")]:
            if code_variant:
                try:
                    diagram_result = run_diagram_judge(
                        judge_llm=judge_llm,
                        tech_context=initial_state["technical_context"] or "",
                        nf_code=nf_code,
                        mermaid_code=code_variant,
                        strategy=source,
                    )
                    if diagram_result:
                        d_scores = {f"{source}_{k}": v for k, v in diagram_result.items() if "score" in k}
                        scores.update(d_scores)
                        if "diagram_judge_scores" not in details:
                            details["diagram_judge_scores"] = {}
                        details["diagram_judge_scores"].update(d_scores)
                        for k, v in d_scores.items():
                            if v < 4:
                                passed = False
                                details[f"{k}_low"] = v
                except Exception as e:
                    scores[f"{source}_diagram_judge_passed"] = 0.0
                    details[f"{source}_diagram_judge_error"] = str(e)[:200]

    if errors:
        details["errors"] = errors
        print(f"\n[FAIL] {scenario['id']} test_recreation failed:\n" + "\n".join(errors))

    report.add_result(
        scenario_id=f"[Recreation] {scenario['id']}",
        level=scenario["level"],
        success=passed,
        difficulty=scenario.get("difficulty", "—"),
        description=scenario.get("description", ""),
        scores=scores,
        details=details,
    )

    rate_limit_pause()
    
    assert not errors, f"Recreation test failed:\n" + "\n".join(errors)
