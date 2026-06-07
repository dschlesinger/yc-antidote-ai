"""Moss semantic search service for real-time fact retrieval."""

import logging

from moss import DocumentInfo, MossClient, MutationOptions, QueryOptions

from app.config import settings
from app.models.document import DocumentChunk

logger = logging.getLogger(__name__)

_client = MossClient(settings.moss_project_id, settings.moss_project_key)


_index_ready = False


async def ensure_index() -> None:
    """Load the index into memory. Auto-create with a placeholder doc if missing.

    Non-fatal: errors are logged so the server can still boot and serve non-Moss
    routes (auth, LiveKit token issuance). Moss-dependent endpoints will error
    on demand.
    """
    global _index_ready
    try:
        await _client.load_index(settings.moss_index_name)
        _index_ready = True
        logger.info("Loaded Moss index '%s'", settings.moss_index_name)
    except RuntimeError as e:
        if "INDEX_NOT_FOUND" in str(e):
            try:
                await _client.create_index(
                    settings.moss_index_name,
                    [DocumentInfo(id="__bootstrap__", text="Antidote AI knowledge base.")],
                    "moss-minilm",
                )
                await _client.load_index(settings.moss_index_name)
                _index_ready = True
                logger.info("Created and loaded Moss index '%s'", settings.moss_index_name)
            except Exception as create_err:
                logger.warning("Moss index creation failed (non-fatal): %s", create_err)
        else:
            logger.warning("Moss index load failed (non-fatal): %s", e)


def is_ready() -> bool:
    return _index_ready


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
    result = await _client.query(
        settings.moss_index_name,
        query,
        QueryOptions(top_k=top_k),
    )
    return [
        {
            "text": d.text,
            "document": d.metadata.get("document", ""),
            "page": d.metadata.get("page"),
            "score": d.score,
        }
        for d in (result.docs or [])
    ]
