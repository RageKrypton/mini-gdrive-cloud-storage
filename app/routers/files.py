# app/routers/files.py

import os
import uuid
from typing import List

from fastapi import (
    APIRouter,
    Request,
    Depends,
    UploadFile,
    File,
)
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.models.database import SessionLocal
from app.models.file import FileMeta

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Where uploaded files are stored on disk
UPLOAD_DIR = "user_files"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ---------- DB DEPENDENCY ----------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------- HELPER: CURRENT USER ----------

def get_current_user_id(request: Request) -> int | None:
    user_id = request.cookies.get("user_id")
    if not user_id:
        return None
    try:
        return int(user_id)
    except ValueError:
        return None


# ---------- ROUTES ----------

@router.get("/files", response_class=HTMLResponse)
def list_files(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    files: List[FileMeta] = (
        db.query(FileMeta)
        .filter(FileMeta.owner_id == user_id)
        .order_by(FileMeta.uploaded_at.desc())
        .all()
    )

    return templates.TemplateResponse(
        "files.html",
        {
            "request": request,
            "files": files,
        },
    )


@router.post("/upload")
async def upload_file(
    request: Request,
    upload: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    # Read file into memory
    content = await upload.read()

    # Generate a safe unique name for storing on disk
    stored_name = uuid.uuid4().hex
    file_path = os.path.join(UPLOAD_DIR, stored_name)

    # Save to disk
    with open(file_path, "wb") as f:
        f.write(content)

    # Save metadata in DB
    file_meta = FileMeta(
        original_name=upload.filename,
        stored_name=stored_name,
        owner_id=user_id,
        size=len(content),
        content_type=upload.content_type,
    )

    db.add(file_meta)
    db.commit()
    db.refresh(file_meta)

    return RedirectResponse(url="/files", status_code=303)


@router.get("/download/{file_id}")
def download_file(
    file_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    file = db.query(FileMeta).filter(
        FileMeta.id == file_id,
        FileMeta.owner_id == user_id,
    ).first()

    if not file:
        # Just send back to /files for now; later we can show proper error
        return RedirectResponse(url="/files", status_code=303)

    file_path = os.path.join(UPLOAD_DIR, file.stored_name)
    return FileResponse(
        file_path,
        media_type=file.content_type or "application/octet-stream",
        filename=file.original_name,
    )


@router.post("/delete/{file_id}")
def delete_file(
    file_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    file = db.query(FileMeta).filter(
        FileMeta.id == file_id,
        FileMeta.owner_id == user_id,
    ).first()

    if not file:
        return RedirectResponse(url="/files", status_code=303)

    file_path = os.path.join(UPLOAD_DIR, file.stored_name)

    # Remove metadata from DB
    db.delete(file)
    db.commit()

    # Remove file from disk (ignore if already gone)
    if os.path.exists(file_path):
        os.remove(file_path)

    return RedirectResponse(url="/files", status_code=303)
