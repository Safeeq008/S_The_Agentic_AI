import os
import json
import logging
from datetime import datetime
from typing import Optional
from exa_py import Exa
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

logger = logging.getLogger(__name__)

api_key = os.environ.get("EXA_API_KEY", "e4f681d3-e238-4934-97ad-94f095cebe56")
exa_client = Exa(api_key=api_key)


EXA_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the web for current information. Use this when the user "
            "asks about recent events, real-time data, specific websites, or "
            "anything requiring up-to-date knowledge beyond your training data. "
            "ALWAYS use this for news, sports, weather, stocks, or any current topic."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query string",
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (1-10, default 5)",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 10,
                },
                "include_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of domains to restrict search to",
                },
                "exclude_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of domains to exclude from search",
                },
                "start_published_date": {
                    "type": "string",
                    "description": "ISO 8601 date — only results published after this date",
                },
                "end_published_date": {
                    "type": "string",
                    "description": "ISO 8601 date — only results published before this date",
                },
            },
            "required": ["query"],
        },
    },
}

GET_CURRENT_TIME_TOOL = {
    "type": "function",
    "function": {
        "name": "get_current_time",
        "description": "Get the current date and time. Use this when the user asks about today's date, current time, or needs to know the current datetime.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}

EXECUTE_CODE_TOOL = {
    "type": "function",
    "function": {
        "name": "execute_calculation",
        "description": "Execute a mathematical calculation or simple Python expression. Use this when the user asks to calculate something.",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "The mathematical expression to evaluate (e.g., '2 + 2', 'sqrt(144)', '100 * 3.14')",
                }
            },
            "required": ["expression"],
        },
    },
}

ALL_TOOLS = [EXA_SEARCH_TOOL, GET_CURRENT_TIME_TOOL, EXECUTE_CODE_TOOL]


def execute_get_current_time() -> dict:
    """Return the current date and time."""
    now = datetime.now()
    return {
        "datetime": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "day_of_week": now.strftime("%A"),
        "timezone": "local",
    }


def execute_calculation(expression: str) -> dict:
    """Safely evaluate a mathematical expression."""
    import math

    allowed_names = {
        "abs": abs, "round": round,
        "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos,
        "tan": math.tan, "pi": math.pi, "e": math.e,
        "log": math.log, "log10": math.log10, "pow": pow,
        "min": min, "max": max, "sum": sum,
    }

    try:
        result = eval(expression, {"__builtins__": {}}, allowed_names)
        return {"expression": expression, "result": result}
    except Exception as e:
        return {"expression": expression, "error": str(e)}


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((Exception,)),
    reraise=True,
)
def execute_exa_search(
    query: str,
    num_results: int = 5,
    include_domains: Optional[list[str]] = None,
    exclude_domains: Optional[list[str]] = None,
    start_published_date: Optional[str] = None,
    end_published_date: Optional[str] = None,
) -> dict:
    """
    Execute a web search via the EXA API with automatic retry on
    rate limits and transient server errors.
    """
    try:
        results = exa_client.search_and_contents(
            query,
            type="auto",
            num_results=num_results,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            start_published_date=start_published_date,
            end_published_date=end_published_date,
        )

        formatted = []
        for r in results.results:
            formatted.append({
                "title": r.title or "Untitled",
                "url": r.url,
                "highlights": getattr(r, "highlights", []) or [],
                "published_date": getattr(r, "published_date", None),
                "text": getattr(r, "text", "")[:500] if getattr(r, "text", None) else "",
            })

        logger.info(f"EXA search '{query}' returned {len(formatted)} results")
        return {"results": formatted, "query": query}

    except Exception as e:
        error_str = str(e)
        if "429" in error_str or "RATE_LIMIT" in error_str.upper():
            logger.warning(f"EXA rate limit hit for query '{query}': {e}")
            raise
        logger.error(f"EXA search failed: {e}")
        raise


def format_search_results_for_model(results: dict) -> str:
    """Convert EXA results into a compact text block for the model context."""
    if not results.get("results"):
        return "No search results found for this query."

    lines = [f"Search results for: {results['query']}\n"]
    for i, r in enumerate(results["results"], 1):
        lines.append(f"{i}. [{r['title']}]({r['url']})")
        if r.get("published_date"):
            lines.append(f"   Published: {r['published_date']}")
        if r.get("highlights"):
            for h in r["highlights"][:2]:
                lines.append(f"   - {h}")
        if r.get("text"):
            lines.append(f"   Preview: {r['text'][:200]}...")
        lines.append("")
    return "\n".join(lines)