"""
tests/scenarios/level3_complex.py
Level 3 — Complex: Multi-step pipeline construction

Each scenario requires the system to chain 3+ tools into a coherent pipeline,
handling channel wiring, multi-step data flow, and cross-domain analysis.

Complexity: COMPLEX
  - User describes a multi-step analysis spanning 3+ bioinformatics domains
  - Requires correct channel routing between steps
  - May need custom pipeline construction (no single template covers it)
  - Expected: system builds a complete, functional multi-step pipeline
"""

LEVEL3_SCENARIOS = [
    {
        "id": "L3_01_bacteria_typing_full",
        "level": 3,
        "difficulty": "complex",
        "description": "Bacterial isolate characterization: species ID + MLST + AMR",
        "chat_messages": [
            "I have bacterial Illumina isolates from a foodborne outbreak. I need to identify the species, run MLST for epidemiological typing, and find antimicrobial resistance genes.",
            "The isolates are Campylobacter jejuni. I have paired-end 2x150bp Illumina reads, already trimmed.",
            "Yes, I want KmerFinder for species, MLST for sequence typing, and ABRicate for AMR screening. That covers everything I need.",
            "I approve. Build the pipeline.",
        ],
        "expect_approved": True,
        "expect_code": True,
    },
    {
        "id": "L3_02_viral_genome_reconstruction",
        "level": 3,
        "difficulty": "complex",
        "description": "Viral genome reconstruction: mapping + consensus + Prokka annotation",
        "chat_messages": [
            "I want to reconstruct a viral genome from Illumina reads. I need reference mapping, consensus generation, and then gene annotation with Prokka.",
            "It's a flavivirus sample. I have the reference FASTA and GenBank files ready. The reads are paired-end Illumina, already trimmed.",
            "Yes, use iVar for mapping and consensus, then Prokka for annotation. I approve, please build.",
        ],
        "expect_approved": True,
        "expect_code": True,
    },
    {
        "id": "L3_03_selective_assembly",
        "level": 3,
        "difficulty": "complex",
        "description": "Extract mapped reads + de novo assembly of selected fraction",
        "chat_messages": [
            "I have a mixed clinical sample with host contamination. I want to extract only the reads that map to a specific pathogen reference, then assemble only those reads de novo.",
            "It's an Illumina paired-end sample. I have the pathogen reference FASTA. I want to use Bowtie2 for filtering, then SPAdes for assembly.",
            "Yes, that's the workflow I need. Filter first, then assemble the filtered reads. I approve.",
        ],
        "expect_approved": True,
        "expect_code": True,
    },
    {
        "id": "L3_04_trim_assemble_amr",
        "level": 3,
        "difficulty": "complex",
        "description": "Trimming + de novo assembly + AMR detection: fastp → SPAdes → ABRicate",
        "chat_messages": [
            "I want to trim Illumina reads with fastp, do de novo assembly with SPAdes, and then run ABRicate for AMR gene detection on the assemblies.",
            "Yes, the reads are raw paired-end Illumina from bacterial isolates. I need all three steps chained together.",
            "I approve. Build the full pipeline.",
        ],
        "expect_approved": True,
        "expect_code": True,
    },
    {
        "id": "L3_05_bacteria_full_workflow",
        "level": 3,
        "difficulty": "complex",
        "description": "Full bacterial workflow: trim → assemble → species ID → MLST",
        "chat_messages": [
            "I have bacterial isolates from environmental monitoring. I need a complete workflow: trim with fastp, assemble with Shovill, identify species with KmerFinder, and run MLST.",
            "The samples are Listeria monocytogenes from a food processing plant. Illumina paired-end reads.",
            "Yes, all four steps in sequence. I approve, build it.",
        ],
        "expect_approved": True,
        "expect_code": True,
    },
    {
        "id": "L3_06_hostdepl_assemble_annotate",
        "level": 3,
        "difficulty": "complex",
        "description": "Host depletion + assembly + annotation: Bowtie → SPAdes → Prokka",
        "chat_messages": [
            "I want to do host depletion with Bowtie, then assemble the depleted reads with SPAdes, and annotate the assembled contigs with Prokka.",
            "The host is bovine (Bos taurus). The sample is from a clinical veterinary case. Illumina paired-end reads.",
            "Yes, host depletion first, then assembly, then annotation. I approve.",
        ],
        "expect_approved": True,
        "expect_code": True,
    },
]
