"""
tests/test_level4_rejection.py
Level 4 — Negative: Rejection / Guardrail Tests via API

Tests that the system correctly rejects invalid or impossible requests.
The AI must stay in CHATTING status, explain WHY, and suggest alternatives.
LLM judge scores rejection quality + alternative suggestions.
Retries up to 3 times, keeps best result.
"""
import time
import pytest

from tests.report import report
from tests.helpers import run_multi_turn_chat, run_with_retries, rate_limit_pause, DEFAULT_PAUSE_BETWEEN_TESTS
from tests.scenarios.level4_guardrails import LEVEL4_SCENARIOS
from tests.evaluation.judge import judge_rejection


@pytest.mark.parametrize("scenario", LEVEL4_SCENARIOS, ids=lambda s: s["id"])
def test_level4_rejection(scenario, api_client):
    """Rejection guardrail test via API with retry-best-of-3."""
    start = time.time()

    def _attempt():
        result = run_multi_turn_chat(
            client=api_client,
            chat_messages=scenario["chat_messages"],
            expect_rejection=True,
        )

        scores = {}
        details = {
            "ai_reply": result.get("reply", "")[:400],
            "ai_status": result.get("status"),
            "rejection_expected": scenario.get("rejection_reason", ""),
        }

        assert result["success"], f"API call failed: {result.get('error')}"

        # Must stay CHATTING (not APPROVED)
        assert result["status"] != "APPROVED", (
            f"REJECTION FAILED: Agent APPROVED an impossible request. "
            f"Reply: {result.get('reply', '')[:200]}"
        )

        # Should NOT have generated code
        assert not result.get("nextflow_code"), (
            f"REJECTION FAILED: Agent generated Nextflow code for impossible request."
        )

        # ── LLM Judge: Rejection Quality + Alternatives ──
        judge_scores = judge_rejection(
            prompt=scenario["chat_messages"][0],
            rejection_reason=scenario.get("rejection_reason", ""),
            reply=result.get("reply", ""),
            status=result.get("status", ""),
        )
        if judge_scores:
            scores.update(judge_scores)
            details["judge_rejection_reason"] = judge_scores.get("rejection_reason", "")[:200]
            details["judge_alternative_reason"] = judge_scores.get("alternative_reason", "")[:200]

        return {"scores": scores, "details": details, "result": result}

    best = run_with_retries(_attempt, max_retries=3)
    elapsed = time.time() - start

    success = best.get("error") is None
    report.add_result(
        scenario["id"], 4, scenario["difficulty"],
        scenario["description"], success,
        best.get("scores", {}),
        best.get("details", {}),
        elapsed,
    )

    if not success:
        pytest.fail(f"All 3 attempts failed. Last error: {best.get('error', '')[:300]}")

    rate_limit_pause(DEFAULT_PAUSE_BETWEEN_TESTS, "between L4 tests")
