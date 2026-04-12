"""
tests/test_rag.py
Isolated RAG Retrieval Tests

Tests that retrieve_rag_context() returns the expected catalog items for
various user queries across all scenario complexities (Simple, Medium, Complex).

Calls the RAG function DIRECTLY against the loaded store.
Bypasses the Agent, the LLM, and the API.
"""
import pytest

from app.services.tools import retrieve_rag_context
from tests.scenarios.level1_simple import LEVEL1_SCENARIOS
from tests.scenarios.level2_medium import LEVEL2_SCENARIOS
from tests.scenarios.level3_complex import LEVEL3_SCENARIOS
from tests.report import report

ALL_SCENARIOS = LEVEL1_SCENARIOS + LEVEL2_SCENARIOS + LEVEL3_SCENARIOS

@pytest.mark.parametrize(
    "scenario",
    ALL_SCENARIOS,
    ids=[s["id"] for s in ALL_SCENARIOS],
)
def test_rag_retrieval(scenario, store):
    """Verify that RAG retrieves the expected catalog components and templates."""
    # RAG uses the first message in the chat history as the query
    query = scenario["chat_messages"][0]
    expected_ids = scenario.get("expect_in_context", [])

    if not expected_ids:
        pytest.skip("No expect_in_context defined for this scenario.")

    # ── Direct RAG call (no API, no agent) ──
    context = retrieve_rag_context(query, store, embed_code=False)

    # ── Deterministic assertions ──
    missing = [eid for eid in expected_ids if eid not in context]

    passed = len(missing) == 0
    scores = {"rag_precision": 1.0 if passed else 0.0}

    if missing:
        print(f"\n[FAIL] {scenario['id']} test_rag failed! Missing expected IDs: {missing}")
        print(f"Context snippet: {context[:500]}...")

    report.add_result(
        scenario_id=scenario["id"],
        level=scenario["level"],
        success=passed,
        difficulty=scenario.get("difficulty", "—"),
        description=scenario.get("description", ""),
        scores=scores,
        details={
            "query": query,
            "expected": expected_ids,
            "missing": missing,
            "context_length": len(context),
            "error": f"Missing components: {missing}" if missing else None,
        }
    )

    assert not missing, (
        f"RAG missed expected IDs: {missing}\n"
        f"Query: {query}\n"
        f"Context snippet: {context[:500]}..."
    )
