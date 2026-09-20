import os
import json
import logging
from typing import AsyncGenerator
import ollama
from ollama import AsyncClient

from agent.exa_tools import (
    EXA_SEARCH_TOOL,
    execute_exa_search,
    format_search_results_for_model,
)
from models.schemas import SSEEventType

logger = logging.getLogger(__name__)

OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:1.5b-instruct")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

client = AsyncClient(host=OLLAMA_HOST)

# ── System prompt tuned for Qwen2.5's tool-use behavior ──
# Qwen2.5 uses the Hermes-style tool-call format internally. When
# running through Ollama, the model emits OpenAI-compatible tool_calls
# in the response object rather than inline text. [reference:3]
SYSTEM_PROMPT = """You are a helpful AI assistant with access to a web search tool.

When the user asks about current events, real-time data, specific websites, or any topic requiring up-to-date information, use the `web_search` function. Provide clear, concise answers with citations from search results.

If the user's question can be answered with your existing knowledge, respond directly without searching. Always cite sources using the format [Title](URL) when you use search results.

Be concise but thorough. Never fabricate information — if search results are insufficient, say so."""


async def run_agent_stream(
    user_message: str,
    history: list[dict],
) -> AsyncGenerator[dict, None]:
    """
    Async generator that runs the full agent loop with streaming.
    Yields SSE event dicts: {type, data}.

    The loop:
    1. Send messages + tools to Ollama with stream=True
    2. Accumulate streaming chunks; watch for tool_calls
    3. If a tool_call is emitted, execute EXA search
    4. Append tool result to messages and loop again
    5. Yield final content tokens and a done event
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": user_message},
    ]

    max_iterations = 5
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        tool_calls_accumulated = []
        content_accumulated = ""

        try:
            # ── Stream from Ollama ──
            stream = await client.chat(
                model=OLLAMA_MODEL,
                messages=messages,
                tools=[EXA_SEARCH_TOOL],
                stream=True,
            )

            async for chunk in stream:
                msg = chunk.message

                # Thinking trace (if model supports it)
                if getattr(msg, "thinking", None):
                    yield {
                        "type": SSEEventType.thinking,
                        "data": msg.thinking,
                    }

                # Accumulate content tokens
                if msg.content:
                    content_accumulated += msg.content
                    yield {
                        "type": SSEEventType.token,
                        "data": msg.content,
                    }

                # Accumulate tool calls — Ollama streams tool_calls across chunks [reference:4]
                if getattr(msg, "tool_calls", None):
                    for tc in msg.tool_calls:
                        tool_calls_accumulated.append(tc)

            # ── After streaming completes, check for tool calls ──
            if tool_calls_accumulated:
                # Append assistant message with the tool call
                assistant_msg = {
                    "role": "assistant",
                    "content": content_accumulated or None,
                    "tool_calls": [
                        {
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            }
                        }
                        for tc in tool_calls_accumulated
                    ],
                }
                messages.append(assistant_msg)

                for tc in tool_calls_accumulated:
                    fn_name = tc.function.name
                    fn_args = tc.function.arguments

                    # Arguments arrive as a JSON string — parse it [reference:5]
                    if isinstance(fn_args, str):
                        fn_args = json.loads(fn_args)

                    yield {
                        "type": SSEEventType.tool_call_start,
                        "data": {
                            "name": fn_name,
                            "arguments": fn_args,
                        },
                    }

                    if fn_name == "web_search":
                        try:
                            search_results = execute_exa_search(**fn_args)
                            formatted = format_search_results_for_model(search_results)

                            yield {
                                "type": SSEEventType.tool_call_result,
                                "data": {
                                    "name": fn_name,
                                    "result": search_results,
                                },
                            }

                            # Append tool result to messages and continue loop
                            messages.append({
                                "role": "tool",
                                "content": formatted,
                            })
                        except Exception as e:
                            logger.error(f"Tool execution failed: {e}")
                            messages.append({
                                "role": "tool",
                                "content": f"Search failed: {str(e)}. Please answer based on your knowledge.",
                            })

                # Loop again — model will process the tool results
                continue

            # ── No tool calls — this is the final response ──
            yield {
                "type": SSEEventType.done,
                "data": {"content": content_accumulated},
            }
            return

        except Exception as e:
            logger.error(f"Ollama streaming error: {e}")
            yield {
                "type": SSEEventType.error,
                "data": {"message": f"Agent error: {str(e)}"},
            }
            return

    # Max iterations exceeded
    yield {
        "type": SSEEventType.error,
        "data": {"message": "Maximum tool iterations reached."},
    }