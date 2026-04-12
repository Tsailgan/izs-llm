"""
tests/scenarios/level5_recreation.py
Level 5 — Code Recreation: Reconstruct modules from code_store_hollow.jsonl

Each scenario gives the AI a natural language description of a pipeline module
and asks it to build it through the API conversation. The generated Nextflow code
is then compared against the REFERENCE code from code_store_hollow.jsonl.

These tests use the run_multi_turn_chat() API client and the CodeRecreationEval judge.

The reference code is loaded at runtime from data/code_store_hollow.jsonl.
"""
import json
from pathlib import Path

# ──────────────────────────────────────────────────────────────
# Load reference code from code_store_hollow.jsonl
# ──────────────────────────────────────────────────────────────

PROJECT_DIR = Path(__file__).parent.parent.parent
_HOLLOW_PATH = PROJECT_DIR / "data" / "code_store_hollow.jsonl"

REFERENCE_CODE = {}

if _HOLLOW_PATH.exists():
    for line in _HOLLOW_PATH.open():
        line = line.strip()
        if not line:
            continue
        # Handle potential concatenated JSON objects
        parts = line.split("}{")
        for i, p in enumerate(parts):
            if i > 0:
                p = "{" + p
            if i < len(parts) - 1:
                p = p + "}"
            try:
                obj = json.loads(p)
                # Only keep first occurrence of each ID
                if obj["id"] not in REFERENCE_CODE:
                    REFERENCE_CODE[obj["id"]] = obj.get("content", "")
            except (json.JSONDecodeError, KeyError):
                pass


# ──────────────────────────────────────────────────────────────
# Recreation Scenarios
# ──────────────────────────────────────────────────────────────

