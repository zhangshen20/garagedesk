"""Job card photo endpoints: the careful reader in front of the owner app's pipeline.

  POST /api/jobcards/scan                 {image_b64, mime} like /api/owner/photo -> the same
                                          draft response, plus "jobcard" (per-field confidence)
  POST /api/jobcards/samples/{name}/scan  same, using a bundled sample card (demo, no phone)
  GET  /api/jobcards/samples              names of the bundled sample cards
  GET  /api/jobcards/samples/{name}.jpg   a sample card image
  GET  /api/jobcards/photos/{photo_id}.jpg  the stored photo behind a draft"""

from __future__ import annotations

import base64
import binascii
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session

from ..db import get_session
from .jobcard import photos_dir, scan_jobcard
from .reader import SAMPLES_DIR, sample_names
from .to_job import to_owner_draft

router = APIRouter(prefix="/api/jobcards", tags=["jobcards"])

MAX_BYTES = 20 * 1024 * 1024


def _scan(s: Session, data: bytes) -> dict[str, Any]:
    try:
        card = scan_jobcard(s, data)
    except ValueError as e:
        raise HTTPException(415, str(e)) from e
    out = to_owner_draft(s, card)
    s.commit()
    return out


class PhotoIn(BaseModel):
    image_b64: str
    mime: str = "image/jpeg"


@router.post("/scan")
def scan(body: PhotoIn, s: Session = Depends(get_session)) -> dict[str, Any]:
    b64 = body.image_b64.split(",", 1)[-1]  # a data: URL is fine too
    if len(b64) > MAX_BYTES * 4 // 3:
        raise HTTPException(413, "That photo is too big. Take it again at normal size.")
    try:
        data = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as e:
        raise HTTPException(400, "The photo didn't come through. Try again.") from e
    if not data:
        raise HTTPException(400, "The photo was empty.")
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


@router.post("/samples/{name}/scan")
def scan_sample(name: str, s: Session = Depends(get_session)) -> dict[str, Any]:
    return _scan(s, _sample_path(name).read_bytes())


@router.get("/photos/{photo_id}.jpg")
def photo(photo_id: str) -> FileResponse:
    if not re.fullmatch(r"[0-9a-f]{16}", photo_id):
        raise HTTPException(404, "No such photo")
    p = photos_dir() / f"{photo_id}.jpg"
    if not p.is_file():
        raise HTTPException(404, "No such photo")
    return FileResponse(p, media_type="image/jpeg")
