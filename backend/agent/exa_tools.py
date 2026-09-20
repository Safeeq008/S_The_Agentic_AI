import os
import logging
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


# ── Tool schema passed to Qwen2.5 via Ollama ──
# Qwen2.5 uses the OpenAI-compatible tool format natively when
# running through Ollama. The model will emit tool_calls in the
# standard OpenAI structure; no schema transformation is needed. [reference:0]
EXA_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the web for current information. Use this when the user "
            "asks about recent events, real-time data, specific websites, or "
            "anything requiring up-to-date knowledge beyond your training data."
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
    rate limits (429) and transient server errors. The EXA SDK
    handles auth via the API key set at construction time.
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
            contents={"highlights": True},  # token-efficient content extraction
        )

        formatted = []
        for r in results.results:
            formatted.append({
                "title": r.title or "Untitled",
                "url": r.url,
                "highlights": getattr(r, "highlights", []) or [],
                "published_date": getattr(r, "published_date", None),
            })

        logger.info(f"EXA search '{query}' returned {len(formatted)} results")
        return {"results": formatted, "query": query}

    except Exception as e:
        error_str = str(e)
        # EXA returns 429 for rate limits; the retry decorator handles backoff [reference:1]
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
            for h in r["highlights"][:2]:  # limit highlights to reduce tokens
                lines.append(f"   - {h}")
        lines.append("")
    return "\n".join(lines)