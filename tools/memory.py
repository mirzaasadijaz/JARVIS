"""@tool save_note, search_notes — ChromaDB + Voyage AI embeddings.

Uses the shared embedding function in core/embeddings.py — see that
file for how to switch to the free local option instead of Voyage.
tools/documents.py (file/RAG search) uses the same one, in its own
"documents" collection, separate from these short user-authored notes.
"""

import chromadb
from langchain_core.tools import tool

from core.embeddings import VoyageEmbeddingFunction

_DB_PATH = "data/chroma"
_COLLECTION_NAME = "notes"

_collection = None


def _get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=_DB_PATH)
        _collection = client.get_or_create_collection(
            name=_COLLECTION_NAME, embedding_function=VoyageEmbeddingFunction()
        )
    return _collection


@tool
def save_note(text: str) -> str:
    """Save a note for later semantic search."""
    import uuid

    _get_collection().add(documents=[text], ids=[str(uuid.uuid4())])
    return "Saved."


@tool
def search_notes(query: str, n_results: int = 5) -> str:
    """Search past notes by meaning, not exact keywords.

    Args:
        query: What you're trying to recall
        n_results: How many matches to return (default 5)
    """
    results = _get_collection().query(query_texts=[query], n_results=n_results)
    documents = results.get("documents", [[]])[0]
    if not documents:
        return "No matching notes found."
    return "\n".join(f"- {doc}" for doc in documents)


@tool
def save_note(text: str) -> str:
    """Save a note for later semantic search."""
    import uuid

    _get_collection().add(documents=[text], ids=[str(uuid.uuid4())])
    return "Saved."


@tool
def search_notes(query: str, n_results: int = 5) -> str:
    """Search past notes by meaning, not exact keywords.

    Args:
        query: What you're trying to recall
        n_results: How many matches to return (default 5)
    """
    results = _get_collection().query(query_texts=[query], n_results=n_results)
    documents = results.get("documents", [[]])[0]
    if not documents:
        return "No matching notes found."
    return "\n".join(f"- {doc}" for doc in documents)
