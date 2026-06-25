"""File upload endpoints for web chat and agents."""

import logging
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/uploads", tags=["uploads"])
logger = logging.getLogger(__name__)


@router.post("")
async def upload_files(
    session_id: str = Form(...),
    file: List[UploadFile] = File(...),
):
    from ..uploads import save_upload

    if not session_id.strip():
        raise HTTPException(status_code=400, detail="session_id is required")
    if not file:
        raise HTTPException(status_code=400, detail="No files provided")

    results = []
    errors = []
    for f in file:
        try:
            meta = await save_upload(session_id, f)
            results.append(meta.to_dict())
        except ValueError as e:
            errors.append(f"{f.filename or '?'}: {e}")
        except Exception as e:
            logger.error(f"upload failed: {e}")
            errors.append(f"{f.filename or '?'}: upload failed")

    if not results and errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    return {"uploads": results, "errors": errors}


@router.get("")
async def list_session_uploads(session_id: str):
    from ..uploads import list_uploads

    if not session_id.strip():
        raise HTTPException(status_code=400, detail="session_id is required")
    return [m.to_dict() for m in list_uploads(session_id)]


@router.get("/{upload_id}")
async def get_upload_file(upload_id: str, session_id: str):
    from ..uploads import get_upload

    meta = get_upload(session_id, upload_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    path = meta.path
    if not path or not __import__("os").path.isfile(path):
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponse(path, media_type=meta.mime, filename=meta.filename)


@router.delete("/{upload_id}")
async def remove_upload(upload_id: str, session_id: str):
    from ..uploads import delete_upload

    if not delete_upload(session_id, upload_id):
        raise HTTPException(status_code=404, detail="Upload not found")
    return {"status": "deleted"}
