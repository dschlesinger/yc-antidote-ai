"""Moss semantic search service for real-time fact retrieval."""

from moss import DocumentInfo, MossClient, MutationOptions, QueryOptions

from app.config import settings
from app.models.document import DocumentChunk

_client = MossClient(settings.moss_project_id, settings.moss_project_key)


async def ensure_index() -> None:
    """Load the shared due-diligence index into memory (idempotent)."""
    await _client.load_index(settings.moss_index_name)


async def add_document_chunks(chunks: list[DocumentChunk]) -> None:
    """Upsert parsed document chunks into the shared Moss index."""
    docs = [
        DocumentInfo(
            id=f"{c.document_name}:{c.page_number}:{i}",
            text=c.text,
            metadata={
                "document": c.document_name,
                "page": str(c.page_number or ""),
                "type": c.segment_type or "",
            },
        )
        for i, c in enumerate(chunks)
    ]
    await _client.add_docs(
        settings.moss_index_name,
        docs,
        MutationOptions(upsert=True),
    )


async def search(query: str, top_k: int = 5) -> list[dict]:
    """Semantic search against the due-diligence index. Returns source-attributed results."""
    results = await _client.query(
        settings.moss_index_name,
        query,
        QueryOptions(top_k=top_k),
    )
    return [
        {
            "text": r.text,
            "document": r.metadata.get("document", ""),
            "page": r.metadata.get("page"),
            "score": r.score,
        }
        for r in results
    ]
