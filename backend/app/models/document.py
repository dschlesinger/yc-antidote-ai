from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    """Response returned after a document is submitted for processing."""
    id: str
    name: str
    status: str  # "processing" | "ready" | "error"
    unsiloed_job_id: str | None = None


class DocumentChunk(BaseModel):
    """A single text chunk extracted from a parsed document."""
    text: str
    page_number: int | None = None
    segment_type: str | None = None
    document_name: str = ""
