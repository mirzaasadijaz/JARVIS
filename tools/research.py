"""@tool search_wikipedia, web_search.

Skip web_search entirely if your brain is Claude — its native web_search
tool (see the Tech Stack Guide, §1) covers this without a separate key.
This file is for the other three brain choices, or if you'd rather keep
research provider-independent from whichever LLM you pick.
"""

import requests
import wikipedia
from langchain_core.tools import tool

from config import settings


@tool
def search_wikipedia(query: str) -> str:
    """Search Wikipedia and return a short summary of the best-matching article."""
    try:
        return wikipedia.summary(query, sentences=3, auto_suggest=True)
    except wikipedia.DisambiguationError as e:
        return f"That's ambiguous — did you mean one of: {', '.join(e.options[:5])}?"
    except wikipedia.PageError:
        return f"No Wikipedia article found for '{query}'."


@tool
def web_search(query: str, num_results: int = 5) -> str:
    """Search the web via SerpAPI. Skip this tool if your brain is Claude
    (use its native web_search tool instead).

    Args:
        query: What to search for
        num_results: How many results to return (default 5)
    """
    settings.require("serpapi_api_key")
    response = requests.get(
        "https://serpapi.com/search",
        params={"q": query, "num": num_results, "api_key": settings.serpapi_api_key},
        timeout=15,
    )
    response.raise_for_status()
    results = response.json().get("organic_results", [])
    if not results:
        return "No results found."
    return "\n".join(f"- {r.get('title', '?')}: {r.get('link', '?')}" for r in results[:num_results])
