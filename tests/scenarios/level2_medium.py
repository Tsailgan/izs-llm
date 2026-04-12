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
    },
]
