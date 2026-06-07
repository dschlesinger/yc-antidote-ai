"""Tests for the Unsiloed REST API wrapper."""

from unittest.mock import MagicMock, patch

import pytest

from app.models.document import DocumentChunk
from app.services import unsiloed


def _mock_response(status_code: int, json_data: dict) -> MagicMock:
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = json_data
    m.raise_for_status.return_value = None
    return m


def test_submit_document_returns_job_id() -> None:
    with patch.object(unsiloed.requests, "post") as mock_post:
        mock_post.return_value = _mock_response(200, {"job_id": "abc-123"})
        job_id = unsiloed.submit_document(b"%PDF-1.4 fake", "doc.pdf")
    assert job_id == "abc-123"


def test_poll_job_returns_chunks_on_success() -> None:
    with patch.object(unsiloed.requests, "get") as mock_get:
        mock_get.return_value = _mock_response(
            200, {"status": "Succeeded", "chunks": [{"segments": []}]}
        )
        chunks = unsiloed.poll_job("job-1", max_wait_s=5, poll_interval_s=1)
    assert chunks == [{"segments": []}]


def test_poll_job_raises_on_failure() -> None:
    with patch.object(unsiloed.requests, "get") as mock_get:
        mock_get.return_value = _mock_response(
            200, {"status": "Failed", "message": "bad pdf"}
        )
        with pytest.raises(RuntimeError, match="bad pdf"):
            unsiloed.poll_job("job-1", max_wait_s=5, poll_interval_s=1)


def test_extract_chunks_filters_empty_and_attaches_document_name() -> None:
    raw = [
        {
            "segments": [
                {"content": "Revenue $6B", "page_number": 1, "segment_type": "Text"},
                {"content": "  ", "page_number": 1, "segment_type": "Text"},  # empty
                {"content": "Acme Corp", "page_number": 2, "segment_type": "Title"},
            ]
        }
    ]
    result = unsiloed.extract_chunks(raw, "acme.pdf")
    assert len(result) == 2
    assert all(isinstance(c, DocumentChunk) for c in result)
    assert result[0].text == "Revenue $6B"
    assert result[0].page_number == 1
    assert result[0].document_name == "acme.pdf"
    assert result[1].text == "Acme Corp"
    assert result[1].segment_type == "Title"
