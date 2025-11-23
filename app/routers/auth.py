from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.models.database import SessionLocal
from app.models.user import User
from werkzeug.security import generate_password_hash, check_password_hash

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# DB session dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})


@router.post("/signup")
def signup(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    # Check if user exists
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Username already exists"})

    # Hash password
    hashed_pw = generate_password_hash(password)

    # Save user
    new_user = User(username=username, password=hashed_pw)
    db.add(new_user)
    db.commit()

    return RedirectResponse(url="/login", status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    
    if not user or not check_password_hash(user.password, password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})

    # login success → set a cookie
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie("user_id", str(user.id))
    return response
