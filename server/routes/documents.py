"""The signed-in user's private document library."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from config.settings import get_settings
from server.db import DocumentRecord, User, get_db, new_id
from server.schemas import DocumentOut
from server.security import verified_user
from server.storage import documents_dir, safe_display_name
from src.ingestion.loader import SUPPORTED_EXTENSIONS
from src.ingestion.vector_store import get_index

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])


def _list(db: Session, user: User) -> list[DocumentOut]:
    docs = (
        db.query(DocumentRecord)
        .filter(DocumentRecord.user_id == user.id)
        .order_by(DocumentRecord.created_at.desc())
        .all()
    )
    return [DocumentOut.of(d) for d in docs]


@router.get("", response_model=list[DocumentOut])
def list_documents(user: User = Depends(verified_user), db: Session = Depends(get_db)) -> list[DocumentOut]:
    return _list(db, user)


def _store_and_index(db: Session, user: User, filename: str, data: bytes) -> DocumentRecord:
    ext = Path(filename).suffix.lower()
    doc_id = new_id()
    stored = documents_dir(user.id) / f"{doc_id}{ext}"
    stored.write_bytes(data)
    try:
        chunks = get_index().index_file(stored, owner=user.id, doc_id=doc_id, display_name=filename)
    except Exception:
        stored.unlink(missing_ok=True)
        logger.exception("Indexing failed for %s", filename)
        raise HTTPException(422, {"code": "unreadable", "message": f"We couldn't read {filename}."}) from None
    if chunks == 0:
        stored.unlink(missing_ok=True)
        raise HTTPException(
            422,
            {
                "code": "no_text",
                "message": f"{filename} has no readable text. Scanned PDFs need to be converted first.",
            },
        )
    record = DocumentRecord(
        id=doc_id,
        user_id=user.id,
        filename=filename,
        stored_name=stored.name,
        size_bytes=len(data),
        chunks=chunks,
    )
    db.add(record)
    db.commit()
    return record


@router.post("", response_model=DocumentOut, status_code=201)
def upload_document(
    file: UploadFile, user: User = Depends(verified_user), db: Session = Depends(get_db)
) -> DocumentOut:
    """Upload one PDF, TXT or Markdown file (one request per file keeps progress reporting simple)."""
    filename = safe_display_name(file.filename or "document")
    if Path(filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise HTTPException(415, {"code": "bad_type", "message": "Please upload a PDF, TXT or Markdown file."})
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            413, {"code": "too_large", "message": f"Files can be up to {get_settings().max_upload_mb} MB."}
        )
    if not data:
        raise HTTPException(422, {"code": "empty", "message": f"{filename} is empty."})
    return DocumentOut.of(_store_and_index(db, user, filename, data))



@router.delete("/{doc_id}", status_code=204)
def delete_document(doc_id: str, user: User = Depends(verified_user), db: Session = Depends(get_db)) -> Response:
    record = db.get(DocumentRecord, doc_id)
    if record is None or record.user_id != user.id:
        raise HTTPException(404, {"code": "not_found", "message": "That document no longer exists."})
    get_index().delete_document(doc_id, owner=user.id)
    (documents_dir(user.id) / record.stored_name).unlink(missing_ok=True)
    db.delete(record)
    db.commit()
    return Response(status_code=204)
