"""Unsiloed document parsing service (REST API wrapper)."""

import time
from typing import Any

import requests

from app.config import settings
from app.models.document import DocumentChunk


class UnsupportedFileError(Exception):
    """Raised when Unsiloed rejects the upload as an unsupported file type."""


def submit_document(file_bytes: bytes, filename: str) -> str:
    """Submit a document for async parsing. Returns the Unsiloed job_id.

    Raises UnsupportedFileError on 4xx responses (bad input — caller should
    return 400 to the client) and propagates other HTTP errors (treated as
    upstream 502 by the caller).
    """
    url = f"{settings.unsiloed_api_url}/parse"
    headers = {"accept": "application/json", "api-key": settings.unsiloed_api_key}
    files = {"file": (filename, file_bytes, "application/octet-stream")}
    data = {
        "use_high_resolution": "true",
        "layout_analysis": "smart_layout_detection",
        "ocr_strategy": "auto_detection",
        "merge_tables": "true",
    }
    resp = requests.post(url, headers=headers, files=files, data=data, timeout=60)
    if 400 <= resp.status_code < 500:
        try:
            detail = resp.json().get("message") or resp.text
        except Exception:
            detail = resp.text
        msg = detail.strip() or f"Unsiloed rejected the upload ({resp.status_code})"
        raise UnsupportedFileError(msg)
    resp.raise_for_status()
    return resp.json()["job_id"]


def poll_job(
    job_id: str, *, max_wait_s: int = 300, poll_interval_s: int = 5
) -> list[dict[str, Any]]:
    """Poll until the Unsiloed job succeeds. Returns list of raw chunk dicts."""
    url = f"{settings.unsiloed_api_url}/parse/{job_id}"
    headers = {"api-key": settings.unsiloed_api_key}
    deadline = time.monotonic() + max_wait_s
    while time.monotonic() < deadline:
        data = requests.get(url, headers=headers, timeout=30).json()
        status = data.get("status", "")
        if status == "Succeeded":
            return data.get("chunks", [])
        if status == "Failed":
            raise RuntimeError(f"Unsiloed job {job_id} failed: {data.get('message')}")
        time.sleep(poll_interval_s)
    raise TimeoutError(f"Unsiloed job {job_id} did not complete in {max_wait_s}s")


def extract_chunks(raw_chunks: list[dict[str, Any]], document_name: str) -> list[DocumentChunk]:
    """Convert raw Unsiloed response chunks into DocumentChunk objects."""
    result: list[DocumentChunk] = []
    for chunk in raw_chunks:
        for seg in chunk.get("segments", []):
            text = seg.get("content", "").strip()
            if not text:
                continue
            result.append(DocumentChunk(
                text=text,
                page_number=seg.get("page_number"),
                segment_type=seg.get("segment_type"),
                document_name=document_name,
            ))
    return result
