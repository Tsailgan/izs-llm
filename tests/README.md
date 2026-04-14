# IZS Bioinformatics Agent Test Framework

## 1) What This Test Does

This test checks whether the AI can safely and correctly help people build bioinformatics pipelines from natural language.

In simple terms, it asks:

- Can the AI find the right tools from the catalog?
- Can it plan correctly before generating code?
- Can it generate valid Nextflow DSL2 code?
- Can it reject dangerous or invalid requests?
- Can it recreate known reference modules with high fidelity?
- Can it revise a previous plan after user feedback?

The tests are built for both technical and non-technical audiences:

- Developers get deterministic checks and compiler validation.
- Scientists and project leads get readable scoring and explanation in a Markdown report.

## 2) Big Picture: Test Architecture

The framework uses two styles of testing:

- Full API path (through `/chat`) using FastAPI `TestClient` in-memory.
- Isolated path (direct function and subgraph invocation) to test specific subsystems independently.

That means the test can isolate where a failure comes from:

- Retrieval problem (RAG)
- Planning problem (Consultant)
- Code generation problem (Execution/Architect)
- Guardrail problem (Rejection)
- Similarity/fidelity problem (Recreation)

## 3) Test Categories (What Is Tested)

These are the actual test modules and their purpose.

### `test_rag.py`

- Tests retrieval only.
- Calls `retrieve_rag_context()` directly.
- Does not involve API, consultant, or code generation.
- Verifies expected IDs are present in retrieved context.

### `test_consultant.py`

- Tests planning logic only.
- Injects deterministic context with `get_exact_context()`.
- Verifies approval behavior, strategy/template alignment, and optional judge quality.

### `test_execution.py`

- Tests execution subgraph in isolation:
  - hydrator -> architect -> repair -> renderer -> diagrams
- Verifies code and AST generation.
- Runs Nextflow compiler checks when available.
- Scores code and diagrams with judge when configured.

### `test_rejection.py`

- Tests guardrails (negative prompts).
- Verifies invalid requests are refused:
  - status should stay `CHATTING`
  - no build-ready plan should be generated
- Optionally scores rejection quality and alternatives.

### `test_recreation.py`

- Part A: module recreation against reference code (`LEVEL5_SCENARIOS`).
- Part B: two-stage revision flows (initial build -> revision -> re-approval -> final build) from `RECREATION_REV` scenarios.
- Includes mandatory judge gates in revision-flow path.

## 4) Scenario Levels and Why They Matter

The scenario set is intentionally layered from easy to hard.

| Level | Focus                   | Why it exists                                              |
| ----- | ----------------------- | ---------------------------------------------------------- |
| 1     | Single-tool requests    | Baseline reliability: one tool, low ambiguity              |
| 2     | Template-level requests | Checks template matching and moderate domain understanding |
| 3     | Complex multi-step      | Stress test for multi-step channel/data-flow logic         |
| 4     | Guardrails/rejection    | Safety and correctness for invalid requests                |
| 5     | Module recreation       | Fidelity to known reference modules                        |

## 5) Current Scenario Counts (From Scenario Files)

Raw scenario definitions:

- `level1_simple.py`: 9 scenarios
- `level2_medium.py`: 17 scenarios
- `level3_complex.py`: 9 scenarios
- `level4_guardrails.py`: 16 scenarios
- `level5_recreation.py`: 14 scenarios

Total defined scenarios: **65**

Test usage differs by module:

- `test_rag.py`: 46 scenarios (excludes `RECREATION_REV` cases)
- `test_consultant.py`: 16 scenarios (L1-L3 non-revision)
- `test_execution.py`: 16 scenarios (L1-L3 non-revision)
- `test_rejection.py`: 16 scenarios (all Level 4)
- `test_recreation.py` (module recreation): 14 scenarios
- `test_recreation.py` (revision-flow): 19 scenarios (`RECREATION_REV` from L1-L3)

Total pytest case executions across these files: **127**

## 6) Validation and Scoring Pipeline

Each category has deterministic checks first, then optional quality scoring.

### Step A: Deterministic checks

Examples:

- Expected status values (`APPROVED` or `CHATTING`)
- Code exists and is non-trivial
- AST exists
- RAG expected IDs appear

Deterministic checks provide hard correctness signals with low ambiguity.

### Step B: Compiler checks (if Nextflow framework is available)

From `nf_validation.py`:

- Syntax: `nextflow run <file> -preview`
- Stub run: `nextflow run <file> -stub`

Why this score/check is used:

- Syntax catches invalid DSL2 structure.
- Stub run catches channel wiring/data-flow issues without running expensive real tools.

### Step C: LLM judge (if judge endpoint is configured)

This is the quality layer. Deterministic checks tell you if the run completed correctly; the judge tells you how good the result is.

#### What the judge does

The judge evaluates scientific and engineering quality using structured output schemas in `tests/evaluation/schemas.py` and rubric prompts in `tests/evaluation/prompts.py`.

