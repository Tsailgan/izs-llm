"""
tests/scenarios/level4_guardrails.py
Level 4 — Negative: Rejection / Guardrail Tests

These scenarios test that the system correctly REJECTS invalid requests.
The user asks for tools or combinations that are impossible or unavailable.

Complexity: MEDIUM (the request itself is simple, but correct rejection requires domain expertise)
  - Tools not in the catalog (BWA, Canu, TrimGalore, GATK)
  - Tools applied to wrong organism (Pangolin for bacteria)
  - Tools for wrong sequencing tech (Flye for Illumina)
  - Tools for wrong purpose (iVar for de novo assembly)

Expected behavior:
  - Status remains CHATTING (never APPROVED)
  - No pipeline code is generated
  - AI explains WHY and suggests valid alternatives
"""

LEVEL4_SCENARIOS = [
    {
        "id": "L4_01_bwa_not_available",
        "level": 4,
        "difficulty": "medium",
        "description": "Reject: BWA not in catalog",
        "chat_messages": [
            "I want to do mapping with BWA on my Illumina paired-end reads.",
        ],
        "expect_rejection": True,
        "rejection_reason": (
            "BWA and BWA-MEM2 are NOT available in this framework. "
            "Available mapping tools include: Bowtie2 (step_2AS_mapping__bowtie), "
            "Minimap2 (step_2AS_mapping__minimap2), iVar (step_2AS_mapping__ivar), "
            "Snippy (step_2AS_mapping__snippy)."
        ),
    },
    {
        "id": "L4_02_canu_not_available",
        "level": 4,
        "difficulty": "medium",
        "description": "Reject: Canu not in catalog",
        "chat_messages": [
            "I want to assemble my Nanopore long reads with Canu.",
        ],
        "expect_rejection": True,
        "rejection_reason": (
            "Canu is NOT available in this framework. "
            "Available long-read assemblers include: Flye (step_2AS_denovo__flye). "
            "For hybrid assembly: Unicycler (step_2AS_hybrid__unicycler)."
        ),
    },
    {
        "id": "L4_03_pangolin_bacteria",
        "level": 4,
        "difficulty": "medium",
        "description": "Reject: Pangolin for Salmonella (wrong organism)",
        "chat_messages": [
            "I have Salmonella samples and want to determine lineage with Pangolin.",
        ],
        "expect_rejection": True,
        "rejection_reason": (
            "Pangolin (step_4TY_lineage__pangolin) is exclusively for SARS-CoV-2 lineage "
            "classification using the PANGO nomenclature. It CANNOT be applied to bacterial "
            "genomes. For Salmonella typing: MLST (step_4TY_MLST__mlst), "
            "cgMLST (step_4TY_cgMLST__chewbbaca)."
        ),
    },
    {
        "id": "L4_04_ivar_denovo",
        "level": 4,
        "difficulty": "medium",
        "description": "Reject: iVar for de novo assembly (wrong purpose)",
        "chat_messages": [
            "I want to do de novo assembly of my bacterial isolates using iVar.",
        ],
        "expect_rejection": True,
        "rejection_reason": (
            "iVar (step_2AS_mapping__ivar) is a reference-based consensus caller — it requires "
            "a reference genome and CANNOT perform de novo assembly. For de novo assembly: "
            "SPAdes (step_2AS_denovo__spades), Shovill (step_2AS_denovo__shovill), "
            "Unicycler (step_2AS_denovo__unicycler)."
        ),
    },
    {
        "id": "L4_05_trimgalore_not_available",
        "level": 4,
        "difficulty": "medium",
        "description": "Reject: TrimGalore not in catalog",
        "chat_messages": [
            "I want to run TrimGalore on my Illumina reads for quality trimming.",
        ],
        "expect_rejection": True,
        "rejection_reason": (
            "TrimGalore is NOT available in this framework. "
            "Available trimming tools include: fastp (step_1PP_trimming__fastp), "
            "Trimmomatic (step_1PP_trimming__trimmomatic). "
            "For Nanopore: Chopper (step_1PP_trimming__chopper)."
        ),
    },
    {
        "id": "L4_06_gatk_not_available",
        "level": 4,
        "difficulty": "medium",
        "description": "Reject: GATK not in catalog",
        "chat_messages": [
            "I want to use GATK for variant calling on my bacterial whole genome sequencing data.",
        ],
        "expect_rejection": True,
        "rejection_reason": (
            "GATK (Genome Analysis Toolkit) is NOT available in this framework. "
            "For variant calling/consensus: iVar (step_2AS_mapping__ivar), "
            "Snippy (step_2AS_mapping__snippy), Medaka (step_2AS_mapping__medaka for Nanopore)."
        ),
    },
]
