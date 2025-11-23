from pathlib import Path
import time
import io
from datetime import datetime, timedelta
from sqlalchemy import func

import boto3
from fastapi import APIRouter, Request, Depends, UploadFile, File as FastAPIFile, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.models.database import SessionLocal
from app.models.file import FileMeta
from app.core.config import get_settings

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

settings = get_settings()

s3 = boto3.client(
    "s3",
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
    region_name=settings.aws_region,
)

BUCKET_NAME = settings.aws_s3_bucket_name

# (Optional) You can keep STORAGE_DIR if you still want local storage,
# but for now S3 is our main storage.
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
def list_files(request: Request, db: Session = Depends(get_db), search: str = None, error: str = None):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    # Get all user's files (for stats - no search filter)
    all_files_query = db.query(FileMeta).filter(FileMeta.owner_id == user_id)
    
    # Calculate statistics (only when not searching)
    stats = {}
    if not search or not search.strip():
        # Total files count
        total_files = all_files_query.count()
        
        # Total storage used (sum of all file sizes)
        total_storage_result = all_files_query.with_entities(func.sum(FileMeta.size)).scalar()
        total_storage = total_storage_result if total_storage_result else 0
        
        # Files uploaded in last 7 days
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        recent_files_count = all_files_query.filter(FileMeta.uploaded_at >= seven_days_ago).count()
        
        stats = {
            "total_files": total_files,
            "total_storage": total_storage,
            "recent_files": recent_files_count,
        }

    # Get filtered files (with search if provided)
    query = all_files_query
    if search and search.strip():
        search_term = f"%{search.strip().lower()}%"
        query = query.filter(FileMeta.original_name.ilike(search_term))
    
    files = query.order_by(FileMeta.uploaded_at.desc()).all()

    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "files": files,
            "search_query": search or "",
            "stats": stats,
            "error": error,
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

    # Create a unique S3 key, grouped per user
    key = f"{user_id}/{int(time.time())}_{upload.filename}"

    # Read file content
    content = await upload.read()

    # Upload to S3
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=content,
        ContentType=upload.content_type or "application/octet-stream",
    )

    # Save metadata in DB
    meta = FileMeta(
        owner_id=user_id,
        stored_name=key,          # we will use this as the S3 key
        original_name=upload.filename,
        size=len(content),
        path=key,                 # if your 'path' column is NOT NULL
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

    # Fetch object from S3
    try:
        obj = s3.get_object(Bucket=BUCKET_NAME, Key=file.stored_name)
    except Exception:
        raise HTTPException(status_code=404, detail="File missing in cloud")

    file_bytes = obj["Body"].read()
    content_type = obj.get("ContentType") or "application/octet-stream"

    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{file.original_name}"'
        },
    )




# --- rename a file ---
@router.post("/rename/{file_id}")
async def rename_file(
    file_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    # Get form data
    form_data = await request.form()
    new_name = form_data.get("new_name", "").strip()
    
    if not new_name:
        # Redirect back with error message in query param
        from urllib.parse import quote
        return RedirectResponse(url=f"/files?error={quote('Invalid filename')}", status_code=303)

    file = (
        db.query(FileMeta)
        .filter(FileMeta.id == file_id, FileMeta.owner_id == user_id)
        .first()
    )
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    # Update the original_name in database (stored_name on S3 stays the same)
    file.original_name = new_name
    db.commit()

    return RedirectResponse(url="/files", status_code=303)


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

    # Delete from S3
    try:
        s3.delete_object(Bucket=BUCKET_NAME, Key=file.stored_name)
    except Exception:
        # we can log this, but still attempt to delete DB record
        pass

    db.delete(file)
    db.commit()

    return RedirectResponse(url="/files", status_code=303)
