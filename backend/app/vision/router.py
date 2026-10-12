"""Job card photo endpoints.

  POST /api/jobcards/scan                 multipart "photo" (iPhone camera upload) -> JobDraft
  POST /api/jobcards/samples/{name}/scan  same, using a bundled sample card (demo, no phone)
  GET  /api/jobcards/samples              names of the bundled sample cards
  GET  /api/jobcards/samples/{name}.jpg   a sample card image
  GET  /api/jobcards/photos/{photo_id}.jpg  the stored photo behind a draft"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session

from ..db import get_session
from .jobcard import photos_dir, scan_jobcard
from .reader import SAMPLES_DIR, sample_names
from .schema import JobDraft

router = APIRouter(prefix="/api/jobcards", tags=["jobcards"])

MAX_BYTES = 20 * 1024 * 1024


def _scan(s: Session, data: bytes) -> JobDraft:
    try:
        draft = scan_jobcard(s, data)
    except ValueError as e:
        raise HTTPException(415, str(e)) from e
    s.commit()
    return draft


@router.post("/scan", response_model=JobDraft)
async def scan(photo: UploadFile = File(...), s: Session = Depends(get_session)) -> JobDraft:
    data = await photo.read()
    if not data:
        raise HTTPException(400, "The photo was empty.")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "That photo is too big. Take it again at normal size.")
    return _scan(s, data)


@router.get("/samples")
def samples() -> dict[str, list[str]]:
    return {"samples": sample_names()}


def _sample_path(name: str):
    if name not in sample_names():
        raise HTTPException(404, "No such sample card")
    return SAMPLES_DIR / f"{name}.jpg"


@router.get("/samples/{name}.jpg")
def sample_image(name: str) -> FileResponse:
    return FileResponse(_sample_path(name), media_type="image/jpeg")


@router.post("/samples/{name}/scan", response_model=JobDraft)
def scan_sample(name: str, s: Session = Depends(get_session)) -> JobDraft:
    return _scan(s, _sample_path(name).read_bytes())


@router.get("/photos/{photo_id}.jpg")
def photo(photo_id: str) -> FileResponse:
    if not re.fullmatch(r"[0-9a-f]{16}", photo_id):
        raise HTTPException(404, "No such photo")
    p = photos_dir() / f"{photo_id}.jpg"
    if not p.is_file():
        raise HTTPException(404, "No such photo")
    return FileResponse(p, media_type="image/jpeg")
