from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from app.models.database import Base, engine
import app.models.user
import app.models.file

Base.metadata.create_all(bind=engine)

app = FastAPI()

# Where our HTML files will live
templates = Jinja2Templates(directory="app/templates")

# Static folder for CSS, JS, images, etc.
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

from app.routers import auth
app.include_router(auth.router)
