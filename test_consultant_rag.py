import pytest
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.store.memory import InMemoryStore

from app.services.tools import retrieve_rag_context, _inject_template, _inject_component
from app.services.agents import CONSULTANT_SYSTEM_PROMPT
from app.models.consultant_structure import ConsultantOutput
from app.services.llm import get_llm, get_judge_llm, with_rate_limit_retry
from app.core.loader import data_loader

store = InMemoryStore()

@pytest.fixture(scope="session", autouse=True)
def setup_database():
    print("Loading the real vector store and catalog for testing.")
    data_loader.load_all(store=store)
    print("Database loaded successfully.")

# ==========================================
# GLOBAL SCHEMAS & PROMPTS
# ==========================================

class AcademicEval(BaseModel):
    faithfulness_reason: str = Field(description="Step by step reasoning explaining if the AI invented tools or stuck perfectly to the RAG context.")
    faithfulness_score: int = Field(description="Score 1 to 5 based on the rubric.")
    relevance_reason: str = Field(description="Step by step reasoning explaining if the AI answered the specific biological scenario from the user.")
    relevance_score: int = Field(description="Score 1 to 5 based on the rubric.")

# Reusable Agent Prompt
CONSULTANT_TEST_PROMPT = ChatPromptTemplate.from_messages([
    ("system", CONSULTANT_SYSTEM_PROMPT + "\n\nAVAILABLE RAG CONTEXT\n{context}"),
    ("placeholder", "{messages}")
])

# Reusable Strict Judge Prompt with Rubric
JUDGE_SYSTEM_STRING = """You are a very strict academic reviewer evaluating an AI system for bioinformatics. 
Read the RAG context and the conversation. Write your reasoning first then give the score based on these exact rules.

FAITHFULNESS SCORE RUBRIC:
5: Perfect. The AI only uses the tools from the catalog and nothing else.
4: Good. The AI uses the tools but maybe adds a tiny general fact that is not in the text.
3: Okay. The AI uses the tools but talks a bit too much about outside tools.
2: Bad. The AI tries to put a tool in the pipeline that is not in the catalog.
1: Very bad. The AI completely makes up fake tools and fake pipeline names.

RELEVANCE SCORE RUBRIC:
5: Perfect. The AI gives the exact right pipeline and follows all rules like checking the data type.
4: Good. The AI gives the right pipeline but maybe misses a very small preference from the user.
3: Okay. The AI gives a pipeline but ignores a big rule (like using a short read tool for long read data).
2: Bad. The AI picks the wrong template (like giving a bacteria pipeline when the user has a virus).
1: Very bad. The AI completely ignores what the user asked for.
"""

JUDGE_TEST_PROMPT = ChatPromptTemplate.from_messages([
    ("system", JUDGE_SYSTEM_STRING),
    ("human", "RAG Context\n{context}\n\nConversation History\n{chat}\n\nFinal AI Reply to Evaluate\n{reply}")
])

# ==========================================
# GLOBAL HELPER FUNCTIONS
# ==========================================

def get_exact_context(template_ids, component_ids, store):
    """Bypasses vector search to inject exact catalog items for deterministic logic testing."""
    found_ids = set()
    context_blocks = []
    for tid in template_ids:
        _inject_template(tid, found_ids, context_blocks, store, embed_code=False)
    for cid in component_ids:
        _inject_component(cid, found_ids, context_blocks, store, embed_code=False)
    return "\n".join(context_blocks) + "\n\n"

def force_approve_consultant(agent, real_context, chat_history, max_attempts=3):
    """Runs the agent and automatically retries if it gets stuck in CHATTING status."""
    chain = CONSULTANT_TEST_PROMPT | agent
    for attempt in range(max_attempts):
        result = chain.invoke({"context": real_context, "messages": chat_history})
        
        if result.status == "APPROVED":
            return result # Success
            
        print(f"\n[Attempt {attempt+1}] Agent returned status '{result.status}'. Nudging for approval...")
        chat_history.append(AIMessage(content=result.response_to_user))
        chat_history.append(HumanMessage(content="I explicitly APPROVE this pipeline plan. I am ready to build. Please change your status to APPROVED and output the module IDs."))
    
    pytest.fail(f"Agent stubbornly refused to approve after {max_attempts} attempts. Final status: {result.status} | AI said: {result.response_to_user}")

def run_academic_judge(judge_llm, real_context, chat_history, ai_reply):
    """Runs the LLM judge, prints the reasoning, and asserts strict scores."""
    formatted_chat = "\n".join([f"{m.type.capitalize()}: {m.content}" for m in chat_history])
    evaluation = (JUDGE_TEST_PROMPT | judge_llm).invoke({
        "context": real_context,
        "chat": formatted_chat,
        "reply": ai_reply
    })
    
    print("\nFaithfulness " + str(evaluation.faithfulness_score) + " - " + evaluation.faithfulness_reason)
    print("Relevance " + str(evaluation.relevance_score) + " - " + evaluation.relevance_reason)
    
    assert evaluation.faithfulness_score >= 4, "Faithfulness is too low."
    assert evaluation.relevance_score >= 4, "Relevance is too low."

# ==========================================
# ACTUAL TESTS
# ==========================================

def test_rag_retrieval_virologist_wnv():
    query = "We have a large bird die-off in the area. I suspect it is West Nile. I need a pipeline to analyze the sequence data and figure out the exact viral lineage."
    context = retrieve_rag_context(query, store, embed_code=False)
    
    assert "module_westnile" in context.lower(), "Context Relevance Failed. Missing template."
    assert "step_4TY_lineage__westnile" in context.lower(), "Context Relevance Failed. Missing tool."

@with_rate_limit_retry(max_attempts=3, delay_seconds=25)
def test_consultant_logic_and_quality_virologist_wnv():
    llm = get_llm()
    agent = llm.with_structured_output(ConsultantOutput)
    judge_llm = get_judge_llm(temperature=0.0).with_structured_output(AcademicEval)
    
    # 1. Setup Exact Context & Scenario
    real_context = get_exact_context(["module_westnile"], ["step_4TY_lineage__westnile"], store)
    chat_history = [
        HumanMessage(content="We're dealing with a sudden cluster of dead crows and blue jays. We suspect a flavivirus, likely West Nile. I have paired-end Illumina reads. I need to figure out the exact viral lineage to trace the origin."),
        AIMessage(content="I can assist with that. The West Nile Virus surveillance pipeline (`module_westnile`) is designed exactly for this. It uses `step_4TY_lineage__westnile` to compute the lineage and then dynamically maps the reads. Does that sound like what you need?"),
        HumanMessage(content="That sounds right, but my reads are already trimmed by our core facility using fastp. Will that work with this pipeline?"),
        AIMessage(content="Yes, absolutely. The `module_westnile` template explicitly accepts `fastq_trimmed` as input, so your data is perfect for this. Shall I go ahead and finalize the pipeline design for the Architect?"),
        HumanMessage(content="Perfect. Yes, I completely approve the plan. I am ready to build.")
    ]
    
    # 2. Run Consultant
    result = force_approve_consultant(agent, real_context, chat_history)
    
    # 3. Assert Logic Outputs
    assert result.used_template_id == "module_westnile", f"Logic Failed. Expected 'module_westnile', got '{result.used_template_id}'"
    assert "step_4TY_lineage__westnile" in result.selected_module_ids, "Logic Failed. Missing 'step_4TY_lineage__westnile' module."

    # 4. Run Judge Eval
    run_academic_judge(judge_llm, real_context, chat_history, result.response_to_user)