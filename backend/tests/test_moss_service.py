"""Tests for the Moss semantic search wrapper."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.document import DocumentChunk
from app.services import moss_service


@pytest.mark.asyncio
async def test_ensure_index_creates_when_missing() -> None:
    with patch.object(moss_service, "_client") as mock_client:
        mock_client.load_index = AsyncMock(
            side_effect=[
                RuntimeError("Failed: INDEX_NOT_FOUND"),  # initial load fails
                None,  # post-create load succeeds
            ]
        )
        mock_client.create_index = AsyncMock(return_value=None)
        await moss_service.ensure_index()
    mock_client.create_index.assert_awaited_once()
    assert moss_service.is_ready() is True


@pytest.mark.asyncio
async def test_ensure_index_swallows_unknown_errors() -> None:
    moss_service._index_ready = False
    with patch.object(moss_service, "_client") as mock_client:
        mock_client.load_index = AsyncMock(side_effect=RuntimeError("boom"))
        # Should not raise — just warn and leave _index_ready False.
        await moss_service.ensure_index()
    assert moss_service.is_ready() is False


@pytest.mark.asyncio
async def test_add_document_chunks_calls_add_docs_with_upsert() -> None:
    chunks = [
        DocumentChunk(
            text="Acme made $6B", page_number=1, segment_type="Text", document_name="a.pdf"
        ),
        DocumentChunk(
            text="EBITDA was $1B", page_number=2, segment_type="Text", document_name="a.pdf"
        ),
    ]
    with patch.object(moss_service, "_client") as mock_client:
        mock_client.add_docs = AsyncMock(return_value=None)
        await moss_service.add_document_chunks(chunks)
    call = mock_client.add_docs.call_args
    assert call.args[0] == moss_service.settings.moss_index_name
    docs = call.args[1]
    assert len(docs) == 2
    assert docs[0].text == "Acme made $6B"
    assert docs[0].metadata["document"] == "a.pdf"


@pytest.mark.asyncio
async def test_search_returns_dict_results() -> None:
    fake_result = MagicMock()
    fake_result.text = "Revenue $6B"
    fake_result.metadata = {"document": "acme.pdf", "page": "1"}
    fake_result.score = 0.92
    with patch.object(moss_service, "_client") as mock_client:
        mock_client.query = AsyncMock(return_value=[fake_result])
        results = await moss_service.search("acme revenue", top_k=3)
    assert results == [
        {"text": "Revenue $6B", "document": "acme.pdf", "page": "1", "score": 0.92}
    ]
