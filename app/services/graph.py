from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langchain_core.messages import RemoveMessage, trim_messages

from app.services.graph_state import GraphState
from app.services.agents import consultant_node, hydrator_node, architect_node, diagram_node
from app.services.repair import repair_node, should_repair
from app.services.renderer import renderer_node

def check_consultant_status(state: GraphState):
    if state.get("consultant_status") == "APPROVED":
        return "approved"
    return "chatting"

def delete_messages_node(state: GraphState):
    messages = state.get("messages", [])
    if len(messages) <= 6:
        return {}
        
    trimmed_messages = trim_messages(
        messages,
        max_tokens=6,
        strategy="last",
        token_counter=len,
        include_system=True
    )
    
    trimmed_ids = {m.id for m in trimmed_messages}
    delete_actions = [RemoveMessage(id=m.id) for m in messages if m.id not in trimmed_ids]
    
    return {"messages": delete_actions} if delete_actions else {}

def build_consultant_subgraph():
    sub = StateGraph(GraphState)
    sub.add_node("consultant", consultant_node)
    sub.add_node("delete_messages", delete_messages_node)
    sub.set_entry_point("consultant")
    sub.add_edge("consultant", "delete_messages")
    
    # In a subgraph, we route back to the parent (END) regardless.
    # The parent graph will check the status and route accordingly.
    sub.add_edge("delete_messages", END)
    return sub.compile()

def build_execution_subgraph():
    sub = StateGraph(GraphState)
    sub.add_node("hydrator", hydrator_node)
    sub.add_node("architect", architect_node)
    sub.add_node("repair", repair_node)
    sub.add_node("renderer", renderer_node)
    sub.add_node("diagram", diagram_node)
    
    sub.set_entry_point("hydrator")
    sub.add_edge("hydrator", "architect")
    
    sub.add_conditional_edges(
        "architect",
        should_repair,
        {
            "success": "renderer",
            "repair": "repair",
            "fail": END
        }
    )
    
    sub.add_edge("repair", "architect")
    sub.add_edge("renderer", "diagram")
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