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
]
