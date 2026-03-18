from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import RemoveMessage

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
    if len(messages) > 6:
        return {"messages": [RemoveMessage(id=m.id) for m in messages[:-6]]}
    return {}

def build_graph():
    workflow = StateGraph(GraphState)

    workflow.add_node("consultant", consultant_node)
    workflow.add_node("delete_messages", delete_messages_node)
    workflow.add_node("hydrator", hydrator_node)
    workflow.add_node("architect", architect_node)
    workflow.add_node("repair", repair_node)
    workflow.add_node("renderer", renderer_node)
    workflow.add_node("diagram", diagram_node)

    workflow.set_entry_point("consultant")

    workflow.add_edge("consultant", "delete_messages")

    workflow.add_conditional_edges(
        "delete_messages",
        check_consultant_status,
        {
            "chatting": END,
            "approved": "hydrator"
        }
    )

    workflow.add_edge("hydrator", "architect")

    workflow.add_conditional_edges(
        "architect",
        should_repair,
        {
            "success": "renderer",
            "repair": "repair",
            "fail": END
        }
    )

    workflow.add_edge("repair", "architect")
    workflow.add_edge("renderer", "diagram")
    workflow.add_edge("diagram", END)

    checkpointer = InMemorySaver()

    return workflow.compile(checkpointer=checkpointer)

app_graph = build_graph()