"""
tests/test_rejection.py
Level 4 — Negative: Rejection / Guardrail Tests

Tests that the consultant agent correctly rejects invalid requests.
Uses get_exact_context to inject real alternatives, then invokes
the consultant directly. The agent should stay CHATTING and explain
why the request is invalid.

Bypasses RAG and the execution subgraph.
"""
import pytest
from langchain_core.messages import HumanMessage

from app.models.consultant_structure import ConsultantOutput
from tests.evaluation.prompts import CONSULTANT_TEST_PROMPT
from tests.helpers import get_exact_context, rate_limit_pause
from tests.scenarios.level4_guardrails import LEVEL4_SCENARIOS
from tests.report import report

@pytest.mark.parametrize(
    "scenario",
    LEVEL4_SCENARIOS,
    ids=[s["id"] for s in LEVEL4_SCENARIOS],
)
def test_rejection_guardrail(scenario, store, llm, judge_llm):
    """Verify that the consultant rejects invalid tool requests."""

    if "template_ids" not in scenario or "component_ids" not in scenario:
        pytest.skip("Mock data for alternatives not defined in scenario.")

    # ── Build deterministic context with REAL alternatives ──
    real_context = get_exact_context(
        scenario["template_ids"],
        scenario["component_ids"],
        store,
    )

    # ── Build agent chain ──
    agent = llm.with_structured_output(ConsultantOutput)
    chain = CONSULTANT_TEST_PROMPT | agent

    # ── Invoke with the invalid request ──
    chat_history = [HumanMessage(content=scenario["chat_messages"][0])]
    result = chain.invoke({"context": real_context, "messages": chat_history})

    # ── Deterministic assertions ──
    passed = True
    details = {
        "status": result.status,
        "response": result.response_to_user[:300],
        "expected_rejection_reason": scenario["rejection_reason"],
    }
    scores = {}

    assert result.status == "CHATTING", (
        f"Agent APPROVED an invalid request! Expected CHATTING.\n"
        f"Request: {scenario['chat_messages'][0]}\n"
        f"Reply: {result.response_to_user[:200]}"
    )

    assert not result.draft_plan or result.draft_plan.strip() == "", "Agent generated a plan for an invalid request."

    # ── LLM Judge: Rejection quality ──
    if judge_llm:
        try:
            from tests.helpers import run_rejection_judge
            judge_result = run_rejection_judge(
                judge_llm=judge_llm,
                prompt=scenario["chat_messages"][0],
                rejection_reason=scenario["rejection_reason"],
                reply=result.response_to_user,
                status=result.status,
            )
            if judge_result:
                scores = {k: v for k, v in judge_result.items() if "score" in k}
                details["judge_scores"] = scores
                for k, v in scores.items():
                    if v < 4:
                        passed = False
                        details[f"{k}_low"] = v
        except Exception as e:
            details["judge_error"] = str(e)[:200]

    report.add_result(
        scenario_id=scenario["id"],
        level=scenario["level"],
        success=passed,
        difficulty=scenario.get("difficulty", "—"),
        description=scenario.get("description", ""),
        scores=scores,
        details=details,
    )

    rate_limit_pause()
