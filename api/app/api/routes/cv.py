from __future__ import annotations

import re
from pathlib import PurePosixPath
from urllib.parse import quote, unquote

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.db.dependencies import get_db
from app.models.cv import CvDocument
from app.models.user import User
from app.schemas.cv import CvRead, CvSuggestionsRead
from app.services import cv as cv_service
from app.services.cv import CvError

router = APIRouter(prefix="/profile/cv", tags=["cv"])

_EXTENSIONS = {"pdf": ".pdf", "docx": ".docx", "text": ".txt"}


def _safe_filename(raw: str | None, kind: str) -> str:
    name = PurePosixPath(unquote(raw or "").replace("\\", "/")).name
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")[:120]
    extension = _EXTENSIONS[kind]
    if not name:
        name = "cv"
    if not name.lower().endswith(extension):
        name = f"{name.rsplit('.', 1)[0] if '.' in name else name}{extension}"
    return name


def _read(document: CvDocument) -> CvRead:
    suggestions = cv_service.suggest_profile(document.extracted_text)
    return CvRead(
        filename=document.filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        uploaded_at=document.uploaded_at,
        text_characters=len(document.extracted_text),
        suggestions=CvSuggestionsRead(full_name=suggestions.full_name, skills=suggestions.skills),
    )


async def _read_limited_body(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.cv_max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "The file is too large.")
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > settings.cv_max_bytes:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "The file is too large.")
        chunks.append(chunk)
    return b"".join(chunks)


def _store(db: Session, user: User, filename_header: str | None, data: bytes) -> CvRead:
    try:
        if not data:
            raise CvError("The file is empty.")
        kind = cv_service.detect_kind(data)
        text = cv_service.extract_text(kind, data)
    except CvError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    if len(text.strip()) < 40:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "No readable text was found. Scanned images are not supported; upload a text-based PDF or a .docx.",
        )
    document = db.scalar(select(CvDocument).where(CvDocument.user_id == user.id))
    if document is None:
        document = CvDocument(user_id=user.id)
        db.add(document)
    document.filename = _safe_filename(filename_header, kind)
    document.content_type = cv_service.content_type_for(kind)
    document.size_bytes = len(data)
    document.data = data
    document.extracted_text = text
    db.commit()
    db.refresh(document)
    return _read(document)


@router.put("", response_model=CvRead)
async def upload_cv(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CvRead:
    """Upload a CV as the raw request body. The original file name goes in X-Filename."""
    data = await _read_limited_body(request)
    return await run_in_threadpool(_store, db, user, request.headers.get("x-filename"), data)


@router.get("", response_model=CvRead | None)
def read_cv(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> CvRead | None:
    document = db.scalar(select(CvDocument).where(CvDocument.user_id == user.id))
    return _read(document) if document else None


@router.get("/download")
def download_cv(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Response:
    document = db.scalar(select(CvDocument).where(CvDocument.user_id == user.id))
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No CV uploaded")
    return Response(
        content=document.data,
        media_type=document.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(document.filename)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_cv(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Response:
    document = db.scalar(select(CvDocument).where(CvDocument.user_id == user.id))
    if document is not None:
        db.delete(document)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