It does not replace deterministic checks. It complements them by scoring quality dimensions that are hard to validate with simple assertions.

#### Which model is used

`get_judge_llm()` in `app/services/llm.py` configures a `ChatOpenAI` client using:

- `base_url` from `JUDGE_BASE_URL`
- model: `Qwen3-Coder-30B`
- temperature: `0.0` (deterministic judging behavior)

#### How the judge scores

All judges use a 1-5 rubric and require reason-first output (reason fields plus score fields).

Judge families and dimensions:

- Consultant judge (`AcademicEval`):
  - `faithfulness_score`: does the response stay inside catalog constraints
  - `relevance_score`: does it fit organism/platform/analysis goal
- Pipeline judge (`ArchitectEval`):
  - `syntax_score`: Nextflow DSL2 quality
  - `logic_score`: workflow correctness versus plan/context
- Diagram judge (`DiagramEval`):
  - `syntax_score`: Mermaid validity
  - `mapping_score`: alignment with Nextflow data flow
- Rejection judge (`RejectionEval`):
  - `rejection_score`: correctness/clarity of refusal
  - `alternative_score`: quality of suggested valid alternatives
- Recreation judge (`CodeRecreationEval`):
  - `structural_score`: similarity to reference structure
  - `channel_score`: channel wiring similarity

#### What evidence each judge uses (based on what)

The judge does not score from a single text. It scores from explicit evidence bundles:

- Consultant:
  - retrieved context
  - chat transcript
  - final AI reply
  - generated design plan
- Pipeline:
  - design plan
  - technical context
  - generated Nextflow code
- Diagram:
  - technical context
  - generated Nextflow code
  - Mermaid code (agentic or deterministic)
- Rejection:
  - invalid user request
  - ground-truth rejection reason
  - AI reply
  - AI status
- Recreation:
  - reference module code
  - generated code

This is why the judge can answer "why" a result is weak, not only "pass/fail".

#### When the judge runs

The judge is called conditionally in each test file when `judge_llm` is available.

- `test_rag.py`:
  - no LLM judge; only deterministic retrieval scoring
- `test_consultant.py`:
  - after consultant output is produced
  - `run_academic_judge()` evaluates faithfulness/relevance
- `test_execution.py`:
  - after execution subgraph produces code and diagrams
  - `run_pipeline_judge()` evaluates code
  - `run_diagram_judge()` evaluates both deterministic and agentic diagrams
- `test_rejection.py`:
  - after consultant rejects an invalid request
  - `run_rejection_judge()` evaluates refusal and alternatives
- `test_recreation.py` (Level 5 recreation):
  - after generated module code is available
  - `run_recreation_judge()` plus both diagram judges
- `test_recreation.py` (revision two-stage flow):
  - on revision turn and/or final revised output
  - non-rejection revision path: consultant + architect + both diagram judges
  - rejection revision path: rejection judge on final consultant reply

#### Judge thresholds used in the suite

Operational thresholds currently applied by test logic:

- Consultant quality target: >= 4
- Pipeline quality target: >= 4
- Diagram quality target: >= 4
- Rejection quality target: >= 4
- Recreation structural/channel target: >= 3 in Level 5 recreation path

Important nuance:

- Some tests only record low judge scores in report quality fields.
- Some flows (especially revision flows in `test_recreation.py`) treat missing/low judge evidence as hard failure.

Why 1-5 is used:

- Easy for stakeholders to interpret.
- Enough granularity to separate "acceptable" from "excellent".
- Works well for trend reporting in slides and dashboards.

## 7) Pass/Fail Semantics (Important Nuance)

There are two notions of success:

- Pytest hard pass/fail (assertions)
- Report pass/fail (quality result recorded in `report.py`)

In some tests, low judge scores can mark a scenario as failed in the report while pytest itself still passes (because deterministic assertions passed).

Where judge thresholds are strict in logic:

- Consultant quality: target >= 4 on faithfulness/relevance
- Execution quality: target >= 4 for pipeline/diagram dimensions
- Rejection quality: target >= 4 for rejection/alternative
- Recreation quality: structural/channel often accepted at >= 3 for recreation judge, diagrams >= 4

Revision-flow tests in `test_recreation.py` are stricter and can hard-fail when mandatory judge evidence or thresholds are not met.

## 8) Why These Scores Are Chosen

This framework balances three needs:

- Safety: invalid requests must be refused clearly.
- Scientific fit: recommendations must match organism/platform/purpose.
- Engineering quality: generated Nextflow must be valid and coherent.

Score interpretation intent:

- 5: production-grade behavior
- 4: acceptable for operational use with minor caveats
- 3: usable but with notable risk/gaps
- 1-2: unsuitable without correction

This makes score thresholds practical:

- `>= 4` for quality-critical behavior
- `>= 3` acceptable for structural similarity in recreation where equivalent variants may exist

