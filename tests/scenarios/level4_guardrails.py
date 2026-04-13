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
        "template_ids": [],
        "component_ids": ["step_2AS_mapping__bowtie", "step_2AS_mapping__minimap2", "step_2AS_mapping__ivar", "step_2AS_mapping__snippy"],
        "expect_in_context": ["step_2AS_mapping__bowtie", "step_2AS_mapping__minimap2", "step_2AS_mapping__ivar", "step_2AS_mapping__snippy"],
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
        "template_ids": [],
        "component_ids": ["step_2AS_denovo__flye", "step_2AS_hybrid__unicycler"],
        "expect_in_context": ["step_2AS_denovo__flye", "step_2AS_hybrid__unicycler"],
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
        "template_ids": [],
        "component_ids": ["step_4TY_lineage__pangolin", "step_4TY_MLST__mlst", "step_4TY_cgMLST__chewbbaca"],
        "expect_in_context": ["step_4TY_lineage__pangolin", "step_4TY_MLST__mlst", "step_4TY_cgMLST__chewbbaca"],
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
        "template_ids": [],
        "component_ids": ["step_2AS_mapping__ivar", "step_2AS_denovo__spades", "step_2AS_denovo__shovill", "step_2AS_denovo__unicycler"],
        "expect_in_context": ["step_2AS_mapping__ivar", "step_2AS_denovo__spades", "step_2AS_denovo__shovill", "step_2AS_denovo__unicycler"],
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
        "template_ids": [],
        "component_ids": ["step_1PP_trimming__fastp", "step_1PP_trimming__trimmomatic", "step_1PP_trimming__chopper"],
        "expect_in_context": ["step_1PP_trimming__fastp", "step_1PP_trimming__trimmomatic", "step_1PP_trimming__chopper"],
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
        "template_ids": [],
        "component_ids": ["step_2AS_mapping__ivar", "step_2AS_mapping__snippy", "step_2AS_mapping__medaka"],
        "expect_in_context": ["step_2AS_mapping__ivar", "step_2AS_mapping__snippy", "step_2AS_mapping__medaka"],
        "rejection_reason": (
            "GATK (Genome Analysis Toolkit) is NOT available in this framework. "
            "For variant calling/consensus: iVar (step_2AS_mapping__ivar), "
            "Snippy (step_2AS_mapping__snippy), Medaka (step_2AS_mapping__medaka for Nanopore)."
        ),
    },
    {
        "id": "L4_REV_01_kallisto_not_available",
        "level": 4,
        "difficulty": "easy",
        "description": "Reject: Kallisto not in catalog",
        "chat_messages": [
            "I want to align my sequences. Please use kallisto for the alignment.",
        ],
        "expect_rejection": True,
        "template_ids": [],
        "component_ids": ["step_2AS_mapping__bowtie", "step_2AS_mapping__minimap2", "step_2AS_mapping__ivar"],
        "expect_in_context": ["step_2AS_mapping__bowtie", "step_2AS_mapping__minimap2", "step_2AS_mapping__ivar"],
        "rejection_reason": (
            "Kallisto is NOT available in this framework. "
            "Use supported alignment/mapping tools such as Bowtie2, Minimap2, or iVar depending on data type and objective."
        ),
    },
    {
        "id": "L4_REV_02_chewbbaca_wrong_organism",
        "level": 4,
        "difficulty": "medium",
        "description": "Reject: chewBBACA requested for SARS-CoV-2",
        "chat_messages": [
            "I have a sars cov 2 sample. I want to run chewbbaca on it to find the sequence type.",
        ],
        "expect_rejection": True,
        "template_ids": [],
        "component_ids": ["step_4TY_cgMLST__chewbbaca", "step_4TY_lineage__pangolin"],
        "expect_in_context": ["step_4TY_cgMLST__chewbbaca", "step_4TY_lineage__pangolin"],
        "rejection_reason": (
            "chewBBACA is a bacterial cgMLST typing tool and is not valid for SARS-CoV-2. "
            "For SARS-CoV-2 typing/lineage use Pangolin."
        ),
    },
    {
        "id": "L4_REV_03_bowtie_wrong_for_nanopore_long",
        "level": 4,
        "difficulty": "medium",
        "description": "Reject: Bowtie for Nanopore long-read mapping",
        "chat_messages": [
            "I have nanopore long reads. I want to map them to my reference using bowtie.",
        ],
        "expect_rejection": True,
        "template_ids": [],
        "component_ids": ["step_2AS_mapping__bowtie", "step_2AS_mapping__minimap2"],
        "expect_in_context": ["step_2AS_mapping__bowtie", "step_2AS_mapping__minimap2"],
        "rejection_reason": (
            "Bowtie2 is intended for short reads. Nanopore long reads should be mapped with Minimap2 in this framework."
        ),
    },
    {
        "id": "L4_REV_04_medaka_wrong_for_illumina",
        "level": 4,
        "difficulty": "medium",
        "description": "Reject: Medaka requested for Illumina",
        "chat_messages": [
            "I have illumina reads and a reference. I want to map them using medaka.",
        ],
        "expect_rejection": True,
        "template_ids": [],
        "component_ids": ["step_2AS_mapping__medaka", "step_2AS_mapping__bowtie", "step_2AS_mapping__ivar"],
        "expect_in_context": ["step_2AS_mapping__medaka", "step_2AS_mapping__bowtie", "step_2AS_mapping__ivar"],
        "rejection_reason": (
            "Medaka is designed for Nanopore consensus polishing and is incompatible with Illumina reads. "
            "Use Bowtie2 or iVar for Illumina mapping workflows."
        ),
    },
    {
        "id": "L4_REV_05_abricate_missing_prereq_reads",
        "level": 4,
        "difficulty": "easy",
        "description": "Reject: ABRicate directly on raw FASTQ",
        "chat_messages": [
            "I have raw fastq reads. I want to run abricate directly on them to find amr genes.",
        ],
        "expect_rejection": True,
        "template_ids": [],
        "component_ids": ["step_4AN_AMR__abricate", "step_2AS_denovo__spades", "step_2AS_denovo__shovill"],
        "expect_in_context": ["step_4AN_AMR__abricate", "step_2AS_denovo__spades", "step_2AS_denovo__shovill"],
        "rejection_reason": (
            "ABRicate requires assembled contigs, not raw FASTQ reads. "
            "Assemble first with a supported assembler (e.g., SPAdes or Shovill), then run ABRicate."
        ),
    },
    {
        "id": "L4_REV_06_bwa_not_available_alt",
        "level": 4,
        "difficulty": "easy",
        "description": "Reject: BWA explicitly requested",
        "chat_messages": [
            "I want to align my short reads using bwa. Please build this pipeline.",
        ],
        "expect_rejection": True,
        "template_ids": [],
        "component_ids": ["step_2AS_mapping__bowtie", "step_2AS_mapping__minimap2", "step_2AS_mapping__ivar"],
        "expect_in_context": ["step_2AS_mapping__bowtie", "step_2AS_mapping__minimap2", "step_2AS_mapping__ivar"],
        "rejection_reason": (
            "BWA is not part of the available tool catalog in this framework. "
            "Use Bowtie2 or iVar for short-read reference mapping depending on workflow needs."
        ),
    },
    {
        "id": "L4_REV_07_pangolin_wrong_for_salmonella",
        "level": 4,
        "difficulty": "medium",
        "description": "Reject: Pangolin requested for Salmonella",
        "chat_messages": [
            "I have some salmonella reads. I want to map them and then use pangolin to find the variant lineage.",
        ],
        "expect_rejection": True,
        "template_ids": [],
        "component_ids": ["step_4TY_lineage__pangolin", "step_4TY_MLST__mlst", "step_4TY_cgMLST__chewbbaca"],
        "expect_in_context": ["step_4TY_lineage__pangolin", "step_4TY_MLST__mlst", "step_4TY_cgMLST__chewbbaca"],
        "rejection_reason": (
            "Pangolin applies only to SARS-CoV-2 lineage classification and is invalid for Salmonella. "
            "Use bacterial typing tools such as MLST or cgMLST instead."
        ),
    },
    {
        "id": "L4_REV_08_ivar_wrong_purpose_denovo",
        "level": 4,
        "difficulty": "easy",
        "description": "Reject: iVar requested for de novo assembly",
        "chat_messages": [
            "I want to do a de novo assembly of my bacterial genome. Please use ivar for the assembly step.",
        ],
        "expect_rejection": True,
        "template_ids": [],
        "component_ids": ["step_2AS_mapping__ivar", "step_2AS_denovo__spades", "step_2AS_denovo__shovill", "step_2AS_denovo__unicycler"],
        "expect_in_context": ["step_2AS_mapping__ivar", "step_2AS_denovo__spades", "step_2AS_denovo__shovill", "step_2AS_denovo__unicycler"],
        "rejection_reason": (
            "iVar is for reference-guided consensus and cannot perform de novo assembly. "
            "Use SPAdes, Shovill, or Unicycler for de novo assembly tasks."
        ),
    },
    {
        "id": "L4_REV_09_fastp_wrong_for_nanopore",
        "level": 4,
        "difficulty": "medium",
        "description": "Reject: fastp requested for Nanopore long reads",
        "chat_messages": [
            "I have nanopore long reads. I want to trim them first. Please use fastp for the trimming.",
        ],
        "expect_rejection": True,
        "template_ids": [],
        "component_ids": ["step_1PP_trimming__fastp", "step_1PP_trimming__chopper"],
        "expect_in_context": ["step_1PP_trimming__fastp", "step_1PP_trimming__chopper"],
        "rejection_reason": (
            "fastp is intended for short-read data. Nanopore long-read trimming should use Chopper in this framework."
        ),
    },
    {
        "id": "L4_REV_10_prokka_missing_prereq_reads",
        "level": 4,
        "difficulty": "easy",
        "description": "Reject: Prokka directly on raw FASTQ",
        "chat_messages": [
            "I have raw fastq reads from my sequencer. I want to run prokka on them to find the genes.",
        ],
        "expect_rejection": True,
        "template_ids": [],
        "component_ids": ["step_4AN_genes__prokka", "step_2AS_denovo__spades", "step_2AS_denovo__shovill", "step_2AS_denovo__unicycler"],
        "expect_in_context": ["step_4AN_genes__prokka", "step_2AS_denovo__spades", "step_2AS_denovo__shovill", "step_2AS_denovo__unicycler"],
        "rejection_reason": (
            "Prokka annotates assembled contigs/genomes and cannot run directly on raw reads. "
            "Assemble first, then run Prokka for gene annotation."
        ),
    },
]
