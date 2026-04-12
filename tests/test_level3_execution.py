"""
tests/test_level3_execution.py
Level 3 — Complex: Multi-step pipeline construction via API

Tests complex multi-step pipelines that chain 3+ tools. The system must
correctly wire channels between steps and produce valid Nextflow code.
Validates: code generation, both Mermaid diagrams, and AST output.
LLM judge scores: pipeline syntax/logic + diagram syntax/mapping.
Retries up to 3 times, keeps best result.
"""
import time
import pytest

from tests.report import report
from tests.helpers import run_multi_turn_chat, run_with_retries, rate_limit_pause, DEFAULT_PAUSE_BETWEEN_TESTS
from tests.scenarios.level3_complex import LEVEL3_SCENARIOS
from tests.evaluation.judge import judge_pipeline, judge_diagram
from tests.nf_validation import validate_nextflow


@pytest.mark.parametrize("scenario", LEVEL3_SCENARIOS, ids=lambda s: s["id"])
def test_level3_complex(scenario, api_client):
    """Complex multi-step pipeline via API with retry-best-of-3."""
    start = time.time()

    def _attempt():
        result = run_multi_turn_chat(
            client=api_client,
            chat_messages=scenario["chat_messages"],
        )

        scores = {}
        details = {
            "ai_reply": result.get("reply", "")[:300],
            "ai_status": result.get("status"),
            "turns": result.get("turns"),
        }

        assert result["success"], f"API call failed: {result.get('error')}"

        if scenario.get("expect_approved"):
            assert result["status"] == "APPROVED", (
                f"Expected APPROVED but got '{result['status']}'. "
                f"Reply: {result.get('reply', '')[:200]}"
            )

        if scenario.get("expect_code"):
            nf_code = result.get("nextflow_code")
            assert nf_code, "Expected Nextflow code but none was generated."
            details["nf_code_length"] = len(nf_code)

            # Validate code has workflow structure
            assert "workflow" in nf_code, (
                "Generated code is missing a workflow definition."
            )

            # Nextflow compiler validation (syntax + stub for L3)
            details.update(validate_nextflow(nf_code, run_stub=True))

            # ── LLM Judge: Pipeline Syntax + Logic ──
            pipeline_scores = judge_pipeline(
                plan=scenario["description"],
                context=scenario["description"],
                code=nf_code,
            )
            if pipeline_scores:
                scores["pipeline_syntax_score"] = pipeline_scores.get("syntax_score")
                scores["pipeline_logic_score"] = pipeline_scores.get("logic_score")
                details["judge_syntax_reason"] = pipeline_scores.get("syntax_reason", "")[:200]
                details["judge_logic_reason"] = pipeline_scores.get("logic_reason", "")[:200]

            # Check + judge agentic diagram
            mermaid_agent = result.get("mermaid_agent")
            if mermaid_agent:
                details["mermaid_agent_length"] = len(mermaid_agent)
                assert "flowchart" in mermaid_agent or "graph" in mermaid_agent, (
                    "Agentic diagram is not a valid Mermaid flowchart."
                )
                agent_diag_scores = judge_diagram(
                    context=scenario["description"],
                    nf_code=nf_code,
                    mermaid_code=mermaid_agent,
                    diagram_source="agentic",
                )
                if agent_diag_scores:
                    scores["diagram_agent_syntax_score"] = agent_diag_scores.get("syntax_score")
                    scores["diagram_agent_mapping_score"] = agent_diag_scores.get("mapping_score")

            # Check + judge deterministic diagram
            mermaid_det = result.get("mermaid_deterministic")
            if mermaid_det:
                details["mermaid_deterministic_length"] = len(mermaid_det)
                assert "flowchart" in mermaid_det or "graph" in mermaid_det, (
                    "Deterministic diagram is not a valid Mermaid flowchart."
                )
                det_diag_scores = judge_diagram(
                    context=scenario["description"],
                    nf_code=nf_code,
                    mermaid_code=mermaid_det,
                    diagram_source="deterministic",
                )
                if det_diag_scores:
                    scores["diagram_det_syntax_score"] = det_diag_scores.get("syntax_score")
                    scores["diagram_det_mapping_score"] = det_diag_scores.get("mapping_score")

            # Check AST
            if result.get("ast_json"):
                details["has_ast"] = True
                assert isinstance(result["ast_json"], dict), "ast_json must be a dict."

        return {"scores": scores, "details": details, "result": result}

    best = run_with_retries(_attempt, max_retries=3)
    elapsed = time.time() - start

    success = best.get("error") is None
    report.add_result(
        scenario["id"], 3, scenario["difficulty"],
        scenario["description"], success,
        best.get("scores", {}),
        best.get("details", {}),
        elapsed,
    )

    if not success:
        pytest.fail(f"All 3 attempts failed. Last error: {best.get('error', '')[:300]}")

    rate_limit_pause(DEFAULT_PAUSE_BETWEEN_TESTS, "between L3 tests")
