from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Generic Chatbot Backend", version="1.0.0")

class ChatRequest(BaseModel):
    session_id: str
    message: str
    context: dict = {}

class ChatResponse(BaseModel):
    reply: str
    sources: list = []

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Error should always be caught at a route level and then transformed 
    and returned for maximum traceability. No emojis.
    """
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error occurred.", "details": str(exc)}
    )

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Main chat endpoint. Responses must be in JSON format and NOT contain ANY emojis.
    """
    try:
        # Mock RAG logic
        # 1. Embed query
        # 2. Search Supabase
        # 3. Generate response with LLM
        
        reply_text = f"Received your message: {request.message}. This is a generic response."
        
        return ChatResponse(
            reply=reply_text,
            sources=["doc_123", "doc_456"]
        )
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail="Failed to process chat request.")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
