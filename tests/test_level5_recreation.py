"""
tests/test_level5_recreation.py
Level 5 — Code Recreation: Reconstruct modules via API

Tests that the system can recreate known pipeline modules from the framework.
The generated Nextflow code is compared against the reference implementation
from data/code_store_hollow.jsonl.

Each test:
  1. Sends the conversation via API
  2. Validates that code was generated
  3. LLM judge scores structural similarity + channel logic vs reference

Retries up to 3 times, keeps best result.
"""
import time
import pytest

from tests.report import report
from tests.helpers import run_multi_turn_chat, run_with_retries, rate_limit_pause, DEFAULT_PAUSE_BETWEEN_TESTS
from tests.scenarios.level5_recreation import LEVEL5_SCENARIOS, REFERENCE_CODE
from tests.evaluation.judge import judge_recreation
from tests.nf_validation import validate_nextflow


@pytest.mark.parametrize("scenario", LEVEL5_SCENARIOS, ids=lambda s: s["id"])
def test_level5_recreation(scenario, api_client):
    """Module recreation via API with retry-best-of-3."""
    start = time.time()
    module_id = scenario["module_id"]

    # Get reference code
    ref_code = REFERENCE_CODE.get(module_id, "")
    assert ref_code, f"Reference code for '{module_id}' not found in code_store_hollow.jsonl"

    def _attempt():
        result = run_multi_turn_chat(
            client=api_client,
            chat_messages=scenario["chat_messages"],
        )

        scores = {}
        details = {
            "module_id": module_id,
            "ai_reply": result.get("reply", "")[:300],
            "ai_status": result.get("status"),
            "turns": result.get("turns"),
            "reference_code_length": len(ref_code),
        }

        assert result["success"], f"API call failed: {result.get('error')}"

        # Must reach APPROVED with code
        assert result["status"] == "APPROVED", (
            f"Expected APPROVED but got '{result['status']}'. "
            f"Reply: {result.get('reply', '')[:200]}"
        )

        nf_code = result.get("nextflow_code")
        assert nf_code, "Expected Nextflow code but none was generated."
        details["nf_code_length"] = len(nf_code)
        details["generated_code_preview"] = nf_code[:500]
        details["reference_code_preview"] = ref_code[:500]

        # Check for include statements matching the reference
        ref_includes = set()
        gen_includes = set()
        for line in ref_code.splitlines():
            stripped = line.strip()
            if stripped.startswith("include {") or stripped.startswith("include{"):
                ref_includes.add(stripped)
        for line in nf_code.splitlines():
            stripped = line.strip()
            if stripped.startswith("include {") or stripped.startswith("include{"):
                gen_includes.add(stripped)

        if ref_includes:
            matched = len(ref_includes & gen_includes)
            total = len(ref_includes)
            include_ratio = matched / total if total > 0 else 0.0
            details["include_match_ratio"] = f"{matched}/{total} ({include_ratio:.0%})"
            scores["include_match_pct"] = round(include_ratio * 100)

        # Check both diagrams
        if result.get("mermaid_agent"):
            details["mermaid_agent_length"] = len(result["mermaid_agent"])
        if result.get("mermaid_deterministic"):
            details["mermaid_deterministic_length"] = len(result["mermaid_deterministic"])

        # Nextflow compiler validation (syntax + stub for L5)
        details.update(validate_nextflow(nf_code, run_stub=True))

        # ── LLM Judge: Structural Similarity + Channel Logic ──
        judge_scores = judge_recreation(
            reference_code=ref_code,
            generated_code=nf_code,
        )
        if judge_scores:
            scores.update(judge_scores)
            details["judge_structural_reason"] = judge_scores.get("structural_reason", "")[:200]
            details["judge_channel_reason"] = judge_scores.get("channel_reason", "")[:200]

        return {"scores": scores, "details": details, "result": result}

    best = run_with_retries(_attempt, max_retries=3)
    elapsed = time.time() - start

    success = best.get("error") is None
    report.add_result(
        scenario["id"], 5, scenario["difficulty"],
        scenario["description"], success,
        best.get("scores", {}),
        best.get("details", {}),
        elapsed,
    )

    if not success:
        pytest.fail(f"All 3 attempts failed. Last error: {best.get('error', '')[:300]}")

    rate_limit_pause(DEFAULT_PAUSE_BETWEEN_TESTS, "between L5 tests")