LEVEL5_SCENARIOS = [
    # ── Core surveillance modules ──
    {
        "id": "L5_01_westnile",
        "level": 5,
        "difficulty": "complex",
        "description": "Recreate module_westnile: WNV lineage → dynamic ref → iVar mapping",
        "module_id": "module_westnile",
        "chat_messages": [
            "I need a West Nile Virus surveillance pipeline. It should first detect the WNV lineage from raw reads, "
            "then dynamically select the correct reference genome based on the detected lineage, "
            "and finally do consensus mapping with iVar against that lineage-specific reference.",
            "Yes, I want the lineage detection step to feed into the reference selection, which then feeds into iVar. "
            "I approve. Build the pipeline.",
        ],
    },
    {
        "id": "L5_02_covid_emergency",
        "level": 5,
        "difficulty": "complex",
        "description": "Recreate module_covid_emergency: iVar consensus + Pangolin lineage",
        "module_id": "module_covid_emergency",
        "chat_messages": [
            "I need the COVID emergency pipeline. It should map reads against Wuhan-Hu-1 with iVar "
            "for consensus calling, then run Pangolin for SARS-CoV-2 lineage classification.",
            "Yes, iVar first then Pangolin on the consensus. I approve, build it.",
        ],
    },
    {
        "id": "L5_03_denovo",
        "level": 5,
        "difficulty": "complex",
        "description": "Recreate module_denovo: conditional host depletion → SPAdes assembly",
        "module_id": "module_denovo",
        "chat_messages": [
            "I need a de novo assembly pipeline with optional host depletion. If a host reference genome "
            "is provided, it should run host depletion with Bowtie2 first. If no host reference, skip "
            "straight to assembly. Assembly should use SPAdes.",
            "Yes, the conditional logic is important — branch on whether host is available. I approve.",
        ],
    },
    {
        "id": "L5_04_typing_bacteria",
        "level": 5,
        "difficulty": "complex",
        "description": "Recreate module_typing_bacteria: species ID → mapping → MLST/cgMLST/AMR/annotation",
        "module_id": "module_typing_bacteria",
        "chat_messages": [
            "I need the comprehensive bacterial typing pipeline. It should: identify species with KmerFinder, "
            "optionally map reads to the best reference with Bowtie2 based on KmerFinder results, "
            "then run the full typing suite — MLST, cgMLST with chewBBACA, flaA typing, "
            "AMR screening with ABRicate and StarAMR, and gene annotation with Prokka.",
            "Yes, all those tools. The mapping step should use the reference dynamically selected by KmerFinder. I approve.",
        ],
    },
    {
        "id": "L5_05_draft_genome",
        "level": 5,
        "difficulty": "complex",
        "description": "Recreate module_draft_genome: Bowtie + iVar mapping + Prokka annotation",
        "module_id": "module_draft_genome",
        "chat_messages": [
            "I need a viral draft genome pipeline. It should: map reads to a reference with Bowtie2, "
            "generate consensus with iVar, then annotate the consensus with Prokka using the Viruses kingdom. "
            "The Prokka step needs the GenBank reference for annotation.",
            "Yes, I need all three steps chained: Bowtie mapping, iVar consensus, Prokka annotation. I approve.",
        ],
    },
    {
        "id": "L5_06_wgs_bacteria",
        "level": 5,
        "difficulty": "simple",
        "description": "Recreate module_wgs_bacteria: simple Shovill assembly",
        "module_id": "module_wgs_bacteria",
        "chat_messages": [
            "I need a simple bacterial WGS pipeline that takes trimmed reads and assembles them with Shovill.",
            "Yes, just Shovill assembly. I approve, build it.",
        ],
    },
    {
        "id": "L5_07_reads_processing",
        "level": 5,
        "difficulty": "complex",
        "description": "Recreate module_reads_processing: raw QC + trimming + Kraken classification",
        "module_id": "module_reads_processing",
        "chat_messages": [
            "I need a reads processing pipeline. It should: check raw read quality with FASTQ stats, "
            "then trim with both Trimmomatic and fastp, and finally run Kraken for taxonomic classification.",
            "Yes, I want all four steps: raw QC, Trimmomatic trimming, fastp trimming, and Kraken. I approve.",
        ],
    },
    {
        "id": "L5_08_filtered_denovo",
        "level": 5,
        "difficulty": "medium",
        "description": "Recreate module_filtered_denovo: Bowtie filtering → SPAdes assembly",
        "module_id": "module_filtered_denovo",
        "chat_messages": [
            "I need a pipeline that filters reads by mapping to a reference with Bowtie2, "
            "then takes only the mapped/filtered reads and assembles them with SPAdes.",
            "Yes, filter first then assemble. I approve.",
        ],
    },
    {
        "id": "L5_09_scaffolds_filtering",
        "level": 5,
        "difficulty": "complex",
        "description": "Recreate module_scaffolds_filtering: ABRicate species ID → SeqIO filtering",
        "module_id": "module_scaffolds_filtering",
        "chat_messages": [
            "I need a scaffolds filtering pipeline. It should run VirDabricate for species identification "
            "on assembled scaffolds, then use SeqIO to filter the scaffolds based on the identification results "
            "and a reference genome.",
            "Yes, VirDabricate calls first, then SeqIO filtering using those calls plus the assembly and reference. I approve.",
        ],
    },
    {
        "id": "L5_10_plasmids",
        "level": 5,
        "difficulty": "medium",
        "description": "Recreate module_plasmids: MOB-suite plasmid detection",
        "module_id": "module_plasmids",
        "chat_messages": [
            "I need a plasmid detection pipeline using MOB-suite on assembled bacterial genomes.",
            "Yes, just MOB-suite for plasmid identification and typing. I approve.",
        ],
    },
    {
        "id": "L5_11_variant_lineage_fixed",
        "level": 5,
        "difficulty": "complex",
        "description": "Recreate module_variant_lineage_FIXED: iVar mapping + Pangolin lineage",
        "module_id": "module_variant_lineage_FIXED",
        "chat_messages": [
            "I need a variant lineage pipeline. Map reads to the reference with iVar for consensus, "
            "then run Pangolin on the consensus for SARS-CoV-2 lineage classification.",
            "Yes, iVar consensus first, then Pangolin. I approve.",
        ],
    },
    {
        "id": "L5_12_segmented",
        "level": 5,
        "difficulty": "medium",
        "description": "Recreate module_segmented: iVar mapping for segmented viruses",
        "module_id": "module_segmented",
        "chat_messages": [
            "I need a pipeline for segmented virus analysis. Map reads to multiple reference segments "
            "using iVar for consensus generation.",
            "Yes, iVar mapping against the segmented reference. I approve.",
        ],
    },
    {
        "id": "L5_13_enterotoxin",
        "level": 5,
        "difficulty": "medium",
        "description": "Recreate module_enterotoxin_saureus_finder: Unicycler assembly + BLAST AMR",
        "module_id": "module_enterotoxin_saureus_finder",
        "chat_messages": [
            "I need an S. aureus enterotoxin detection pipeline. Assemble with Unicycler, "
            "then run BLAST for AMR/toxin gene detection.",
            "Yes, Unicycler assembly then BLAST search. I approve.",
        ],
    },
    {
        "id": "L5_14_vdraft_light",
        "level": 5,
        "difficulty": "complex",
        "description": "Recreate module_vdraft_light: host depletion + Bowtie mapping",
        "module_id": "module_vdraft_light",
        "chat_messages": [
            "I need a lightweight viral draft pipeline. First deplete host reads with Bowtie2, "
            "then map the depleted reads to the viral reference with Bowtie2 for consensus.",
            "Yes, two Bowtie2 steps: host depletion then reference mapping. I approve.",
        ],
    },
]
