"""
tests/evaluation/judge.py
LLM Judge — invokes the evaluation prompts against a Groq-hosted LLM
to score the AI agent's outputs.

Uses the same get_judge_llm() pattern from app/services/llm.py but with
graceful degradation — if GROQ_API_KEY is missing, all judge functions
return empty scores and tests still pass with deterministic assertions only.

Usage:
    from tests.evaluation.judge import judge_consultant, judge_pipeline, ...
"""
import os
from typing import Optional

from tests.evaluation.schemas import (
    AcademicEval,
    ArchitectEval,
    DiagramEval,
    RejectionEval,
    CodeRecreationEval,
)
from tests.evaluation.prompts import (
    JUDGE_PROMPT,
    PIPELINE_JUDGE_PROMPT,
    DIAGRAM_JUDGE_PROMPT,
    REJECTION_JUDGE_PROMPT,
    CODE_RECREATION_JUDGE_PROMPT,
)

_judge_llm = None
_judge_available = None


def get_judge():
    """
    Lazily initialize the Groq judge LLM.
    Returns None if GROQ_API_KEY is not set.

    NOTE: conftest.py loads .env before this module is imported,
    so os.environ will already have the keys if they exist in .env.
    """
    global _judge_llm, _judge_available

    if _judge_available is not None:
        return _judge_llm

    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        print("\n⚠️  GROQ_API_KEY not set — LLM judge scoring will be SKIPPED.")
        print("   Tests will still run with deterministic assertions only.\n")
        _judge_available = False
        _judge_llm = None
        return None

    try:
        # Import here to avoid import errors if langchain_groq is not installed
        from langchain_groq import ChatGroq

        _judge_llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            temperature=0.0,
            api_key=api_key,
        )
        _judge_available = True
        print("\n✅ LLM Judge initialized (Groq / llama-3.3-70b-versatile)")
        return _judge_llm
    except Exception as e:
        print(f"\n⚠️  Failed to initialize LLM judge: {e}")
        print("   Tests will still run with deterministic assertions only.\n")
        _judge_available = False
        _judge_llm = None
        return None


def _run_judge(prompt, schema, invoke_kwargs: dict) -> Optional[dict]:
    """
    Internal: invoke a judge prompt with structured output.
    Returns a dict of scores and reasons, or None if judge is unavailable.
    """
    llm = get_judge()
    if llm is None:
        return None

    try:
        chain = prompt | llm.with_structured_output(schema)
        result = chain.invoke(invoke_kwargs)
        # Convert pydantic model to dict
        return result.model_dump()
    except Exception as e:
        print(f"  ⚠️  Judge call failed: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# Public judge functions — one per test level
# ──────────────────────────────────────────────────────────────

def judge_consultant(context: str, chat: str, reply: str) -> dict:
    """
    Judge the consultant's response for faithfulness + relevance.
    Used by L1 (Simple) and L2 (Medium) tests.

    Returns dict with keys: faithfulness_score, faithfulness_reason,
    relevance_score, relevance_reason — or empty dict if judge unavailable.
    """
    result = _run_judge(JUDGE_PROMPT, AcademicEval, {
        "context": context,
        "chat": chat,
        "reply": reply,
    })
    return result or {}


def judge_pipeline(plan: str, context: str, code: str) -> dict:
    """
    Judge the architect's generated Nextflow code for syntax + logic.
    Used by L3 (Complex) tests.

    Returns dict with keys: syntax_score, syntax_reason,
    logic_score, logic_reason — or empty dict if judge unavailable.
    """
    result = _run_judge(PIPELINE_JUDGE_PROMPT, ArchitectEval, {
        "plan": plan,
        "context": context,
        "code": code,
    })
    return result or {}


def judge_diagram(
    context: str, nf_code: str, mermaid_code: str, diagram_source: str
) -> dict:
    """
    Judge a Mermaid diagram (agentic OR deterministic) for syntax + mapping.
    Used by L3 (Complex) tests — called once per diagram variant.

    Parameters
    ----------
    diagram_source : str
        Either "agentic" or "deterministic".

    Returns dict with keys: syntax_score, syntax_reason,
    mapping_score, mapping_reason — or empty dict if judge unavailable.
    """
    result = _run_judge(DIAGRAM_JUDGE_PROMPT, DiagramEval, {
        "diagram_source": diagram_source,
        "context": context,
        "nf_code": nf_code,
        "mermaid_code": mermaid_code,
    })
    return result or {}


def judge_rejection(prompt: str, rejection_reason: str, reply: str, status: str) -> dict:
    """
    Judge the AI's rejection of an invalid request.
    Used by L4 (Guardrails) tests.

    Returns dict with keys: rejection_score, rejection_reason,
    alternative_score, alternative_reason — or empty dict if judge unavailable.
    """
    result = _run_judge(REJECTION_JUDGE_PROMPT, RejectionEval, {
        "prompt": prompt,
        "rejection_reason": rejection_reason,
        "reply": reply,
        "status": status,
    })
    return result or {}


def judge_recreation(reference_code: str, generated_code: str) -> dict:
    """
    Judge the AI's code recreation against a reference module.
    Used by L5 (Recreation) tests.

    Returns dict with keys: structural_score, structural_reason,
    channel_score, channel_reason — or empty dict if judge unavailable.
    """
    result = _run_judge(CODE_RECREATION_JUDGE_PROMPT, CodeRecreationEval, {
        "reference_code": reference_code,
        "generated_code": generated_code,
    })
    return result or {}
