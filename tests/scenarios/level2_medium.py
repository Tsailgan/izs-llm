"""
tests/scenarios/level2_medium.py
Level 2 — Medium: Template-level pipeline requests

Each scenario tests multi-step pipelines that typically map to a known template.
Conversations are 3–5 turns with the user providing biological context.

Complexity: MEDIUM
  - User describes a biological scenario requiring 2–3 tools
  - Usually maps to an existing template in the catalog
  - Requires understanding of organism + sequencing platform
  - Expected: system selects appropriate template and builds pipeline
"""

LEVEL2_SCENARIOS = [
    {
        "id": "L2_01_covid_mapping_lineage",
        "level": 2,
        "difficulty": "medium",
        "description": "SARS-CoV-2 mapping and Pangolin lineage assignment",
        "chat_messages": [
            "I have SARS-CoV-2 samples from a hospital outbreak and need to do mapping and lineage assignment with Pangolin.",
            "Yes, I have paired-end Illumina data. The reads are already trimmed with fastp by our core facility.",
            "That sounds right. I approve the plan, please build the pipeline.",
        ],
        "expect_approved": True,
        "expect_code": True,
        "expect_in_context": ["module_covid_emergency", "step_4TY_lineage__pangolin"],
        "template_ids": ["module_covid_emergency"],
        "component_ids": ["step_2AS_mapping__ivar", "step_4TY_lineage__pangolin"],
        "expect_strategy": "EXACT_MATCH",
        "expect_template_id": "module_covid_emergency",
        "design_plan": "Execute the COVID emergency pipeline. Step 1: Map reads against Wuhan-Hu-1 with iVar for consensus calling. Step 2: Run Pangolin for SARS-CoV-2 lineage classification.",
        "selected_module_ids": ["step_2AS_mapping__ivar", "step_4TY_lineage__pangolin"],
    },
    {
        "id": "L2_02_denovo_host_depletion",
        "level": 2,
        "difficulty": "medium",
        "description": "De novo assembly with host depletion using Bowtie2 + SPAdes",
        "chat_messages": [
            "I want to do de novo assembly on clinical samples, but first I need to remove the host reads. The samples are from bovine respiratory tissue.",
            "Yes, I have the Bos taurus reference genome. I'm using Illumina paired-end data.",
            "Perfect, I approve. Build it.",
        ],
        "expect_approved": True,
        "expect_code": True,
        "expect_in_context": ["module_denovo", "step_2AS_mapping__bowtie"],
        "template_ids": ["module_denovo"],
        "component_ids": ["step_2AS_mapping__bowtie", "step_2AS_denovo__spades"],
        "expect_strategy": "EXACT_MATCH",
        "expect_template_id": "module_denovo",
        "design_plan": "Execute the de novo assembly pipeline with host depletion. Step 1: Deplete host reads with Bowtie2. Step 2: Assemble remaining reads with SPAdes.",
        "selected_module_ids": ["step_2AS_mapping__bowtie", "step_2AS_denovo__spades"],
    },
    {
        "id": "L2_03_westnile_lineage",
        "level": 2,
        "difficulty": "medium",
        "description": "West Nile Virus lineage detection and reference mapping",
        "chat_messages": [
            "I have West Nile Virus samples from dead corvids in the Abruzzo region. I need to determine the lineage and then do consensus mapping.",
            "Yes, I have paired-end Illumina reads from brain tissue. The reads are already trimmed.",
            "That's exactly what I need. I approve, please build it.",
        ],
        "expect_approved": True,
        "expect_code": True,
        "expect_in_context": ["module_westnile", "step_4TY_lineage__westnile"],
        "template_ids": ["module_westnile"],
        "component_ids": ["step_4TY_lineage__westnile"],
        "expect_strategy": "EXACT_MATCH",
        "expect_template_id": "module_westnile",
        "design_plan": "Execute the standard WNV surveillance pipeline. Step 1: Detect WNV lineage from raw reads using the westnile lineage tool. Step 2: Dynamically select the correct reference genome. Step 3: Perform consensus mapping with iVar.",
        "selected_module_ids": ["step_4TY_lineage__westnile"],
    },
    {
        "id": "L2_04_bowtie2_mapping",
        "level": 2,
        "difficulty": "medium",
        "description": "Map reads to a reference genome using Bowtie2",
        "chat_messages": [
            "I want to map my trimmed Illumina reads to a reference genome using Bowtie2. I have the reference FASTA ready.",
            "Yes, that's correct. I approve, build the pipeline.",
        ],
        "expect_approved": True,
        "expect_code": True,
        "expect_in_context": ["step_2AS_mapping__bowtie"],
        "template_ids": [],
        "component_ids": ["step_2AS_mapping__bowtie"],
        "expect_strategy": "CUSTOM_BUILD",
        "expect_template_id": None,
        "design_plan": "Execute a custom pipeline. Step 1: Map trimmed Illumina reads to a reference genome using Bowtie2.",
        "selected_module_ids": ["step_2AS_mapping__bowtie"],
    },
    {
        "id": "L2_05_kmerfinder_species",
        "level": 2,
        "difficulty": "medium",
        "description": "Species identification with KmerFinder on assemblies",
        "chat_messages": [
            "I have assembled bacterial genomes and want to do species identification using KmerFinder.",
            "Yes, the assemblies are from Shovill. I want to confirm the species before running downstream analysis.",
            "I approve. Build it.",
        ],
        "expect_approved": True,
        "expect_code": True,
        "expect_in_context": ["step_3TX_species__kmerfinder"],
        "template_ids": [],
        "component_ids": ["step_3TX_species__kmerfinder"],
        "expect_strategy": "CUSTOM_BUILD",
        "expect_template_id": None,
        "design_plan": "Execute a custom pipeline. Step 1: Species identification using KmerFinder on assembled genomes.",
        "selected_module_ids": ["step_3TX_species__kmerfinder"],
    },
]
