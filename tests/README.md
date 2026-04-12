# 🧬 IZS Bioinformatics Agent — Test Framework

## Overview

This test suite evaluates the IZS Nextflow AI Agent. It uses **FastAPI's TestClient** to run tests directly against the application logic in-memory. This ensures that lifespan events (like loading the RAG catalog) are correctly triggered without requiring a live network server.

Tests are organized into 5 levels by complexity, from simple single-tool requests to full module recreation from reference code.

## Quick Start

You can run these tests directly via `pytest`. Since they use `TestClient`, you don't need to start the Uvicorn server in the background.

```bash
# 1. Install dependencies (httpx is required for TestClient)
pip install pytest httpx

# 2. Run all tests
pytest tests/ -v --tb=short

# 3. Run a single level
pytest tests/test_level1_rag.py -v

# 4. Run a specific test scenario by ID
pytest tests/ -v -k "L1_01_fastp_trim"
```

## Test Levels

| Level | Name | Difficulty | Tests | What It Tests |
|-------|------|-----------|-------|---------------|
| 1 | **Single-Tool Pipelines** | Simple | 5 | Can the AI build a pipeline for one tool? (e.g., "trim with fastp") |
| 2 | **Template-Level Pipelines** | Medium | 5 | Can the AI match known templates? (e.g., "COVID mapping + Pangolin") |
| 3 | **Complex Multi-Step** | Complex | 6 | Can the AI chain 3+ tools correctly? (e.g., "trim → assemble → AMR") |
| 4 | **Rejection Guardrails** | Medium | 6 | Does the AI refuse invalid requests? (e.g., "BWA", "Pangolin for bacteria") |
| 5 | **Module Recreation** | Complex | 14 | Can the AI recreate known modules from description? |
| | | **Total** | **36** | |

## Validation Layers

Every test that generates code is evaluated through **three independent layers**:

### Layer 1: Deterministic Assertions (always active)
- API returned HTTP 200
- Status reached `APPROVED`
- Nextflow code was generated and contains a `workflow` block
- Mermaid diagrams contain `flowchart` or `graph`
- Include statements match reference (L5 only)

### Layer 2: Nextflow Compiler (when `NF_FRAMEWORK_DIR` is available)
- **Syntax check** (`nextflow run ... -preview`): validates DSL2 grammar, imports, and process definitions (L3, L5 only)
- **Stub run** (`nextflow run ... -stub`): validates channel wiring and data flow without executing real tools (L3, L5 only)
- Error output is parsed through `error_patterns.py` (50+ regex patterns across 5 categories: syntax, channels, processes, DSL2-specific, and expected noise)

### Layer 3: LLM Judge (when `GROQ_API_KEY` is set)
- Uses `llama-3.3-70b-versatile` on Groq with structured Pydantic output
- Expert-calibrated 5-level rubrics for each test type:
  - **L1/L2**: Faithfulness to catalog + Relevance to biological scenario
  - **L3**: Nextflow DSL2 syntax + Pipeline logic + Diagram accuracy (both agentic and deterministic)
  - **L4**: Rejection correctness + Alternative suggestions quality
  - **L5**: Structural similarity + Channel logic vs reference code
- Chain-of-thought reasoning is forced before scoring (via `_reason` fields)
- Judge reasoning is included in the final markdown report

## How Tests Work

1. **In-Memory API**: Every test uses `api_client` (FastAPI TestClient) to send messages to the `/chat` endpoint. This executes the actual app logic including LangGraph nodes and lifespan startup.
2. **Multi-Turn**: Each scenario has a pre-defined chat history (2–4 user messages).
3. **Retry Logic**: Each test retries up to 3 times, keeping the **best** result (highest scoring).
4. **Rate Limiting**: Automatic pauses between tests (15s) and between turns (5s) to respect LLM provider limits. 30s backoff on rate limit errors.
5. **Reports**: Markdown report auto-generated to `test_reports/test_report_latest.md`.

## Directory Structure

```
tests/
├── conftest.py                    # TestClient fixture + report finalization
├── helpers.py                     # API client wrapper, retry logic, rate limiting
├── error_patterns.py              # 50+ Nextflow error regex patterns (5 categories)
├── nf_validation.py               # NF syntax/stub validation + validate_nextflow() helper
├── report.py                      # Markdown report generator (ReportCollector)
├── evaluation/
│   ├── __init__.py
│   ├── judge.py                   # LLM judge — lazy Groq client, 5 judge functions
│   ├── schemas.py                 # Pydantic models for structured judge output
│   └── prompts.py                 # Expert rubrics (5-level, bias-reduced, domain-specific)
├── scenarios/
│   ├── __init__.py
│   ├── level1_simple.py           # 5 simple single-tool scenarios
│   ├── level2_medium.py           # 5 medium template-level scenarios
│   ├── level3_complex.py          # 6 complex multi-step scenarios
│   ├── level4_guardrails.py       # 6 negative/rejection scenarios
│   └── level5_recreation.py       # 14 module recreation scenarios + JSONL loader
├── test_level1_rag.py             # Runner: Simple (judge only)
├── test_level2_consultant.py      # Runner: Medium (judge only)
├── test_level3_execution.py       # Runner: Complex (NF compiler + judge + diagrams)
├── test_level4_rejection.py       # Runner: Negative (no code expected)
└── test_level5_recreation.py      # Runner: Recreation (NF compiler + judge + ref comparison)
```

## Environment Variables

Tests require API keys for the agents and (optionally) the judge and compiler.

| Variable | Required | Purpose |
|----------|----------|---------|
| `MISTRAL_API_KEY` | Yes | Powers the AI agents (Consultant/Architect) |
| `GROQ_API_KEY` | Optional | Powers the LLM judge for automated scoring |
| `NF_FRAMEWORK_DIR` | Optional | Path to local NF framework for syntax/stub validation |

## Report Output

After each run, a comprehensive markdown report is saved to:
- `test_reports/test_report_<timestamp>.md`
- `test_reports/test_report_latest.md`

The report is designed for non-technical stakeholders and includes:
- Summary table with pass/fail per level
- Complexity descriptions with biological examples
- Per-test metrics (turns, code length, diagram sizes, NF compiler results)
- LLM judge scores with chain-of-thought reasoning
- Score guide for interpreting automated evaluation
