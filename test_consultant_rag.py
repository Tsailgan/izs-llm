import pytest
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langgraph.store.memory import InMemoryStore

from app.services.tools import retrieve_rag_context
from app.services.agents import CONSULTANT_SYSTEM_PROMPT
from app.models.consultant_structure import ConsultantOutput
from app.services.llm import get_llm, get_judge_llm, with_rate_limit_retry

class AcademicEval(BaseModel):
    faithfulness_score: int = Field(description="Score 1 to 5. Did the AI only use tools from the RAG context. Give 1 if it invented any tool.")
    faithfulness_reason: str = Field(description="Explain the faithfulness score.")
    relevance_score: int = Field(description="Score 1 to 5. Did the AI directly answer the biological question.")
    relevance_reason: str = Field(description="Explain the relevance score.")

def test_rag_retrieval_virologist_wnv():
    store = InMemoryStore()
    
    query = "We have a large bird die-off in the area. I suspect it is West Nile. I need a pipeline to analyze the sequence data and figure out the exact viral lineage."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "module_westnile" in context.lower(), "Context Relevance Failed. Missing template."
    assert "step_4TY_lineage__westnile" in context.lower(), "Context Relevance Failed. Missing tool."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_virologist_wnv():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("human", "{query}")
    ])
    
    mock_context = """
    Component ID step_4TY_lineage__westnile Description Compute lineage to identify the best reference.
    Template ID module_westnile Description West Nile Virus surveillance pipeline.
    """
    
    query = "We have a large bird die-off in the area. I suspect it is West Nile. I need a pipeline to analyze the sequence data and figure out the exact viral lineage."
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "query": query
    })
    
    assert result.used_template_id == "module_westnile", "Logic Failed. Wrong template."
    assert "step_4TY_lineage__westnile" in result.selected_module_ids, "Logic Failed. Missing module."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_virologist_wnv():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("human", "{query}")
    ])
    
    mock_context = """
    Template ID module_westnile Description West Nile Virus surveillance pipeline.
    """
    
    query = "We have a large bird die-off in the area. I suspect it is West Nile. I need a pipeline to analyze the sequence data and figure out the exact viral lineage."
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "query": query
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer evaluating an AI system. Read the RAG context and the AI reply. Give strict scores for Faithfulness and Relevance."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": query,
        "reply": consultant_response.response_to_user
    })
    
    print("\nFaithfulness " + str(evaluation.faithfulness_score) + " - " + evaluation.faithfulness_reason)
    print("Relevance " + str(evaluation.relevance_score) + " - " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low."

def test_rag_retrieval_vet_mixed_swab():
    store = InMemoryStore()
    
    query = "I have a mixed environmental swab from the clinic floor. I just need to process the raw reads and see every bacterial species inside it."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "module_reads_processing" in context.lower(), "Context Relevance Failed. Missing reads processing template."
    assert "kraken" in context.lower(), "Context Relevance Failed. Missing Kraken taxonomy tool."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_vet_mixed_swab():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_reads_processing Description Comprehensive reads preprocessing and Taxonomic classification with Kraken.
    Component ID step_3TX_class__kraken Description Taxonomic classification.
    """
    
    # Here we simulate a multi-turn chat history
    chat_history = [
        HumanMessage(content="I want to check a clinic floor swab for bacteria."),
        AIMessage(content="I can help with that. Do you want to assemble the genomes or just do a taxonomic classification to see what species are there?"),
        HumanMessage(content="Just the taxonomic classification from the raw reads please. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.used_template_id == "module_reads_processing", "Logic Failed. Wrong template."
    assert result.status == "APPROVED", "Logic Failed. Agent did not approve the final ready command."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_vet_mixed_swab():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_reads_processing Description Comprehensive reads preprocessing and Taxonomic classification with Kraken.
    """
    
    chat_history = [
        HumanMessage(content="I want to check a clinic floor swab for bacteria. Just tell me what species are in the raw reads.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer evaluating an AI system. Read the RAG context and the AI reply. Give strict scores for Faithfulness and Relevance."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[Mixed Swab Eval] Faithfulness " + str(evaluation.faithfulness_score) + " - " + evaluation.faithfulness_reason)
    print("[Mixed Swab Eval] Relevance " + str(evaluation.relevance_score) + " - " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low."

def test_rag_retrieval_virologist_draft_genome():
    store = InMemoryStore()
    
    query = "We isolated a new viral strain from a farm animal. I need to map the reads to a close relative to get a consensus sequence and then annotate the genes."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "module_draft_genome" in context.lower(), "Context Relevance Failed. Missing genome draft template."
    assert "prokka" in context.lower(), "Context Relevance Failed. Missing Prokka annotation tool."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_virologist_draft_genome():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_draft_genome Description Viral genome reconstruction and annotation pipeline using iVar and Prokka.
    Component ID step_4AN_genes__prokka Description Annotate consensus sequences.
    """
    
    chat_history = [
        HumanMessage(content="We isolated a new viral strain. I need a pipeline to map it get the consensus and annotate the viral genes.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.used_template_id == "module_draft_genome", "Logic Failed. Wrong template."
    assert "step_4AN_genes__prokka" in result.selected_module_ids, "Logic Failed. Missing annotation module."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_virologist_draft_genome():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_draft_genome Description Viral genome reconstruction and annotation pipeline using iVar and Prokka.
    """
    
    chat_history = [
        HumanMessage(content="We isolated a new viral strain. I need a pipeline to map it get the consensus and annotate the viral genes.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer evaluating an AI system. Read the RAG context and the AI reply. Give strict scores for Faithfulness and Relevance."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[Draft Genome Eval] Faithfulness " + str(evaluation.faithfulness_score) + " - " + evaluation.faithfulness_reason)
    print("[Draft Genome Eval] Relevance " + str(evaluation.relevance_score) + " - " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low."

from langchain_core.messages import HumanMessage, AIMessage

def test_rag_retrieval_adapt_covid_pipeline():
    store = InMemoryStore()
    
    query = "I want to run the Covid Emergency Pipeline but I want to use Snippy instead of iVar for the mapping step. Please keep Pangolin for the lineage."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "module_covid_emergency" in context.lower(), "Context Relevance Failed Missing Covid template."
    assert "step_2AS_mapping__snippy" in context.lower(), "Context Relevance Failed Missing Snippy tool."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_adapt_covid_pipeline():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_covid_emergency Description Fast SARS-CoV-2 analysis pipeline using iVar and Pangolin.
    Component ID step_2AS_mapping__snippy Description Rapid variant calling and core genome alignment pipeline.
    Component ID step_4TY_lineage__pangolin Description SARS-CoV-2 Lineage assignment.
    """
    
    chat_history = [
        HumanMessage(content="I want to run the Covid Emergency Pipeline but I want to use Snippy instead of iVar for the mapping step. Please keep Pangolin for the lineage. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.used_template_id == "module_covid_emergency", "Logic Failed Wrong template."
    assert "step_2AS_mapping__snippy" in result.selected_module_ids, "Logic Failed Missing Snippy replacement."
    assert "step_4TY_lineage__pangolin" in result.selected_module_ids, "Logic Failed Missing Pangolin."
    assert result.strategy_selector == "ADAPTED_MATCH", "Logic Failed Agent did not select ADAPTED_MATCH strategy."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_adapt_covid():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_covid_emergency Description Fast SARS-CoV-2 analysis pipeline using iVar and Pangolin.
    Component ID step_2AS_mapping__snippy Description Rapid variant calling.
    """
    
    chat_history = [
        HumanMessage(content="I want to run the Covid Emergency Pipeline but I want to use Snippy instead of iVar for the mapping step.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer evaluating an AI system. Read the RAG context and the AI reply. Give strict scores for Faithfulness and Relevance."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[Adapt Covid Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[Adapt Covid Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low."


def test_rag_retrieval_custom_build():
    store = InMemoryStore()
    
    query = "I need a brand new pipeline for some bacterial reads. First trim them with fastp then do a de novo assembly with SPAdes and finally annotate the genes with Prokka."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "step_1PP_trimming__fastp" in context.lower(), "Context Relevance Failed Missing fastp tool."
    assert "step_2AS_denovo__spades" in context.lower(), "Context Relevance Failed Missing SPAdes tool."
    assert "step_4AN_genes__prokka" in context.lower(), "Context Relevance Failed Missing Prokka tool."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_custom_build():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Component ID step_1PP_trimming__fastp Description Quality trimming.
    Component ID step_2AS_denovo__spades Description De novo assembly.
    Component ID step_4AN_genes__prokka Description Gene annotation.
    """
    
    chat_history = [
        HumanMessage(content="I need a custom pipeline. Trim with fastp then assemble with SPAdes and annotate with Prokka. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.strategy_selector == "CUSTOM_BUILD", "Logic Failed Agent did not select CUSTOM_BUILD strategy."
    assert "step_1PP_trimming__fastp" in result.selected_module_ids, "Logic Failed Missing fastp."
    assert "step_2AS_denovo__spades" in result.selected_module_ids, "Logic Failed Missing SPAdes."
    assert "step_4AN_genes__prokka" in result.selected_module_ids, "Logic Failed Missing Prokka."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_custom_build():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Component ID step_1PP_trimming__fastp Description Quality trimming.
    Component ID step_2AS_denovo__spades Description De novo assembly.
    Component ID step_4AN_genes__prokka Description Gene annotation.
    """
    
    chat_history = [
        HumanMessage(content="I need a custom pipeline. Trim with fastp then assemble with SPAdes and annotate with Prokka.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer evaluating an AI system. Read the RAG context and the AI reply. Give strict scores for Faithfulness and Relevance."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[Custom Build Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[Custom Build Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low."

def test_rag_retrieval_outbreak_phylogeny():
    store = InMemoryStore()
    
    query = "We have a Salmonella outbreak across three different farms. I have the assembled fasta files. I need a pipeline to align them and build a phylogenetic tree to see how they are related."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "reportree" in context.lower(), "Context Relevance Failed Missing ReporTree tool."
    assert "multi_clustering" in context.lower(), "Context Relevance Failed Missing multi clustering template."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_outbreak_phylogeny():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Component ID multi_clustering__reportree_alignment Description ReporTree pipeline variant for FASTA sequences. Automatically performs Multiple Sequence Alignment.
    """
    
    chat_history = [
        HumanMessage(content="I have assembled fasta files from a Salmonella outbreak on three farms. I need to build a phylogenetic tree to see the relationships. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.strategy_selector == "CUSTOM_BUILD", "Logic Failed Agent did not select CUSTOM_BUILD."
    assert "multi_clustering__reportree_alignment" in result.selected_module_ids, "Logic Failed Missing ReporTree alignment module."
    assert result.status == "APPROVED", "Logic Failed Agent did not approve."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_outbreak_phylogeny():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Component ID multi_clustering__reportree_alignment Description ReporTree pipeline variant for FASTA sequences. Automatically performs Multiple Sequence Alignment.
    """
    
    chat_history = [
        HumanMessage(content="I have assembled fasta files from a Salmonella outbreak on three farms. I need to build a phylogenetic tree to see the relationships.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer evaluating an AI system. Read the RAG context and the AI reply. Give strict scores for Faithfulness and Relevance."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[Outbreak Tree Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[Outbreak Tree Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low."


def test_rag_retrieval_nanopore_long_reads():
    store = InMemoryStore()
    
    query = "I used a MinION device to get long reads from a new virus. I need to do quality control on the nanopore data and then map it to a reference."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "nanoplot" in context.lower(), "Context Relevance Failed Missing Nanoplot."
    assert "minimap2" in context.lower() or "medaka" in context.lower(), "Context Relevance Failed Missing long read mapping tools."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_nanopore_long_reads():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Component ID module_qc_nanoplot Description Runs Nanoplot software on raw Nanopore reads.
    Component ID step_2AS_mapping__minimap2 Description Reference based consensus calling workflow for Nanopore long reads.
    Component ID step_2AS_mapping__medaka Description Nanopore consensus polishing and variant calling workflow.
    """
    
    chat_history = [
        HumanMessage(content="I have long reads from a MinION device. I need to run quality control and then map the reads to a reference genome. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.strategy_selector == "CUSTOM_BUILD", "Logic Failed Agent did not select CUSTOM_BUILD."
    assert "module_qc_nanoplot" in result.selected_module_ids, "Logic Failed Missing Nanoplot."
    has_mapping = "step_2AS_mapping__minimap2" in result.selected_module_ids or "step_2AS_mapping__medaka" in result.selected_module_ids
    assert has_mapping, "Logic Failed Missing long read mapping."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_nanopore_long_reads():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Component ID module_qc_nanoplot Description Runs Nanoplot software on raw Nanopore reads.
    Component ID step_2AS_mapping__minimap2 Description Reference based consensus calling workflow for Nanopore long reads.
    """
    
    chat_history = [
        HumanMessage(content="I have long reads from a MinION device. I need to run quality control and then map the reads to a reference genome.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer evaluating an AI system. Read the RAG context and the AI reply. Give strict scores for Faithfulness and Relevance."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[Nanopore Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[Nanopore Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low."

from langchain_core.messages import HumanMessage, AIMessage

def test_rag_retrieval_covid_emergency():
    store = InMemoryStore()
    
    query = "We found some SARS-CoV-2 in mink samples. I need the fast emergency pipeline to map against the reference and assign the Pango lineage."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "module_covid_emergency" in context.lower(), "Context Relevance Failed Missing Covid template."
    assert "pangolin" in context.lower(), "Context Relevance Failed Missing Pangolin tool."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_covid_emergency():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_covid_emergency Description Fast SARS-CoV-2 analysis pipeline using iVar and Pangolin.
    Component ID step_2AS_mapping__ivar Description Viral consensus calling workflow.
    Component ID step_4TY_lineage__pangolin Description SARS-CoV-2 Lineage assignment.
    """
    
    chat_history = [
        HumanMessage(content="We found some SARS-CoV-2 in mink samples. I need the fast emergency pipeline to map it and assign the Pango lineage. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.used_template_id == "module_covid_emergency", "Logic Failed Wrong template."
    assert "step_2AS_mapping__ivar" in result.selected_module_ids, "Logic Failed Missing iVar mapping."
    assert "step_4TY_lineage__pangolin" in result.selected_module_ids, "Logic Failed Missing Pangolin."
    assert result.strategy_selector == "EXACT_MATCH", "Logic Failed Agent did not select EXACT_MATCH."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_covid_emergency():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_covid_emergency Description Fast SARS-CoV-2 analysis pipeline using iVar and Pangolin.
    """
    
    chat_history = [
        HumanMessage(content="We found some SARS-CoV-2 in mink samples. I need the fast emergency pipeline to map it and assign the Pango lineage.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer evaluating an AI system. Read the RAG context and the AI reply. Give strict scores for Faithfulness and Relevance."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[Covid Emergency Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[Covid Emergency Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low."


def test_rag_retrieval_host_depletion_denovo():
    store = InMemoryStore()
    
    query = "I have some clinical swab samples from pigs. I need a pipeline that will first deplete the host pig DNA and then do a de novo assembly on what is left."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "module_denovo" in context.lower(), "Context Relevance Failed Missing denovo template."
    assert "step_1pp_hostdepl__bowtie" in context.lower(), "Context Relevance Failed Missing host depletion tool."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_host_depletion_denovo():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_denovo Description De novo assembly pipeline with optional host depletion.
    Component ID step_1PP_hostdepl__bowtie Description Maps reads against a host reference using Bowtie2 to deplete host reads.
    Component ID step_2AS_denovo__spades Description Accurate de novo assembly workflow.
    """
    
    chat_history = [
        HumanMessage(content="I have swab samples from pigs. I want to deplete the host pig DNA and then do a de novo assembly. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.used_template_id == "module_denovo", "Logic Failed Wrong template."
    assert "step_1PP_hostdepl__bowtie" in result.selected_module_ids, "Logic Failed Missing host depletion."
    assert "step_2AS_denovo__spades" in result.selected_module_ids, "Logic Failed Missing assembly tool."
    assert result.strategy_selector == "EXACT_MATCH", "Logic Failed Agent did not select EXACT_MATCH."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_host_depletion_denovo():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_denovo Description De novo assembly pipeline with optional host depletion.
    """
    
    chat_history = [
        HumanMessage(content="I have swab samples from pigs. I want to deplete the host pig DNA and then do a de novo assembly.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer evaluating an AI system. Read the RAG context and the AI reply. Give strict scores for Faithfulness and Relevance."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[Host Depletion Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[Host Depletion Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low."

def test_rag_retrieval_filtered_denovo():
    store = InMemoryStore()
    
    query = "I have a complex clinical sample but I only care about one specific virus. I want to positively select reads by mapping them to its reference genome first. Then I want to take only those matching reads and do a de novo assembly on them."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "module_filtered_denovo" in context.lower(), "Context Relevance Failed Missing filtered denovo template."
    assert "step_1pp_filtering__bowtie" in context.lower(), "Context Relevance Failed Missing Bowtie filtering tool."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_filtered_denovo():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_filtered_denovo Description Positive selection assembly pipeline. Retains only the reads that map to that reference.
    Component ID step_1PP_filtering__bowtie Description Filter reads Keep only those matching the reference.
    Component ID step_2AS_denovo__spades Description Assemble the filtered reads.
    """
    
    chat_history = [
        HumanMessage(content="I want to find a specific virus in a complex sample. Filter the reads against the reference first and then assemble only the matching reads. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.used_template_id == "module_filtered_denovo", "Logic Failed Wrong template."
    assert "step_1PP_filtering__bowtie" in result.selected_module_ids, "Logic Failed Missing filtering tool."
    assert "step_2AS_denovo__spades" in result.selected_module_ids, "Logic Failed Missing assembly tool."
    assert result.strategy_selector == "EXACT_MATCH", "Logic Failed Agent did not select EXACT_MATCH."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_filtered_denovo():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_filtered_denovo Description Positive selection assembly pipeline. Retains only the reads that map to that reference.
    """
    
    chat_history = [
        HumanMessage(content="I want to find a specific virus in a complex sample. Filter the reads against the reference first and then assemble only the matching reads.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer evaluating an AI system. Read the RAG context and the AI reply. Give strict scores for Faithfulness and Relevance."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[Filtered Denovo Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[Filtered Denovo Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low."


def test_rag_retrieval_segmented_virus():
    store = InMemoryStore()
    
    query = "We are tracking an outbreak of avian influenza. It is a segmented virus. I need a pipeline that maps the short reads against multiple reference segments and gives me the consensus."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "module_segmented" in context.lower(), "Context Relevance Failed Missing segmented template."
    assert "step_2as_mapping__ivar" in context.lower(), "Context Relevance Failed Missing iVar tool."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_segmented_virus():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_segmented Description Performs mapping of genome fragments from segmented viruses like Influenza.
    Component ID step_2AS_mapping__ivar Description Maps reads against multiple reference segments and aggregates the consensus sequences.
    """
    
    chat_history = [
        HumanMessage(content="I am working with avian influenza. I need a pipeline for segmented viruses to map against multiple references. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.used_template_id == "module_segmented", "Logic Failed Wrong template."
    assert "step_2AS_mapping__ivar" in result.selected_module_ids, "Logic Failed Missing iVar mapping tool."
    assert result.strategy_selector == "EXACT_MATCH", "Logic Failed Agent did not select EXACT_MATCH."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_segmented_virus():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_segmented Description Performs mapping of genome fragments from segmented viruses like Influenza.
    """
    
    chat_history = [
        HumanMessage(content="I am working with avian influenza. I need a pipeline for segmented viruses to map against multiple references.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer evaluating an AI system. Read the RAG context and the AI reply. Give strict scores for Faithfulness and Relevance."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[Segmented Virus Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[Segmented Virus Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low."

def test_rag_retrieval_typing_bacteria():
    store = InMemoryStore()
    
    query = "I have a new bacterial isolate from a sick calf. I need a comprehensive pipeline to figure out exactly what species it is map it to the best reference genome automatically find any antibiotic resistance genes and run MLST."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "module_typing_bacteria" in context.lower(), "Context Relevance Failed Missing typing bacteria template."
    assert "kmerfinder" in context.lower(), "Context Relevance Failed Missing KmerFinder tool."
    assert "mlst" in context.lower(), "Context Relevance Failed Missing MLST tool."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_typing_bacteria():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_typing_bacteria Description Comprehensive bacterial characterization pipeline. Identifies species using KmerFinder maps to best reference and runs AMR and MLST.
    Component ID step_3TX_species__kmerfinder Description Determine species and best reference genome.
    Component ID step_4TY_MLST__mlst Description Classical MLST.
    """
    
    chat_history = [
        HumanMessage(content="I have a new bacterial isolate. I need a comprehensive pipeline to find the species map it to the best reference find resistance genes and run MLST. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.used_template_id == "module_typing_bacteria", "Logic Failed Wrong template."
    assert "step_3TX_species__kmerfinder" in result.selected_module_ids, "Logic Failed Missing KmerFinder."
    assert "step_4TY_MLST__mlst" in result.selected_module_ids, "Logic Failed Missing MLST."
    assert result.strategy_selector == "EXACT_MATCH", "Logic Failed Agent did not select EXACT_MATCH."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_typing_bacteria():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_typing_bacteria Description Comprehensive bacterial characterization pipeline.
    """
    
    chat_history = [
        HumanMessage(content="I have a new bacterial isolate. I need a comprehensive pipeline to find the species map it to the best reference find resistance genes and run MLST.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer evaluating an AI system. Read the RAG context and the AI reply. Give strict scores for Faithfulness and Relevance."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[Typing Bacteria Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[Typing Bacteria Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low."


def test_rag_retrieval_qc_quast():
    store = InMemoryStore()
    
    query = "I already assembled my contigs for a dozen samples. I just need a pipeline to run Quast on all the fasta files and give me a summary report of the assembly metrics."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "module_qc_quast" in context.lower(), "Context Relevance Failed Missing Quast QC template."
    assert "quast" in context.lower(), "Context Relevance Failed Missing Quast tool."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_qc_quast():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_qc_quast Description Runs Quast on genomic assemblies and aggregates results.
    Component ID module_qc_quast Description Evaluates genome assembly quality. Runs QUAST on input assemblies.
    """
    
    chat_history = [
        HumanMessage(content="I have assembled contigs. I want to run Quast to check the assembly metrics and get a summary. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.used_template_id == "module_qc_quast", "Logic Failed Wrong template."
    assert "module_qc_quast" in result.selected_module_ids or "quast" in result.selected_module_ids, "Logic Failed Missing Quast step."
    assert result.strategy_selector == "EXACT_MATCH", "Logic Failed Agent did not select EXACT_MATCH."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_qc_quast():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_qc_quast Description Runs Quast on genomic assemblies and aggregates results.
    """
    
    chat_history = [
        HumanMessage(content="I have assembled contigs. I want to run Quast to check the assembly metrics and get a summary.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer evaluating an AI system. Read the RAG context and the AI reply. Give strict scores for Faithfulness and Relevance."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[QC Quast Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[QC Quast Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low."

def test_rag_retrieval_qc_fastqc():
    store = InMemoryStore()
    
    query = "I have some raw Illumina paired reads. I do not want to assemble them yet. I just want to run a basic quality control check to see if the sequencing was good."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "module_qc_fastqc" in context.lower(), "Context Relevance Failed Missing FastQC template."
    assert "fastqc" in context.lower(), "Context Relevance Failed Missing FastQC tool."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_qc_fastqc():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_qc_fastqc Description Runs FastQC on raw or trimmed reads for Illumina or Ion Torrent.
    Component ID module_qc_fastqc Description Performs quality control checks on raw sequence data using FastQC.
    """
    
    chat_history = [
        HumanMessage(content="I have some raw Illumina paired reads. I just want to run a basic quality control check. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.used_template_id == "module_qc_fastqc", "Logic Failed Wrong template."
    assert "module_qc_fastqc" in result.selected_module_ids, "Logic Failed Missing FastQC step."
    assert result.strategy_selector == "EXACT_MATCH", "Logic Failed Agent did not select EXACT_MATCH."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_qc_fastqc():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_qc_fastqc Description Runs FastQC on raw or trimmed reads.
    """
    
    chat_history = [
        HumanMessage(content="I have some raw Illumina paired reads. I just want to run a basic quality control check.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer evaluating an AI system. Read the RAG context and the AI reply. Give strict scores for Faithfulness and Relevance."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[QC FastQC Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[QC FastQC Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low."


def test_rag_retrieval_wgs_bacteria():
    store = InMemoryStore()
    
    query = "I need a whole genome sequencing pipeline for a bacteria sample. It should do trimming then de novo assembly and finally annotate the genes."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "module_wgs_bacteria" in context.lower(), "Context Relevance Failed Missing WGS bacteria template."
    assert "spades" in context.lower() or "unicycler" in context.lower(), "Context Relevance Failed Missing assembly tool."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_wgs_bacteria():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_wgs_bacteria Description Whole genome sequencing pipeline for bacteria.
    Component ID step_1PP_trimming__fastp Description Quality trimming.
    Component ID step_2AS_denovo__spades Description Accurate de novo assembly workflow.
    Component ID step_4AN_genes__prokka Description Functional genome annotation.
    """
    
    chat_history = [
        HumanMessage(content="I need a whole genome sequencing pipeline for a bacteria sample to trim assemble and annotate. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.used_template_id == "module_wgs_bacteria", "Logic Failed Wrong template."
    assert "step_2AS_denovo__spades" in result.selected_module_ids, "Logic Failed Missing assembly tool."
    assert result.strategy_selector == "EXACT_MATCH", "Logic Failed Agent did not select EXACT_MATCH."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_wgs_bacteria():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_wgs_bacteria Description Whole genome sequencing pipeline for bacteria.
    """
    
    chat_history = [
        HumanMessage(content="I need a whole genome sequencing pipeline for a bacteria sample to trim assemble and annotate.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer evaluating an AI system. Read the RAG context and the AI reply. Give strict scores for Faithfulness and Relevance."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[WGS Bacteria Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[WGS Bacteria Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low."

def test_rag_retrieval_scaffolds_filtering():
    store = InMemoryStore()
    
    query = "I have some de novo assembly contigs that are very messy. I want to filter the assembled scaffolds using my variant calls and a reference alignment to clean them up."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "step_2as_filtering__seqio" in context.lower(), "Context Relevance Failed. Missing SeqIO filtering tool."
    assert "cleandenovo" in context.lower(), "Context Relevance Failed. Missing cleanDenovo script reference."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_scaffolds_filtering():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Component ID step_2AS_filtering__seqio Description Post-assembly filtering utility using a custom Python script (cleanDenovo.py). It filters de novo assembly contigs based on variant calls and reference alignment.
    """
    
    chat_history = [
        HumanMessage(content="My assembly scaffolds are messy. I want to filter the contigs using the SeqIO tool based on my reference alignment. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.strategy_selector == "CUSTOM_BUILD", "Logic Failed. Agent did not select CUSTOM_BUILD."
    assert "step_2AS_filtering__seqio" in result.selected_module_ids, "Logic Failed. Missing SeqIO filtering tool."
    assert result.status == "APPROVED", "Logic Failed. Agent did not approve."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_scaffolds_filtering():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Component ID step_2AS_filtering__seqio Description Post-assembly filtering utility using a custom Python script (cleanDenovo.py). It filters de novo assembly contigs.
    """
    
    chat_history = [
        HumanMessage(content="My assembly scaffolds are messy. I want to filter the contigs using the SeqIO tool based on my reference alignment.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer evaluating an AI system. Read the RAG context and the AI reply. Give strict scores for Faithfulness and Relevance."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[Scaffolds Filtering Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[Scaffolds Filtering Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low."


def test_rag_retrieval_vdraft_light():
    store = InMemoryStore()
    
    query = "I want to run the viral genome draft pipeline but I need it to be fast. Just map with Bowtie2 and get the consensus with iVar. Skip the Prokka annotation completely."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "module_draft_genome" in context.lower(), "Context Relevance Failed. Missing genome draft template."
    assert "step_2as_mapping__bowtie" in context.lower(), "Context Relevance Failed. Missing Bowtie2."
    assert "step_2as_mapping__ivar" in context.lower(), "Context Relevance Failed. Missing iVar."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_vdraft_light():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_draft_genome Description Viral genome reconstruction and annotation pipeline. Performs Bowtie2 mapping, iVar consensus, and Prokka annotation.
    Component ID step_2AS_mapping__bowtie Description Generate BAM and coverage plots.
    Component ID step_2AS_mapping__ivar Description Generate consensus sequence.
    Component ID step_4AN_genes__prokka Description Annotate consensus.
    """
    
    chat_history = [
        HumanMessage(content="I want to run the viral genome draft pipeline but I need a light version. Just map with Bowtie2 and get the consensus with iVar. Skip the Prokka annotation completely to save time. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.used_template_id == "module_draft_genome", "Logic Failed. Wrong base template."
    assert "step_2AS_mapping__bowtie" in result.selected_module_ids, "Logic Failed. Missing Bowtie2."
    assert "step_2AS_mapping__ivar" in result.selected_module_ids, "Logic Failed. Missing iVar."
    assert "step_4AN_genes__prokka" not in result.selected_module_ids, "Logic Failed. Agent included Prokka when asked to skip it."
    assert result.strategy_selector == "ADAPTED_MATCH", "Logic Failed. Agent did not select ADAPTED_MATCH strategy."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_vdraft_light():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_draft_genome Description Viral genome reconstruction and annotation pipeline. Performs Bowtie2 mapping, iVar consensus, and Prokka annotation.
    """
    
    chat_history = [
        HumanMessage(content="I want to run the viral genome draft pipeline but I need a light version. Just map with Bowtie2 and get the consensus with iVar. Skip the Prokka annotation completely to save time.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer evaluating an AI system. Read the RAG context and the AI reply. Give strict scores for Faithfulness and Relevance."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[vDraft Light Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[vDraft Light Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low."

def test_rag_retrieval_hybrid_assembly():
    store = InMemoryStore()
    
    query = "I have both Illumina short reads and Nanopore long reads from a difficult bacterial sample. I want to trim the long reads with Chopper and then do a hybrid assembly with Unicycler."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "chopper" in context.lower(), "Context Relevance Failed. Missing Chopper tool."
    assert "step_2as_hybrid__unicycler" in context.lower(), "Context Relevance Failed. Missing hybrid Unicycler tool."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_hybrid_assembly():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Component ID step_1PP_trimming__chopper Description Long-read preprocessing workflow. Performs Filtering/Trimming with Chopper.
    Component ID step_2AS_hybrid__unicycler Description Hybrid assembly workflow combining Short Reads for accuracy and Long Reads for continuity.
    """
    
    chat_history = [
        HumanMessage(content="I have both Illumina short reads and Nanopore long reads. I need a custom pipeline to trim the long reads with Chopper and then do a hybrid assembly with Unicycler. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.strategy_selector == "CUSTOM_BUILD", "Logic Failed. Agent did not select CUSTOM_BUILD."
    assert "step_1PP_trimming__chopper" in result.selected_module_ids, "Logic Failed. Missing Chopper."
    assert "step_2AS_hybrid__unicycler" in result.selected_module_ids, "Logic Failed. Missing hybrid assembly."
    assert result.status == "APPROVED", "Logic Failed. Agent did not approve."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_hybrid_assembly():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Component ID step_1PP_trimming__chopper Description Long-read preprocessing workflow.
    Component ID step_2AS_hybrid__unicycler Description Hybrid assembly workflow.
    """
    
    chat_history = [
        HumanMessage(content="I have both Illumina short reads and Nanopore long reads. I need a custom pipeline to trim the long reads with Chopper and then do a hybrid assembly with Unicycler.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer evaluating an AI system. Read the RAG context and the AI reply. Give strict scores for Faithfulness and Relevance."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[Hybrid Assembly Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[Hybrid Assembly Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low."


def test_rag_retrieval_multi_snippy():
    store = InMemoryStore()
    
    query = "I have trimmed reads from 50 different outbreak samples. I want to run a core SNP alignment on all of them together using Snippy-core to see the variants."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "multi_alignment__snippycore" in context.lower(), "Context Relevance Failed. Missing Snippy-core multi-sample tool."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_multi_snippy():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Component ID multi_alignment__snippycore Description Multi-sample core SNP alignment workflow. Takes raw/trimmed reads, runs Snippy on each against a reference, then aggregates with Snippy-core.
    """
    
    chat_history = [
        HumanMessage(content="I have trimmed reads from 50 different outbreak samples. I want to run a core SNP alignment on all of them together using Snippy-core. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.strategy_selector == "CUSTOM_BUILD", "Logic Failed. Agent did not select CUSTOM_BUILD."
    assert "multi_alignment__snippycore" in result.selected_module_ids, "Logic Failed. Missing Snippy-core tool."
    assert result.status == "APPROVED", "Logic Failed. Agent did not approve."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_multi_snippy():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Component ID multi_alignment__snippycore Description Multi-sample core SNP alignment workflow.
    """
    
    chat_history = [
        HumanMessage(content="I have trimmed reads from 50 different outbreak samples. I want to run a core SNP alignment on all of them together using Snippy-core.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer evaluating an AI system. Read the RAG context and the AI reply. Give strict scores for Faithfulness and Relevance."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[Multi Snippy Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[Multi Snippy Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low."

def test_rag_retrieval_conditional_trimming():
    store = InMemoryStore()
    
    query = "I have raw reads from an Ion Torrent sequencer. I need a pipeline to do quality control, trim them, and classify with Kraken."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "module_reads_processing" in context.lower(), "Context Relevance Failed. Missing reads processing template."
    assert "fastp" in context.lower(), "Context Relevance Failed. Missing fastp tool."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_conditional_trimming():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_reads_processing Description Comprehensive reads preprocessing. Condition: Ion Torrent routes to fastp. Illumina (Non-Bacteria) routes to Trimmomatic.
    Component ID step_1PP_trimming__fastp Description Quality trimming optimized for Bacteria/Ion.
    Component ID step_1PP_trimming__trimmomatic Description Legacy trimming for Illumina.
    Component ID step_3TX_class__kraken Description Taxonomic classification.
    """
    
    chat_history = [
        HumanMessage(content="I have raw reads from an Ion Torrent sequencer. I want to process the reads and classify them with Kraken. Please use the standard processing module. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.used_template_id == "module_reads_processing", "Logic Failed. Wrong template."
    assert "step_1PP_trimming__fastp" in result.selected_module_ids, "Logic Failed. Agent missed the conditional logic and did not select fastp for Ion Torrent."
    assert "step_1PP_trimming__trimmomatic" not in result.selected_module_ids, "Logic Failed. Agent incorrectly selected Trimmomatic for Ion Torrent data."
    assert result.status == "APPROVED", "Logic Failed. Agent did not approve."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_conditional_trimming():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_reads_processing Description Comprehensive reads preprocessing. Condition: Ion Torrent routes to fastp. Illumina routes to Trimmomatic.
    """
    
    chat_history = [
        HumanMessage(content="I have raw reads from an Ion Torrent sequencer. I want to process the reads and classify them with Kraken using the standard processing module.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer evaluating an AI system. Read the RAG context and the AI reply. Give strict scores for Faithfulness and Relevance. Ensure the AI correctly notes the conditional routing for Ion Torrent."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[Conditional Trimming Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[Conditional Trimming Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low."


# --- Test Case 12: Edge Case (Incompatible Tool Request) ---
def test_rag_retrieval_edge_case_incompatible():
    store = InMemoryStore()
    
    query = "I want to do variant calling on my Nanopore long reads using Snippy."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "snippy" in context.lower(), "Context Relevance Failed. Missing Snippy tool."
    # RAG should ideally pull in Medaka or Minimap2 due to "Nanopore long reads" keywords
    assert "nanopore" in context.lower(), "Context Relevance Failed. Missing long read context."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_edge_case_incompatible():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Component ID step_2AS_mapping__snippy Description Rapid variant calling. compatible_seq_types: ["illumina_paired", "ion"]. NOT for Nanopore.
    Component ID step_2AS_mapping__medaka Description Nanopore consensus polishing and variant calling workflow. compatible_seq_types: ["nanopore"].
    """
    
    chat_history = [
        HumanMessage(content="I want to do variant calling on my Nanopore long reads using Snippy. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    # The agent should NOT blindly approve an incompatible pipeline. It should set status back to CHATTING to correct the user.
    assert result.status == "CHATTING", "Logic Failed. Agent blindly approved an incompatible tool instead of correcting the user."
    assert "step_2AS_mapping__snippy" not in result.selected_module_ids, "Logic Failed. Agent included Snippy for Nanopore data."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_edge_case_incompatible():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}\n\nCRITICAL INSTRUCTION: If a requested tool is incompatible with the data type, kindly inform the user and suggest the correct tool from the context."),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Component ID step_2AS_mapping__snippy Description Rapid variant calling. compatible_seq_types: ["illumina_paired", "ion"].
    Component ID step_2AS_mapping__medaka Description Nanopore consensus polishing and variant calling workflow. compatible_seq_types: ["nanopore"].
    """
    
    chat_history = [
        HumanMessage(content="I want to do variant calling on my Nanopore long reads using Snippy.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer evaluating an AI system's safety and edge-case handling. The AI MUST politely correct the user because Snippy is not compatible with Nanopore, and it should suggest Medaka instead. Score strictly."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[Edge Case Incompatible Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[Edge Case Incompatible Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low. The agent likely failed to correct the user's tool choice."

def test_rag_retrieval_staramr_constraint():
    store = InMemoryStore()
    
    query = "I have an assembled E. coli genome. I want to scan it for AMR genes using StarAMR."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "staramr" in context.lower(), "Context Relevance Failed. Missing StarAMR tool."
    assert "campylobacter" in context.lower(), "Context Relevance Failed. Missing species constraint context for StarAMR."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_staramr_constraint():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Component ID step_4AN_AMR__staramr Description Scans for AMR genes and point mutations using StarAMR. Constraint: Currently restricted to 'Campylobacter' species via the isSpeciesSupported check.
    Component ID step_4AN_AMR__resfinder Description Predicts antibiotic resistance genes. Requires genus_species.
    """
    
    chat_history = [
        HumanMessage(content="I have an assembled E. coli genome. I want to scan it for AMR genes using StarAMR. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    # The agent must NOT approve StarAMR for E. coli. It should revert to CHATTING to suggest ResFinder or Abricate.
    assert result.status == "CHATTING", "Logic Failed. Agent approved StarAMR for an incompatible species."
    assert "step_4AN_AMR__staramr" not in result.selected_module_ids, "Logic Failed. Agent included StarAMR despite the Campylobacter constraint."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_staramr_constraint():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}\n\nCRITICAL INSTRUCTION: Enforce all species constraints noted in the tool descriptions."),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Component ID step_4AN_AMR__staramr Description Scans for AMR genes. Constraint: Currently restricted to 'Campylobacter'.
    Component ID step_4AN_AMR__resfinder Description Predicts antibiotic resistance genes.
    """
    
    chat_history = [
        HumanMessage(content="I have an assembled E. coli genome. I want to scan it for AMR genes using StarAMR.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer. Evaluate if the AI successfully caught the user's error. The AI MUST explain that StarAMR is restricted to Campylobacter and suggest an alternative like ResFinder for E. coli. Score strictly."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[StarAMR Validation Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[StarAMR Validation Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low. The agent failed to enforce the strict input validation."


# --- Test Case 14: Module Composition (Custom Preprocessing) ---
def test_rag_retrieval_module_composition_preprocessing():
    store = InMemoryStore()
    
    query = "I want to compose a custom reusable preprocessing module. It should take raw reads, run FastQC, trim them using Trimmomatic, and then deplete human host DNA using Bowtie2."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "step_0sq_rawreads__fastq" in context.lower() or "module_qc_fastqc" in context.lower(), "Context Relevance Failed. Missing FastQC component."
    assert "step_1pp_trimming__trimmomatic" in context.lower(), "Context Relevance Failed. Missing Trimmomatic component."
    assert "step_1pp_hostdepl__bowtie" in context.lower(), "Context Relevance Failed. Missing Bowtie2 host depletion component."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_module_composition_preprocessing():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Component ID step_0SQ_rawreads__fastq Description Unified QC step for raw reads using FastQC.
    Component ID step_1PP_trimming__trimmomatic Description Legacy trimming workflow optimized for Illumina.
    Component ID step_1PP_hostdepl__bowtie Description Host depletion workflow using Bowtie2.
    """
    
    chat_history = [
        HumanMessage(content="I want to compose a custom preprocessing module. Take raw reads, run FastQC, trim them using Trimmomatic, and then deplete host DNA using Bowtie2. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.strategy_selector == "CUSTOM_BUILD", "Logic Failed. Agent did not select CUSTOM_BUILD."
    assert "step_0SQ_rawreads__fastq" in result.selected_module_ids, "Logic Failed. Missing FastQC."
    assert "step_1PP_trimming__trimmomatic" in result.selected_module_ids, "Logic Failed. Missing Trimmomatic."
    assert "step_1PP_hostdepl__bowtie" in result.selected_module_ids, "Logic Failed. Missing Bowtie2 Host Depletion."
    assert result.status == "APPROVED", "Logic Failed. Agent did not approve."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_module_composition():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Component ID step_0SQ_rawreads__fastq Description Unified QC step for raw reads using FastQC.
    Component ID step_1PP_trimming__trimmomatic Description Legacy trimming workflow optimized for Illumina.
    Component ID step_1PP_hostdepl__bowtie Description Host depletion workflow using Bowtie2.
    """
    
    chat_history = [
        HumanMessage(content="I want to compose a custom preprocessing module. Take raw reads, run FastQC, trim them using Trimmomatic, and then deplete host DNA using Bowtie2.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer evaluating an AI system. Read the RAG context and the AI reply. Give strict scores for Faithfulness and Relevance."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[Module Composition Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[Module Composition Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low."

def test_rag_retrieval_empty_file_handling():
    store = InMemoryStore()
    
    query = "I have a large batch of raw reads, but I know some of the fastq files might be completely empty or have very few reads. Which preprocessing pipeline safely checks for this without crashing?"
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "module_reads_processing" in context.lower(), "Context Relevance Failed. Missing reads processing template."
    assert "empty files" in context.lower(), "Context Relevance Failed. Missing empty file handling context."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_empty_file_handling():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_reads_processing Description Comprehensive reads preprocessing module. Includes checks for empty files and insufficient read counts.
    """
    
    chat_history = [
        HumanMessage(content="I have a batch of raw reads but some fastq files might be empty. I need a pipeline that handles this safely. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.used_template_id == "module_reads_processing", "Logic Failed. Agent did not select the template that handles empty files."
    assert result.status == "APPROVED", "Logic Failed. Agent did not approve."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_empty_file_handling():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_reads_processing Description Comprehensive reads preprocessing module. Includes checks for empty files and insufficient read counts.
    """
    
    chat_history = [
        HumanMessage(content="I have a batch of raw reads but some fastq files might be empty. Which pipeline handles this safely?")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer. Evaluate if the AI successfully identified the module that handles empty files based ONLY on the context. Score strictly."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[Empty File Handling Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[Empty File Handling Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low. The agent failed to address the empty file requirement."


def test_rag_retrieval_resource_starvation():
    store = InMemoryStore()
    
    query = "My server has very limited memory, and I have massive paired-end Illumina datasets. I need a tool to downsample the reads that safely handles Java heap memory calculation to prevent out-of-memory errors."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "step_1pp_downsampling__bbnorm" in context.lower(), "Context Relevance Failed. Missing BBNorm downsampling tool."
    assert "java heap" in context.lower() or "85%" in context.lower(), "Context Relevance Failed. Missing memory calculation context."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_resource_starvation():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Component ID step_1PP_downsampling__bbnorm Description Normalizes read depth to reduce computational load. Specifically configured for paired-end Illumina data. Notes: Script explicitly handles Java heap memory calculation (-Xmx) based on 85% of available container memory.
    """
    
    chat_history = [
        HumanMessage(content="I have limited memory and huge Illumina datasets. I need to downsample them without crashing Java. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.strategy_selector == "CUSTOM_BUILD", "Logic Failed. Agent did not select CUSTOM_BUILD."
    assert "step_1PP_downsampling__bbnorm" in result.selected_module_ids, "Logic Failed. Agent missed the BBNorm tool."
    assert result.status == "APPROVED", "Logic Failed. Agent did not approve."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_resource_starvation():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Component ID step_1PP_downsampling__bbnorm Description Normalizes read depth to reduce computational load. Notes: Script explicitly handles Java heap memory calculation (-Xmx) based on 85% of available container memory.
    """
    
    chat_history = [
        HumanMessage(content="I have limited memory and huge Illumina datasets. I need to downsample them without crashing Java. What tool handles this?")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer. Evaluate if the AI successfully recommended BBNorm and faithfully explained the 85% Java heap memory calculation constraint. Score strictly."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[Resource Starvation Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[Resource Starvation Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low. The agent failed to address the memory starvation request."

def test_rag_retrieval_reportree_vcf():
    store = InMemoryStore()
    
    query = "I have VCF files from multiple samples and their metadata. I want to build a minimum spanning tree using ReporTree."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "reportree" in context.lower(), "Context Relevance Failed. Missing ReporTree tool."
    assert "vcf" in context.lower(), "Context Relevance Failed. Missing VCF context."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_reportree_vcf():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Component ID multi_clustering__reportree_vcf Description ReporTree pipeline variant designed specifically for VCF inputs. Constructs a GrapeTree Minimum Spanning Tree.
    Component ID multi_clustering__reportree_alignment Description ReporTree pipeline variant for FASTA sequences.
    """
    
    chat_history = [
        HumanMessage(content="I have VCF files from multiple samples. I want to build a minimum spanning tree using ReporTree. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.strategy_selector == "CUSTOM_BUILD", "Logic Failed. Agent did not select CUSTOM_BUILD."
    assert "multi_clustering__reportree_vcf" in result.selected_module_ids, "Logic Failed. Missing ReporTree VCF module."
    assert "multi_clustering__reportree_alignment" not in result.selected_module_ids, "Logic Failed. Selected wrong ReporTree variant."
    assert result.status == "APPROVED", "Logic Failed. Agent did not approve."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_reportree_vcf():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Component ID multi_clustering__reportree_vcf Description ReporTree pipeline variant designed specifically for VCF inputs. Constructs a GrapeTree Minimum Spanning Tree.
    Component ID multi_clustering__reportree_alignment Description ReporTree pipeline variant for FASTA sequences.
    """
    
    chat_history = [
        HumanMessage(content="I have VCF files from multiple samples. I want to build a minimum spanning tree using ReporTree.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer. Evaluate if the AI successfully identified the correct ReporTree variant (VCF) and omitted the FASTA/alignment variant. Score strictly."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[ReporTree VCF Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[ReporTree VCF Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low. The agent failed to recommend the specific VCF variant."


# --- Test Case 18: Viral Analysis Module (Adapted for Nanopore) ---
def test_rag_retrieval_viral_nanopore_adaptation():
    store = InMemoryStore()
    
    query = "I want to run the Genome Draft Pipeline for a virus, but I have Nanopore long reads instead of Illumina. I need to map the reads, get the consensus, and run Prokka."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "module_draft_genome" in context.lower(), "Context Relevance Failed. Missing Genome Draft template."
    assert "medaka" in context.lower() or "minimap2" in context.lower(), "Context Relevance Failed. Missing Nanopore mapping tool (Medaka/Minimap2)."
    assert "prokka" in context.lower(), "Context Relevance Failed. Missing Prokka annotation tool."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_viral_nanopore_adaptation():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_draft_genome Description Viral genome reconstruction and annotation pipeline using Bowtie2, iVar, and Prokka. compatible_seq_types: ["illumina_paired", "ion"].
    Component ID step_2AS_mapping__medaka Description Nanopore consensus polishing and variant calling workflow. compatible_seq_types: ["nanopore"].
    Component ID step_4AN_genes__prokka Description Functional genome annotation pipeline.
    """
    
    chat_history = [
        HumanMessage(content="I want to run the Genome Draft Pipeline for a virus, but I have Nanopore long reads. Please adapt the template to map and polish with Medaka, then annotate with Prokka. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.used_template_id == "module_draft_genome", "Logic Failed. Wrong base template."
    assert "step_2AS_mapping__medaka" in result.selected_module_ids, "Logic Failed. Missing Medaka for Nanopore adaptation."
    assert "step_4AN_genes__prokka" in result.selected_module_ids, "Logic Failed. Missing Prokka."
    assert "step_2AS_mapping__bowtie" not in result.selected_module_ids, "Logic Failed. Kept incompatible short-read tool."
    assert result.strategy_selector == "ADAPTED_MATCH", "Logic Failed. Agent did not select ADAPTED_MATCH strategy."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_viral_nanopore_adaptation():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_draft_genome Description Viral genome reconstruction and annotation pipeline using Bowtie2, iVar, and Prokka. compatible_seq_types: ["illumina_paired", "ion"].
    Component ID step_2AS_mapping__medaka Description Nanopore consensus polishing and variant calling workflow. compatible_seq_types: ["nanopore"].
    Component ID step_4AN_genes__prokka Description Functional genome annotation pipeline.
    """
    
    chat_history = [
        HumanMessage(content="I want to run the Genome Draft Pipeline for a virus, but I have Nanopore long reads. Please adapt the template so it works with my data.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer. Evaluate if the AI successfully adapted the short-read viral draft pipeline for Nanopore data by substituting Bowtie2/iVar with Medaka. Score strictly."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[Viral Nanopore Adaptation Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[Viral Nanopore Adaptation Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low. The agent failed to explain the Medaka adaptation properly."

def test_rag_retrieval_adapt_denovo_shovill():
    store = InMemoryStore()
    
    query = "I want to run the denovo pipeline with host depletion. But please use Shovill instead of SPAdes for the assembly step because I need it to be fast."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "module_denovo" in context.lower(), "Context Relevance Failed Missing denovo template."
    assert "step_2as_denovo__shovill" in context.lower(), "Context Relevance Failed Missing Shovill tool."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_adapt_denovo_shovill():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_denovo Description De novo assembly pipeline with optional host depletion.
    Component ID step_1PP_hostdepl__bowtie Description Maps reads against a host reference using Bowtie2.
    Component ID step_2AS_denovo__spades Description Accurate de novo assembly workflow.
    Component ID step_2AS_denovo__shovill Description Fast assembly pipeline wrapping SPAdes.
    """
    
    chat_history = [
        HumanMessage(content="I want to run the denovo pipeline with host depletion. But please use Shovill instead of SPAdes for the assembly step. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.used_template_id == "module_denovo", "Logic Failed Wrong template."
    assert "step_2AS_denovo__shovill" in result.selected_module_ids, "Logic Failed Missing Shovill."
    assert "step_2AS_denovo__spades" not in result.selected_module_ids, "Logic Failed Kept SPAdes by mistake."
    assert result.strategy_selector == "ADAPTED_MATCH", "Logic Failed Agent did not select ADAPTED_MATCH."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_adapt_denovo_shovill():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_denovo Description De novo assembly pipeline with optional host depletion.
    Component ID step_2AS_denovo__spades Description Accurate de novo assembly workflow.
    Component ID step_2AS_denovo__shovill Description Fast assembly pipeline wrapping SPAdes.
    """
    
    chat_history = [
        HumanMessage(content="I want to run the denovo pipeline with host depletion. But please use Shovill instead of SPAdes for the assembly step.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer evaluating an AI system. Read the RAG context and the AI reply. Give strict scores for Faithfulness and Relevance. The AI must explain the swap clearly."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[Adapt Denovo Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[Adapt Denovo Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low."


def test_rag_retrieval_adapt_reads_kraken2():
    store = InMemoryStore()
    
    query = "I want to use the raw reads processing pipeline on my Illumina data. Can we swap the old Kraken tool for Kraken2 instead."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "module_reads_processing" in context.lower(), "Context Relevance Failed Missing reads processing template."
    assert "step_3tx_class__kraken2" in context.lower(), "Context Relevance Failed Missing Kraken2 tool."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_adapt_reads_kraken2():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_reads_processing Description Comprehensive reads preprocessing module.
    Component ID step_0SQ_rawreads__fastq Description Unified QC step.
    Component ID step_1PP_trimming__trimmomatic Description Legacy trimming.
    Component ID step_3TX_class__kraken Description Legacy taxonomic classification workflow.
    Component ID step_3TX_class__kraken2 Description Standard taxonomic classification workflow using Kraken2.
    """
    
    chat_history = [
        HumanMessage(content="I want to use the raw reads processing pipeline. But please swap the old Kraken tool for Kraken2. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.used_template_id == "module_reads_processing", "Logic Failed Wrong template."
    assert "step_3TX_class__kraken2" in result.selected_module_ids, "Logic Failed Missing Kraken2."
    assert "step_3TX_class__kraken" not in result.selected_module_ids, "Logic Failed Kept old Kraken by mistake."
    assert result.strategy_selector == "ADAPTED_MATCH", "Logic Failed Agent did not select ADAPTED_MATCH."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_adapt_reads_kraken2():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_reads_processing Description Comprehensive reads preprocessing module.
    Component ID step_3TX_class__kraken Description Legacy taxonomic classification workflow.
    Component ID step_3TX_class__kraken2 Description Standard taxonomic classification workflow using Kraken2.
    """
    
    chat_history = [
        HumanMessage(content="I want to use the raw reads processing pipeline. But please swap the old Kraken tool for Kraken2.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer evaluating an AI system. Read the RAG context and the AI reply. Give strict scores for Faithfulness and Relevance. The AI must explain the swap clearly."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[Adapt Reads Processing Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[Adapt Reads Processing Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low."

def test_rag_retrieval_adapt_reads_mash():
    store = InMemoryStore()
    
    query = "I want to run the raw reads processing pipeline. But please swap Kraken for Mash screen to estimate the species."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "module_reads_processing" in context.lower(), "Context Relevance Failed Missing reads processing template."
    assert "step_3tx_species__mash" in context.lower(), "Context Relevance Failed Missing Mash tool."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_adapt_reads_mash():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_reads_processing Description Comprehensive reads preprocessing module.
    Component ID step_0SQ_rawreads__fastq Description Unified QC step.
    Component ID step_1PP_trimming__fastp Description Quality trimming.
    Component ID step_3TX_class__kraken Description Legacy taxonomic classification workflow.
    Component ID step_3TX_species__mash Description Fast genome distance estimation using MinHash.
    """
    
    chat_history = [
        HumanMessage(content="I want to use the raw reads processing pipeline. But please swap the Kraken tool for Mash screen. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.used_template_id == "module_reads_processing", "Logic Failed Wrong template."
    assert "step_3TX_species__mash" in result.selected_module_ids, "Logic Failed Missing Mash."
    assert "step_3TX_class__kraken" not in result.selected_module_ids, "Logic Failed Kept old Kraken by mistake."
    assert result.strategy_selector == "ADAPTED_MATCH", "Logic Failed Agent did not select ADAPTED_MATCH."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_adapt_reads_mash():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_reads_processing Description Comprehensive reads preprocessing module.
    Component ID step_3TX_class__kraken Description Legacy taxonomic classification workflow.
    Component ID step_3TX_species__mash Description Fast genome distance estimation using MinHash.
    """
    
    chat_history = [
        HumanMessage(content="I want to use the raw reads processing pipeline. But please swap the Kraken tool for Mash screen.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer evaluating an AI system. Read the RAG context and the AI reply. Give strict scores for Faithfulness and Relevance. The AI must explain the swap clearly."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[Adapt Reads Mash Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[Adapt Reads Mash Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low."


def test_rag_retrieval_adapt_staph_spades():
    store = InMemoryStore()
    
    query = "I want to use the enterotoxin S aureus finder pipeline. But please use SPAdes instead of Unicycler for the assembly part."
    
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "module_enterotoxin_saureus_finder" in context.lower(), "Context Relevance Failed Missing Staph template."
    assert "step_2as_denovo__spades" in context.lower(), "Context Relevance Failed Missing SPAdes tool."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_adapt_staph_spades():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_enterotoxin_saureus_finder Description Specific pipeline for detecting enterotoxin genes. Performs de novo assembly with Unicycler followed by BLAST.
    Component ID step_2AS_denovo__unicycler Description Short read assembly optimizer workflow.
    Component ID step_2AS_denovo__spades Description Accurate de novo assembly workflow.
    Component ID step_4AN_AMR__blast Description Detect enterotoxin genes.
    """
    
    chat_history = [
        HumanMessage(content="I want to use the enterotoxin S aureus finder pipeline. But please use SPAdes instead of Unicycler. I am ready to build.")
    ]
    
    result = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    assert result.used_template_id == "module_enterotoxin_saureus_finder", "Logic Failed Wrong template."
    assert "step_2AS_denovo__spades" in result.selected_module_ids, "Logic Failed Missing SPAdes."
    assert "step_2AS_denovo__unicycler" not in result.selected_module_ids, "Logic Failed Kept Unicycler by mistake."
    assert "step_4AN_AMR__blast" in result.selected_module_ids, "Logic Failed Missing BLAST step."
    assert result.strategy_selector == "ADAPTED_MATCH", "Logic Failed Agent did not select ADAPTED_MATCH."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_academic_quality_adapt_staph_spades():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
        ("placeholder", "{messages}")
    ])
    
    mock_context = """
    Template ID module_enterotoxin_saureus_finder Description Specific pipeline for detecting enterotoxin genes. Performs de novo assembly with Unicycler followed by BLAST.
    Component ID step_2AS_denovo__unicycler Description Short read assembly optimizer workflow.
    Component ID step_2AS_denovo__spades Description Accurate de novo assembly workflow.
    """
    
    chat_history = [
        HumanMessage(content="I want to use the enterotoxin S aureus finder pipeline. But please use SPAdes instead of Unicycler.")
    ]
    
    consultant_response = (prompt | agent).invoke({
        "context": mock_context,
        "messages": chat_history
    })
    
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an academic reviewer evaluating an AI system. Read the RAG context and the AI reply. Give strict scores for Faithfulness and Relevance. The AI must explain the assembly tool swap clearly."),
        ("human", "RAG Context {context}\nUser asked {query}\nAI Replied {reply}")
    ])
    
    evaluation = (judge_prompt | judge_llm).invoke({
        "context": mock_context,
        "query": chat_history[-1].content,
        "reply": consultant_response.response_to_user
    })
    
    print("\n[Adapt Staph SPAdes Eval] Faithfulness " + str(evaluation.faithfulness_score) + " and reason is " + evaluation.faithfulness_reason)
    print("[Adapt Staph SPAdes Eval] Relevance " + str(evaluation.relevance_score) + " and reason is " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low."