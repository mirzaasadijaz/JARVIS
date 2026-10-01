"""Shared ChromaDB embedding function — used by tools/memory.py (notes)
and tools/documents.py (RAG over ingested files) so both collections
embed consistently and there's one place to swap providers.

To switch to the free local option instead of Voyage (see the Tech
Stack Guide — Granite Embedding Multilingual R2, for Urdu support),
replace the body of __call__ with a sentence-transformers call; nothing
else in either calling file needs to change.
"""

from chromadb.api.types import EmbeddingFunction

from config import settings


class VoyageEmbeddingFunction(EmbeddingFunction):
    def __init__(self):
        settings.require("voyage_api_key")
        import voyageai

        self._client = voyageai.Client(api_key=settings.voyage_api_key)

    def __call__(self, input: list[str]) -> list[list[float]]:
        result = self._client.embed(texts=input, model="voyage-4-lite", input_type="document")
        return result.embeddings
