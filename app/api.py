from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

# Import your custom modules
from app.core.loader import data_loader
from app.services.graph import app_graph

# --- 1. DATA MODELS (Request/Response) ---
class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Unique ID for the user session to remember chat history")
    message: str = Field(..., description="The user's prompt or reply")

class ChatResponse(BaseModel):
    status: str
    reply: str
    nextflow_code: Optional[str] = None
    mermaid_code: Optional[str] = None
    error: Optional[str] = None

# --- 2. LIFESPAN (Startup/Shutdown Logic) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        data_loader.load_all()
    except Exception as e:
        print(f"CRITICAL STARTUP ERROR {e}")
    yield
    print("Server shutting down...")

# --- 3. API APP DEFINITION ---
app = FastAPI(
    title="Nextflow AI Agent API",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],    
    allow_headers=["*"],    
)

# --- 4. ENDPOINTS ---

@app.get("/health")
def health_check():
    return {
        "status": "online", 
        "vector_store": "loaded" if data_loader.vector_store else "not_loaded"
    }

@app.post("/chat", response_model=ChatResponse)
async def chat_with_agent(request: ChatRequest):
    try:
        # Set up the thread ID so the agent remembers the chat
        config = {"configurable": {"thread_id": request.session_id}}
        
        # Run the graph with async
        result = await app_graph.ainvoke(
            {
                "user_query": request.message,
                "messages": [("user", request.message)]
            }, 
            config=config
        )
        
        # Check for agent errors
        if result.get("error"):
            return ChatResponse(
                status="failed",
                reply="The agent encountered an error.",
                error=result["error"]
            )

        # Get the AI reply from the messages list
        messages = result.get("messages", [])
        ai_reply = messages[-1].content if messages else "No response generated."
        
        # Get the status and final codes
        status = result.get("consultant_status", "CHATTING")
        nf_code = result.get("nextflow_code")
        mermaid = result.get("mermaid_code")
        
        return ChatResponse(
            status=status,
            reply=ai_reply,
            nextflow_code=nf_code,
            mermaid_code=mermaid,
            error=None
        )

    except Exception as e:
        print(f"Server Error {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))