## 9) Full Test Pipeline (End-to-End)

1. `conftest.py` preflight:
   - checks keys/endpoints/index
2. Store and models initialized.
3. Scenario-driven tests execute.
4. Rate-limit pauses and retry policy applied.
5. Deterministic checks run.
6. Optional compiler checks run.
7. Optional judge scoring runs.
8. Results are aggregated by `ReportCollector`.
9. Final report saved to `test_reports/`.

## 10) Environment Variables

| Variable           | Required                 | Purpose                                 |
| ------------------ | ------------------------ | --------------------------------------- |
| `MISTRAL_API_KEY`  | Yes                      | Agent model access                      |
| `JUDGE_BASE_URL`   | Yes in current preflight | Judge model endpoint                    |
| `NF_FRAMEWORK_DIR` | Optional                 | Enables Nextflow syntax/stub validation |

Note: current `conftest.py` preflight exits if `JUDGE_BASE_URL` is missing.

## 11) How to Run

```bash
# Install core test deps
pip install pytest httpx

# Run all tests
pytest tests/ -v --tb=short

# Run by category
pytest tests/test_rag.py -v
pytest tests/test_consultant.py -v
pytest tests/test_execution.py -v
pytest tests/test_rejection.py -v
pytest tests/test_recreation.py -v

# Run one scenario by id keyword
pytest tests/ -v -k "L3_04_trim_assemble_amr"
```

## 12) Report Output and How to Read It

Generated files:

- `test_reports/test_report_<timestamp>.md`
- `test_reports/test_report_latest.md`

Report includes:

- Global pass/fail summary
- Level-by-level sectioning
- Per-scenario details
- Judge reasons and scores
- Compiler outcomes
- Retrieval coverage

This report is designed to be both audit-friendly and presentation-ready.

## 13) Categories You Can Present to Stakeholders

For simple communication, use these categories:

- Retrieval Quality
- Planning Quality
- Generation Quality
- Safety/Guardrail Quality
- Reference Fidelity
- Revision Robustness

Each category maps naturally to one or more test files.

## 14) Slide Deck Guidance (Non-Technical Audience)

Suggested 10-slide flow:

1. Problem: why pipeline generation quality matters.
2. What is being tested (the 6 test categories).
3. Scenario difficulty ladder (L1 -> L5).
4. Validation layers (deterministic, compiler, judge).
5. Safety focus (rejection guardrails examples).
6. Quality score guide (1-5 with plain meaning).
7. Results snapshot (pass/fail and averages).
8. Failure patterns and lessons learned.
9. Improvement backlog and next iteration plan.
10. Go/no-go recommendation.

## 15) Charts That Work Best

Recommended visuals:

- Stacked bar: pass/fail by level.
- Radar chart: average judge dimensions (faithfulness, relevance, syntax, logic, mapping, etc.).
- Heatmap: scenarios vs score dimensions.
- Funnel chart: total scenarios -> deterministic pass -> compiler pass -> quality >= 4.
- Trend line: score over time across weekly runs.
- Pareto chart: top recurring failure reasons.

If your audience is general business/science leadership, prioritize:

- Stacked bar
- Funnel
- Trend line

These three are easiest to understand quickly.

## 16) Example KPI Set for Tracking

Use these KPIs in dashboards/slides:

- Overall deterministic pass rate
- Overall quality pass rate (`score >= 4` policy)
- Guardrail rejection correctness rate
- RAG recall (% expected IDs found)
- Nextflow syntax pass rate
- Nextflow stub pass rate (complex only)
- Recreation fidelity pass rate
- Revision-flow success rate

## 17) Practical Interpretation Rules

- High deterministic + low quality score = technically runnable but scientifically/communicatively weak.
- High quality score + compiler fail = conceptually right but implementation not deployable yet.
- Guardrail failures are high severity even if other categories are strong.

## 18) Notes for Team Members

- Scenario IDs are descriptive and stable enough for regression tracking.
- The retry helper keeps best-scoring attempts for noisy LLM behavior.
- Final report is auto-saved at test-session end by `finalize_report` fixture.

## 19) Directory Guide

```
tests/
  conftest.py                 # preflight, fixtures, report finalization
  helpers.py                  # chat helpers, retries, judges, isolated builders
  nf_validation.py            # Nextflow syntax/stub validators
  error_patterns.py           # parser for Nextflow error patterns
  report.py                   # report collector/markdown builder
  evaluation/
    schemas.py                # structured score schemas
    prompts.py                # scoring rubrics/prompts
  scenarios/
    level1_simple.py
    level2_medium.py
    level3_complex.py
    level4_guardrails.py
    level5_recreation.py
  test_rag.py
  test_consultant.py
  test_execution.py
  test_rejection.py
  test_recreation.py
```

## 20) In One Sentence

This framework is not just checking whether code is produced, it verifies whether the AI is safe, scientifically relevant, technically valid, and reproducible under realistic bioinformatics workflow requests.
