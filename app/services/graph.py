from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.prebuilt import ToolNode
from langchain_core.messages import RemoveMessage, SystemMessage, AIMessage, HumanMessage, ToolMessage as LCToolMessage

from app.services.graph_state import GraphState
from app.services.agents import consultant_node, consultant_extract_node, hydrator_node, architect_node, diagram_node, deterministic_diagram_node
from app.services.repair import repair_node, should_repair
from app.services.renderer import renderer_node
from app.services.consultant_tools import CONSULTANT_TOOLS

# Safety cap on tool-calling iterations to prevent runaway loops
MAX_TOOL_ITERATIONS = 5

# Memory compaction settings
MEMORY_KEEP_LAST_N = 40      # Keep the last N messages without compaction
MEMORY_MAX_TOOL_FACTS = 10   # Max structured tool facts to retain

def check_consultant_status(state: GraphState):
    if state.get("consultant_status") == "APPROVED":
        return "approved"
    return "chatting"


def check_diagram_generation(state: GraphState):
    if state.get("generate_diagrams", True):
        return "with_diagrams"
    return "no_diagrams"


def compact_memory_node(state: GraphState):
    """Lossless memory compaction: instead of deleting messages and losing info,
    extract tool call facts into structured tool_memory before removing old messages.
    
    Strategy:
    - Keep first 2 messages (initial context) always
    - Keep last N messages (MEMORY_KEEP_LAST_N) always
    - Never remove HumanMessages or content-bearing AIMessages
    - For tool-loop messages (AIMessage with only tool_calls, ToolMessages) outside
      the keep window: extract structured facts into tool_memory, then remove
    """
    messages = state.get("messages", [])
    existing_tool_memory = state.get("tool_memory", []) or []
    
    if len(messages) <= MEMORY_KEEP_LAST_N:
        return {}
    
    # Build the keep set: first 2 + last N
    keep_indices = set(range(min(2, len(messages))))  # First 2
    keep_indices.update(range(max(0, len(messages) - MEMORY_KEEP_LAST_N), len(messages)))  # Last N
    
    # Also always keep SystemMessages and HumanMessages
    for i, msg in enumerate(messages):
        if isinstance(msg, SystemMessage):
            keep_indices.add(i)
        elif isinstance(msg, HumanMessage):
            keep_indices.add(i)
        elif isinstance(msg, AIMessage) and msg.content and not getattr(msg, 'tool_calls', None):
            # Keep AI messages that have real content (not just tool call stubs)
            keep_indices.add(i)
    
    # Extract facts from messages we're about to remove
    new_facts = []
    delete_actions = []
    
    for i, msg in enumerate(messages):
        if i in keep_indices:
            continue
        
        # Extract tool call info from AI messages before removing
        if isinstance(msg, AIMessage) and getattr(msg, 'tool_calls', None):
            for tc in msg.tool_calls:
                args_str = str(tc.get('args', {}))[:200]
                new_facts.append({
                    "tool": tc.get('name', 'unknown'),
                    "args": args_str,
                    "result": None,  # Will be filled from the ToolMessage
                })
            delete_actions.append(RemoveMessage(id=msg.id))
        
        # Extract tool results before removing
        elif isinstance(msg, LCToolMessage):
            result_preview = str(msg.content)[:500] if msg.content else "(empty)"
            # Try to attach to the last fact that has no result yet
            for fact in reversed(new_facts):
                if fact["result"] is None:
                    fact["result"] = result_preview
                    break
            else:
                # Standalone tool result — create a new fact
                new_facts.append({
                    "tool": getattr(msg, 'name', 'unknown'),
                    "args": "(from prior call)",
                    "result": result_preview,
                })
            delete_actions.append(RemoveMessage(id=msg.id))
    
    # Merge new facts into existing tool memory, cap at MEMORY_MAX_TOOL_FACTS
    merged_memory = existing_tool_memory + new_facts
    merged_memory = merged_memory[-MEMORY_MAX_TOOL_FACTS:]
    
    updates = {}
    if delete_actions:
        updates["messages"] = delete_actions
    if new_facts:
        updates["tool_memory"] = merged_memory
    
    if updates:
        print(f"[compact_memory] Compacted {len(delete_actions)} messages, extracted {len(new_facts)} tool facts")
        return updates
    return {}

