"""
tests/test_level2_consultant.py
Level 2 — Medium: Template-level pipeline requests via API

Tests multi-step pipeline scenarios that typically map to known templates.
Each test runs the full conversation via API with retry-best-of-3.
LLM judge scores faithfulness + relevance (if GROQ_API_KEY is set).
"""
import time
import pytest

from tests.report import report
from tests.helpers import run_multi_turn_chat, run_with_retries, rate_limit_pause, DEFAULT_PAUSE_BETWEEN_TESTS
from tests.scenarios.level2_medium import LEVEL2_SCENARIOS
from tests.evaluation.judge import judge_consultant


@pytest.mark.parametrize("scenario", LEVEL2_SCENARIOS, ids=lambda s: s["id"])
def test_level2_medium(scenario, api_client):
    """Template-level pipeline via API with retry-best-of-3."""
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
            "all_replies": [r["reply"][:100] for r in result.get("all_replies", [])],
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

            if result.get("mermaid_agent"):
                details["mermaid_agent_length"] = len(result.get("mermaid_agent"))
            if result.get("mermaid_deterministic"):
                details["mermaid_deterministic_length"] = len(result.get("mermaid_deterministic"))


        # ── LLM Judge: Faithfulness + Relevance ──
        chat_str = "\n".join(
            f"Turn {i+1} - User: {m}" for i, m in enumerate(scenario["chat_messages"])
        )
        # Add AI replies to the chat string for context
        for r in result.get("all_replies", []):
            chat_str += f"\nTurn {r['turn']} - AI: {r['reply'][:200]}"

        judge_scores = judge_consultant(
            context=scenario["description"],
            chat=chat_str,
            reply=result.get("reply", ""),
        )
        if judge_scores:
            scores.update(judge_scores)
            details["judge_faithfulness_reason"] = judge_scores.get("faithfulness_reason", "")[:200]
            details["judge_relevance_reason"] = judge_scores.get("relevance_reason", "")[:200]

        return {"scores": scores, "details": details, "result": result}

    best = run_with_retries(_attempt, max_retries=3)
    elapsed = time.time() - start

    success = best.get("error") is None
    report.add_result(
        scenario["id"], 2, scenario["difficulty"],
        scenario["description"], success,
        best.get("scores", {}),
        best.get("details", {}),
        elapsed,
    )

    if not success:
        pytest.fail(f"All 3 attempts failed. Last error: {best.get('error', '')[:300]}")

    rate_limit_pause(DEFAULT_PAUSE_BETWEEN_TESTS, "between L2 tests")
