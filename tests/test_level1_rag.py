"""
tests/test_level1_rag.py
Level 1 — Simple: Single-tool pipeline requests via API

Tests that the system can handle basic single-tool requests through
the /chat API endpoint. Retries up to 3 times, keeps best result.
LLM judge scores faithfulness + relevance (if GROQ_API_KEY is set).
"""
import time
import pytest

from tests.report import report
from tests.helpers import run_multi_turn_chat, run_with_retries, rate_limit_pause, DEFAULT_PAUSE_BETWEEN_TESTS
from tests.scenarios.level1_simple import LEVEL1_SCENARIOS
from tests.evaluation.judge import judge_consultant


@pytest.mark.parametrize("scenario", LEVEL1_SCENARIOS, ids=lambda s: s["id"])
def test_level1_simple(scenario, api_client):
    """Simple single-tool pipeline via API with retry-best-of-3."""
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

            # Check for diagrams
            if result.get("mermaid_agent"):
                details["mermaid_agent_length"] = len(result.get("mermaid_agent"))
            if result.get("mermaid_deterministic"):
                details["mermaid_deterministic_length"] = len(result.get("mermaid_deterministic"))


        # ── LLM Judge: Faithfulness + Relevance ──
        chat_str = "\n".join(
            f"User: {m}" for m in scenario["chat_messages"]
        )
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
        scenario["id"], 1, scenario["difficulty"],
        scenario["description"], success,
        best.get("scores", {}),
        best.get("details", {}),
        elapsed,
    )

    if not success:
        pytest.fail(f"All 3 attempts failed. Last error: {best.get('error', '')[:300]}")

    # Pause between tests for rate limiting
    rate_limit_pause(DEFAULT_PAUSE_BETWEEN_TESTS, "between L1 tests")
