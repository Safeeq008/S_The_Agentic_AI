import os
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from sse_starlette.sse import EventSourceResponse
import httpx

from models.schemas import ChatRequest, SSEEventType
from agent.ollama_client import run_agent_stream, client as ollama_client

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "hf.co/Salesforce/xLAM-2-1b-fc-r-gguf:Q4_K_M")
CORS_ORIGINS = os.environ.get(
    "CORS_ORIGINS", "http://localhost:5173"
).split(",")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Verify Ollama connectivity and model availability on startup."""
    logger.info(f"Checking Ollama at {OLLAMA_HOST}...")
    try:
        async with httpx.AsyncClient(timeout=5.0) as http:
            resp = await http.get(f"{OLLAMA_HOST}/api/tags")
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            logger.info(f"Ollama is running. Available models: {models}")
            if not any(OLLAMA_MODEL in m for m in models):
                logger.warning(
                    f"Model '{OLLAMA_MODEL}' not found. Run: ollama pull {OLLAMA_MODEL}"
                )
    except Exception as e:
        logger.error(f"Cannot reach Ollama: {e}")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="Agentic Search Backend",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS configuration for the Vite dev server ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Health check endpoint — verifies both Ollama and EXA connectivity."""
    status = {"ollama": "unknown", "model": OLLAMA_MODEL, "exa": "unknown"}

    try:
        async with httpx.AsyncClient(timeout=3.0) as http:
            resp = await http.get(f"{OLLAMA_HOST}/api/tags")
            resp.raise_for_status()
            status["ollama"] = "connected"
    except Exception as e:
        status["ollama"] = f"error: {e}"

    # Quick EXA check — search for something trivial
    try:
        from agent.exa_tools import exa_client
        result = exa_client.search("test", num_results=1)
        status["exa"] = "connected" if result.results else "empty"
    except Exception as e:
        status["exa"] = f"error: {e}"

    return status


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    SSE endpoint that streams the agent's reasoning, tool calls,
    and final response token-by-token.
    """
    history = [msg.model_dump() for msg in request.history]

    async def event_generator():
        try:
            async for event in run_agent_stream(request.message, history):
                yield {
                    "event": event["type"],
                    "data": json.dumps(event["data"], ensure_ascii=False),
                }
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield {
                "event": SSEEventType.error,
                "data": json.dumps({"message": str(e)}),
            }

    return EventSourceResponse(event_generator())


@app.post("/api/chat")
async def chat_sync(request: ChatRequest):
    """Non-streaming fallback endpoint."""
    from agent.ollama_client import run_agent_stream

    history = [msg.model_dump() for msg in request.history]
    full_content = ""
    tool_calls_made = []

    async for event in run_agent_stream(request.message, history):
        if event["type"] == SSEEventType.token:
            full_content += event["data"]
        elif event["type"] == SSEEventType.tool_call_start:
            tool_calls_made.append(event["data"])

    return {
        "content": full_content,
        "tool_calls": tool_calls_made,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )