"""Tests for the documents upload + status router."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.deps.auth import AuthUser, get_current_user
from app.main import app
from app.routers import documents


def _override_user() -> AuthUser:
    return AuthUser(user_id="test-user", email="test@example.com")


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = _override_user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_upload_requires_auth() -> None:
    # Without overriding, no token = 401.
    with TestClient(app) as c:
        r = c.post("/api/documents/", files={"file": ("a.pdf", b"%PDF-1.4")})
    assert r.status_code == 401


def test_upload_accepts_and_registers_job(client: TestClient) -> None:
    documents._jobs.clear()
    with patch.object(documents.unsiloed, "submit_document", return_value="job-xyz"), \
         patch("asyncio.create_task") as mock_task:
        r = client.post("/api/documents/", files={"file": ("a.pdf", b"%PDF-1.4")})
        mock_task.assert_called_once()
    assert r.status_code == 202
    body = r.json()
    assert body["unsiloed_job_id"] == "job-xyz"
    assert body["status"] == "processing"
    assert "job-xyz" in documents._jobs


def test_get_status_returns_job(client: TestClient) -> None:
    documents._jobs["job-abc"] = {"status": "ready", "name": "doc.pdf", "error": None}
    r = client.get("/api/documents/job-abc")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_get_status_404_for_missing_job(client: TestClient) -> None:
    documents._jobs.clear()
    r = client.get("/api/documents/does-not-exist")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_process_document_indexes_and_marks_ready() -> None:
    documents._jobs["job-1"] = {"status": "processing", "name": "x.pdf", "error": None}
    poll_patch = patch.object(documents.unsiloed, "poll_job", return_value=[{"segments": []}])
    extract_patch = patch.object(documents.unsiloed, "extract_chunks", return_value=[])
    add_patch = patch.object(
        documents.moss_service, "add_document_chunks", new=AsyncMock(return_value=None)
    )
    with poll_patch as mock_poll, extract_patch as mock_extract, add_patch as mock_add:
        await documents._process_document("job-1", "x.pdf")
    mock_poll.assert_called_once_with("job-1")
    mock_extract.assert_called_once()
    mock_add.assert_awaited_once()
    assert documents._jobs["job-1"]["status"] == "ready"


@pytest.mark.asyncio
async def test_process_document_marks_error_on_exception() -> None:
    documents._jobs["job-2"] = {"status": "processing", "name": "x.pdf", "error": None}
    with patch.object(documents.unsiloed, "poll_job", side_effect=RuntimeError("Unsiloed down")):
        await documents._process_document("job-2", "x.pdf")
    assert documents._jobs["job-2"]["status"] == "error"
    assert "Unsiloed down" in documents._jobs["job-2"]["error"]
