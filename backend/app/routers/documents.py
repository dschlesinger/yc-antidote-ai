"""Document upload and indexing endpoint."""

import asyncio
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from app.deps.auth import AuthUser, get_current_user
from app.models.document import DocumentUploadResponse
from app.services import moss_service, unsiloed

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])
_executor = ThreadPoolExecutor(max_workers=4)

# In-memory job status registry (resets on restart).
# Maps unsiloed_job_id -> {"status": str, "name": str, "error": str | None}
_jobs: dict[str, dict] = {}


@router.post("/", response_model=DocumentUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    user: Annotated[AuthUser, Depends(get_current_user)],
    file: UploadFile,
) -> DocumentUploadResponse:
    """Accept a document upload, parse via Unsiloed, and index into Moss."""
    content = await file.read()
    filename = file.filename or "document"
    doc_id = str(uuid.uuid4())

    try:
        job_id = unsiloed.submit_document(content, filename)
    except unsiloed.UnsupportedFileError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Unsiloed unavailable: {e}") from e

    _jobs[job_id] = {"status": "processing", "name": filename, "error": None}
    asyncio.create_task(_process_document(job_id, filename))

    return DocumentUploadResponse(
        id=doc_id,
        name=filename,
        status="processing",
        unsiloed_job_id=job_id,
    )


@router.get("/{job_id}", response_model=DocumentUploadResponse)
async def get_document_status(
    user: Annotated[AuthUser, Depends(get_current_user)],
    job_id: str,
) -> DocumentUploadResponse:
    """Poll the indexing status for a previously uploaded document."""
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return DocumentUploadResponse(
        id=job_id,
        name=job["name"],
        status=job["status"],
        unsiloed_job_id=job_id,
    )


async def _process_document(job_id: str, filename: str) -> None:
    """Background task: poll Unsiloed, index chunks into Moss, update job status."""
    try:
        raw_chunks = await asyncio.get_event_loop().run_in_executor(
            _executor, lambda: unsiloed.poll_job(job_id)
        )
        chunks = unsiloed.extract_chunks(raw_chunks, filename)
        await moss_service.add_document_chunks(chunks)
        _jobs[job_id]["status"] = "ready"
        logger.info("Indexed %d chunks for %s (%s)", len(chunks), filename, job_id)
    except Exception as e:
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["error"] = str(e)
        logger.exception("Background indexing failed for %s", job_id)
