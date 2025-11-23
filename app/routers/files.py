from pathlib import Path
import time

from fastapi import APIRouter, Request, Depends, UploadFile, File as FastAPIFile, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.models.database import SessionLocal
from app.models.file import FileMeta

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# where files will be stored locally (later we can move this to S3)
BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(exist_ok=True)


# --- DB session dependency (same pattern as in auth.py) ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- helper: get current logged in user id from cookie ---
def get_current_user_id(request: Request) -> int | None:
    user_id = request.cookies.get("user_id")
    if not user_id:
        return None
    try:
        return int(user_id)
    except ValueError:
        return None


# --- show user's files (drive/dashboard) ---
@router.get("/files", response_class=HTMLResponse)
def list_files(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    files = db.query(FileMeta).filter(FileMeta.owner_id == user_id).all()

    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "files": files,
        },
    )


# --- upload a new file ---
@router.post("/upload")
async def upload_file(
    request: Request,
    upload: UploadFile = FastAPIFile(...),
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    # folder per user
    user_folder = STORAGE_DIR / str(user_id)
    user_folder.mkdir(parents=True, exist_ok=True)

    stored_name = f"{int(time.time())}_{upload.filename}"
    file_path = user_folder / stored_name

    content = await upload.read()
    with file_path.open("wb") as f:
        f.write(content)

    meta = FileMeta(
        owner_id=user_id,
        stored_name=stored_name,
        original_name=upload.filename,
        path=str(file_path),  # <-- THIS WAS MISSING
        size=len(content),
    )
    db.add(meta)
    db.commit()

    return RedirectResponse(url="/files", status_code=303)


# --- download a file ---
@router.get("/download/{file_id}")
def download_file(
    file_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    file = (
        db.query(FileMeta)
        .filter(FileMeta.id == file_id, FileMeta.owner_id == user_id)
        .first()
    )
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = STORAGE_DIR / str(user_id) / file.stored_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")

    return FileResponse(
        path=file_path,
        media_type=file.content_type or "application/octet-stream",
        filename=file.original_name,
    )


# --- delete a file ---
@router.post("/delete/{file_id}")
def delete_file(
    file_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    file = (
        db.query(FileMeta)
        .filter(FileMeta.id == file_id, FileMeta.owner_id == user_id)
        .first()
    )
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = STORAGE_DIR / str(user_id) / file.stored_name
    if file_path.exists():
        file_path.unlink()

    db.delete(file)
    db.commit()

    return RedirectResponse(url="/files", status_code=303)
