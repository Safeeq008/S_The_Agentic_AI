import os
import json
import re
import logging
from typing import AsyncGenerator
import ollama
from ollama import AsyncClient

from agent.exa_tools import (
    ALL_TOOLS,
    EXA_SEARCH_TOOL,
    execute_exa_search,
    format_search_results_for_model,
    execute_get_current_time,
    execute_calculation,
)
from models.schemas import SSEEventType

logger = logging.getLogger(__name__)

OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:1.5b-instruct")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

client = AsyncClient(host=OLLAMA_HOST)

SYSTEM_PROMPT = """You are a helpful AI assistant with access to tools.

RULES:
1. For ANY question about news, sports (NFL, NBA, etc.), weather, stocks, current events, recent events, today/tomorrow/yesterday, or anything requiring current information - you MUST use the web_search tool FIRST.
2. For questions about specific people, companies, products, or events - use web_search to get current information.
3. For questions about date/time - use get_current_time.
4. For math questions - use execute_calculation.
5. When in doubt - ALWAYS use web_search. It is better to search unnecessarily than to give outdated information.
6. NEVER say "I cannot provide real-time data" or "I don't have access to current information". You HAVE the tools. USE THEM.
7. After receiving search results, cite sources using format: [Title](URL)

Topics requiring web_search:
- Sports (NFL, NBA, MLB, soccer) - scores, news, schedules
- News (world, politics, business, technology)
- Weather, forecasts
- Stock/crypto prices
- Any question with "today", "latest", "recent", "current", "now"
- Years (2024, 2025, 2026)"""


REALTIME_KEYWORDS = [
    r"\bnews\b", r"\bsports\b", r"\bnfl\b", r"\bnba\b", r"\bmlb\b",
    r"\bweather\b", r"\bstock\b", r"\bcrypto\b", r"\bprice\b",
    r"\btoday\b", r"\btonight\b", r"\btomorrow\b", r"\byesterday\b",
    r"\blast\b", r"\blatest\b", r"\bcurrent\b", r"\brecent\b",
    r"\bright now\b", r"\bnow\b", r"\bthis week\b", r"\bthis month\b",
    r"\bscore\b", r"\bscores\b", r"\bgame\b", r"\bmatch\b",
    r"\belection\b", r"\bmarket\b", r"\beconomy\b",
    r"\b2024\b", r"\b2025\b", r"\b2026\b",
    r"\bwho won\b", r"\bwho is\b", r"\bwhat happened\b",
    r"\bupdate\b", r"\bbreaking\b", r"\bannouncement\b",
]

def needs_web_search(query: str) -> bool:
    """Detect if a query likely requires real-time web search."""
    q = query.lower()
    return any(re.search(pattern, q) for pattern in REALTIME_KEYWORDS)


async def run_agent_stream(
    user_message: str,
    history: list[dict],
) -> AsyncGenerator[dict, None]:
    """
    Async generator that runs the full agent loop with streaming.
    Yields SSE event dicts: {type, data}.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": user_message},
    ]

    max_iterations = 5
    iteration = 0
    used_tool = False

    while iteration < max_iterations:
        iteration += 1
        tool_calls_accumulated = []
        content_accumulated = ""

        try:
            stream = await client.chat(
                model=OLLAMA_MODEL,
                messages=messages,
                tools=ALL_TOOLS,
                stream=True,
            )

            async for chunk in stream:
                msg = chunk.message

                if getattr(msg, "thinking", None):
                    yield {
                        "type": SSEEventType.thinking,
                        "data": msg.thinking,
                    }

                # BUFFER content — don't yield yet, tool call may follow
                if msg.content:
                    content_accumulated += msg.content

                if getattr(msg, "tool_calls", None):
                    for tc in msg.tool_calls:
                        tool_calls_accumulated.append(tc)

            # ── After streaming completes, check for tool calls ──
            if tool_calls_accumulated:
                used_tool = True

                # Discard the "I'm sorry" text the model generated before tool call
                content_accumulated = ""

                assistant_msg = {
                    "role": "assistant",
                    "content": None,
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

                    elif fn_name == "get_current_time":
                        time_result = execute_get_current_time()
                        yield {
                            "type": SSEEventType.tool_call_result,
                            "data": {
                                "name": fn_name,
                                "result": time_result,
                            },
                        }
                        messages.append({
                            "role": "tool",
                            "content": json.dumps(time_result),
                        })

                    elif fn_name == "execute_calculation":
                        calc_result = execute_calculation(**fn_args)
                        yield {
                            "type": SSEEventType.tool_call_result,
                            "data": {
                                "name": fn_name,
                                "result": calc_result,
                            },
                        }
                        messages.append({
                            "role": "tool",
                            "content": json.dumps(calc_result),
                        })

                continue

            # ── FALLBACK: Model didn't call tool, but query needs real-time data ──
            if not used_tool and needs_web_search(user_message):
                logger.info(f"Fallback: forcing web search for query: {user_message}")

                # Discard the "I can't..." text
                content_accumulated = ""

                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "function": {
                            "name": "web_search",
                            "arguments": {"query": user_message, "num_results": 5},
                        }
                    }],
                })

                yield {
                    "type": SSEEventType.tool_call_start,
                    "data": {
                        "name": "web_search",
                        "arguments": {"query": user_message, "num_results": 5},
                    },
                }

                try:
                    search_results = execute_exa_search(
                        query=user_message, num_results=5
                    )
                    formatted = format_search_results_for_model(search_results)

                    yield {
                        "type": SSEEventType.tool_call_result,
                        "data": {
                            "name": "web_search",
                            "result": search_results,
                        },
                    }

                    messages.append({
                        "role": "tool",
                        "content": formatted,
                    })

                    used_tool = True
                    continue

                except Exception as e:
                    logger.error(f"Fallback search failed: {e}")
                    messages.append({
                        "role": "tool",
                        "content": f"Search failed: {str(e)}",
                    })

            # ── No tool calls, no fallback needed — final response ──
            # Yield any buffered content tokens now
            if content_accumulated:
                yield {
                    "type": SSEEventType.token,
                    "data": content_accumulated,
                }
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

    yield {
        "type": SSEEventType.error,
        "data": {"message": "Maximum tool iterations reached."},
    }