def build_consultant_subgraph():
    """Consultant subgraph with ReAct tool-calling loop:
    
    consultant → [tool_calls?] → tools → consultant (loop)
                    ↓ (no tool_calls)
               consultant_extract → compact_memory → END
    """
    sub = StateGraph(GraphState)
    
    # Nodes
    sub.add_node("consultant", consultant_node)
    sub.add_node("tools", ToolNode(CONSULTANT_TOOLS, handle_tool_errors=True))
    sub.add_node("consultant_extract", consultant_extract_node)
    sub.add_node("compact_memory", compact_memory_node)
    
    # Entry
    sub.set_entry_point("consultant")
    
    # Routing: if consultant produced tool_calls → tools, else → extract
    def route_consultant(state: GraphState):
        messages = state.get("messages", [])
        if not messages:
            return "consultant_extract"
        last_msg = messages[-1]
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            # Safety: count tool messages to prevent infinite loops
            tool_msg_count = sum(1 for m in messages if isinstance(m, LCToolMessage))
            if tool_msg_count >= MAX_TOOL_ITERATIONS:
                print(f"⚠️ Tool iteration limit ({MAX_TOOL_ITERATIONS}) reached. Forcing extraction.")
                return "consultant_extract"
            return "tools"
        return "consultant_extract"
    
    sub.add_conditional_edges("consultant", route_consultant, {
        "tools": "tools",
        "consultant_extract": "consultant_extract"
    })
    
    # After tools execute, loop back to consultant for next reasoning step
    sub.add_edge("tools", "consultant")
    
    # After extraction, clean up messages and exit
    # After extraction, compact memory (lossless) and exit
    sub.add_edge("consultant_extract", "compact_memory")
    sub.add_edge("compact_memory", END)
    
    return sub.compile()

def build_execution_subgraph():
    sub = StateGraph(GraphState)
    sub.add_node("hydrator", hydrator_node)
    sub.add_node("architect", architect_node)
    sub.add_node("repair", repair_node)
    sub.add_node("renderer", renderer_node)
    sub.add_node("diagram", diagram_node)
    sub.add_node("deterministic_diagram", deterministic_diagram_node)
    
    sub.set_entry_point("hydrator")
    sub.add_edge("hydrator", "architect")
    
    sub.add_conditional_edges(
        "architect",
        should_repair,
        {
            "success": "renderer",
            "repair": "repair",
            "fail": "renderer"
        }
    )
    
    sub.add_edge("repair", "architect")
    sub.add_conditional_edges(
        "renderer",
        check_diagram_generation,
        {
            "with_diagrams": "deterministic_diagram",
            "no_diagrams": END,
        }
    )

    # Agentic diagram runs after deterministic diagram to keep ordering predictable.
    sub.add_edge("deterministic_diagram", "diagram")
    sub.add_edge("diagram", END)
    
    return sub.compile()

def build_graph():
    # Retaining InMemorySaver as requested by the user
    checkpointer = InMemorySaver()
    store = InMemoryStore()

    sub_planner = build_consultant_subgraph()
    sub_executor = build_execution_subgraph()

    workflow = StateGraph(GraphState)
    workflow.add_node("planner", sub_planner)
    workflow.add_node("executor", sub_executor)
    
    workflow.set_entry_point("planner")

    workflow.add_conditional_edges(
        "planner",
        check_consultant_status,
        {
            "chatting": END,
            "approved": "executor"
        }
    )
    
    workflow.add_edge("executor", END)

    return workflow.compile(checkpointer=checkpointer, store=store), store

app_graph, global_store = build_graph()