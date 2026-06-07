"""Document upload and indexing endpoint."""

import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException, UploadFile, status
from supabase import create_client

from app.config import settings
from app.models.document import DocumentUploadResponse
from app.services import moss_service, unsiloed

router = APIRouter(prefix="/api/documents", tags=["documents"])
_executor = ThreadPoolExecutor(max_workers=4)


def _get_supabase():
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


@router.post("/", response_model=DocumentUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(file: UploadFile) -> DocumentUploadResponse:
    """Accept a document upload, parse via Unsiloed, and index into Moss."""
    content = await file.read()
    filename = file.filename or "document"
    doc_id = str(uuid.uuid4())

    try:
        job_id = unsiloed.submit_document(content, filename)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Unsiloed submission failed: {e}") from e

    # Parse and index in background — client polls for status separately
    import asyncio

    async def _process() -> None:
        try:
            raw_chunks = await asyncio.get_event_loop().run_in_executor(
                _executor, lambda: unsiloed.poll_job(job_id)
            )
            chunks = unsiloed.extract_chunks(raw_chunks, filename)
            await moss_service.add_document_chunks(chunks)
        except Exception:
            logger.exception("Background indexing failed for job %s", job_id)

    import logging
    logger = logging.getLogger(__name__)
    asyncio.create_task(_process())

    return DocumentUploadResponse(
        id=doc_id,
        name=filename,
        status="processing",
        unsiloed_job_id=job_id,
    )
