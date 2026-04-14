"""
tests/scenarios/level1_simple.py
Level 1 — Simple: Single-tool pipeline requests

Each scenario tests that the system can handle a straightforward request
for a single tool. The conversation is short (2–3 turns).

Complexity: SIMPLE
  - User requests exactly one known tool
  - No conditional logic or multi-step workflows
  - Clear, unambiguous request with named tool
  - Expected: system identifies the tool and builds a basic pipeline
"""

import os

LEVEL1_SCENARIOS = [
    {
        "id": "L1_01_fastp_trim",
        "level": 1,
        "difficulty": "simple",
        "description": "Trim Illumina paired-end reads with fastp",
        "chat_messages": [
            "I want to trim my Illumina paired-end reads using fastp.",
            "Yes, that's exactly what I need. Please go ahead and build it.",
        ],
        "expect_approved": True,
        "expect_code": True,
        "expect_in_context": ["step_1PP_trimming__fastp"],
        "template_ids": [],
        "component_ids": ["step_1PP_trimming__fastp"],
        "expect_strategy": "CUSTOM_BUILD",
        "expect_template_id": None,
        "design_plan": "Execute custom pipeline. Step 1: Trim Illumina paired-end reads with fastp.",
        "selected_module_ids": ["step_1PP_trimming__fastp"],
    },
    {
        "id": "L1_02_spades_assembly",
        "level": 1,
        "difficulty": "simple",
        "description": "De novo assembly with SPAdes from trimmed reads",
        "chat_messages": [
            "I have trimmed reads and want to do de novo assembly with SPAdes.",
            "Yes, build the pipeline please.",
        ],
        "expect_approved": True,
        "expect_code": True,
        "expect_in_context": ["step_2AS_denovo__spades"],
        "template_ids": [],
        "component_ids": ["step_2AS_denovo__spades"],
        "expect_strategy": "CUSTOM_BUILD",
        "expect_template_id": None,
        "design_plan": "Execute custom pipeline. Step 1: De novo assembly of trimmed reads with SPAdes.",
        "selected_module_ids": ["step_2AS_denovo__spades"],
    },
    {
        "id": "L1_03_fastqc_qc",
        "level": 1,
        "difficulty": "simple",
        "description": "Quality check reads with FastQC",
        "chat_messages": [
            "I want to check the quality of my raw sequencing reads with FastQC.",
            "That's correct. Build it.",
        ],
        "expect_approved": True,
        "expect_code": True,
        "expect_in_context": ["step_0SQ_rawreads__fastq"],
        "template_ids": [],
        "component_ids": ["step_0SQ_rawreads__fastq"],
        "expect_strategy": "CUSTOM_BUILD",
        "expect_template_id": None,
        "design_plan": "Execute custom pipeline. Step 1: Run quality check on raw reads using FastQC.",
        "selected_module_ids": ["step_0SQ_rawreads__fastq"],
    },
    {
        "id": "L1_04_flye_nanopore",
        "level": 1,
        "difficulty": "simple",
        "description": "Assemble Nanopore long reads with Flye",
        "chat_messages": [
            "I want to assemble my Oxford Nanopore long reads with Flye.",
            "Yes, that's what I need. Please approve and build.",
        ],
        "expect_approved": True,
        "expect_code": True,
        "expect_in_context": ["step_2AS_denovo__flye"],
        "template_ids": [],
        "component_ids": ["step_2AS_denovo__flye"],
        "expect_strategy": "CUSTOM_BUILD",
        "expect_template_id": None,
        "design_plan": "Execute custom pipeline. Step 1: De novo assembly of Oxford Nanopore long reads using Flye.",
        "selected_module_ids": ["step_2AS_denovo__flye"],
    },
    {
        "id": "L1_05_chopper_nanopore",
        "level": 1,
        "difficulty": "simple",
        "description": "Trim Nanopore reads with Chopper",
        "chat_messages": [
            "I want to trim and filter my Nanopore reads using Chopper.",
            "Yes, please build the pipeline.",
        ],
        "expect_approved": True,
        "expect_code": True,
        "expect_in_context": ["step_1PP_trimming__chopper"],
        "template_ids": [],
        "component_ids": ["step_1PP_trimming__chopper"],
        "expect_strategy": "CUSTOM_BUILD",
        "expect_template_id": None,
        "design_plan": "Execute custom pipeline. Step 1: Trim and filter Nanopore reads using Chopper.",
        "selected_module_ids": ["step_1PP_trimming__chopper"],
    },
    {
        "id": "L1_RECREATION_REV_01_qc_fastqc_only",
        "level": 1,
        "difficulty": "simple",
        "description": "Revision: keep only FastQC in QC module",
        "chat_messages": [
            "I want to check the quality of my raw illumina reads.",
            "Approved.",
            "Please only use fastqc and nothing else.",
        ],
        "expect_approved": True,
        "expect_code": True,
        "expect_in_context": ["module_qc_fastqc", "step_0SQ_rawreads__fastq"],
        "template_ids": ["module_qc_fastqc"],
        "component_ids": ["step_0SQ_rawreads__fastq"],
        "expect_strategy": "EXACT_MATCH",
        "expect_template_id": "module_qc_fastqc",
        "design_plan": "Execute FastQC-only QC module. Step 1: Run FastQC on raw reads.",
        "selected_module_ids": ["step_0SQ_rawreads__fastq"],
    },
    {
        "id": "L1_RECREATION_REV_02_qc_nanoplot_only",
        "level": 1,
        "difficulty": "simple",
        "description": "Revision: enforce Nanoplot for Nanopore QC",
        "chat_messages": [
            "I have some nanopore reads. I want to check their quality.",
            "Approved.",
            "Please make sure you use nanoplot for this check.",
        ],
        "expect_approved": True,
        "expect_code": True,
        "expect_in_context": ["module_qc_nanoplot"],
        "template_ids": ["module_qc_nanoplot"],
        "component_ids": [],
        "expect_strategy": "EXACT_MATCH",
        "expect_template_id": "module_qc_nanoplot",
        "design_plan": "Execute Nanopore QC module with Nanoplot.",
        "selected_module_ids": [],
    },
    {
        "id": "L1_RECREATION_REV_03_qc_quast_only",
        "level": 1,
        "difficulty": "simple",
        "description": "Revision: enforce Quast for assembly QC",
        "chat_messages": [
            "I have some genome assemblies. I need to get the quality metrics for them.",
            "Approved.",
            "Please use quast to check the quality.",
        ],
        "expect_approved": True,
        "expect_code": True,
        "expect_in_context": ["module_qc_quast"],
        "template_ids": ["module_qc_quast"],
        "component_ids": [],
        "expect_strategy": "EXACT_MATCH",
        "expect_template_id": "module_qc_quast",
        "design_plan": "Execute assembly QC module with Quast.",
        "selected_module_ids": [],
    },
    {
        "id": "L1_RECREATION_REV_04_panaroo_confirm",
        "level": 1,
        "difficulty": "simple",
        "description": "Revision: enforce Panaroo for pangenome analysis",
        "chat_messages": [
            "I have some gene annotation files. I want to run a pangenome analysis on them.",
            "Approved.",
            "Make sure you use panaroo for this task.",
        ],
        "expect_approved": True,
        "expect_code": True,
        "expect_in_context": ["module_panaroo"],
        "template_ids": ["module_panaroo"],
        "component_ids": [],
        "expect_strategy": "EXACT_MATCH",
        "expect_template_id": "module_panaroo",
        "design_plan": "Execute pangenome analysis module with Panaroo.",
        "selected_module_ids": [],
    },
]

_LEGACY_LEVEL1_SCENARIOS = LEVEL1_SCENARIOS
NEW_LEVEL1_SCENARIOS = []

OLD_LEVEL1_TEST_IDS = [s["id"] for s in _LEGACY_LEVEL1_SCENARIOS]
NEW_LEVEL1_TEST_IDS = [s["id"] for s in NEW_LEVEL1_SCENARIOS]


def _env_enabled(var_name: str) -> bool:
    return os.getenv(var_name, "").strip().lower() in {"1", "true", "yes", "on"}


if _env_enabled("ONLY_NEW_SCENARIOS"):
    print("[tests] ONLY_NEW_SCENARIOS is enabled: not testing old Level 1 scenarios.")
    LEVEL1_SCENARIOS = NEW_LEVEL1_SCENARIOS
else:
    LEVEL1_SCENARIOS = _LEGACY_LEVEL1_SCENARIOS + NEW_LEVEL1_SCENARIOS
