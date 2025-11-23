from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from app.models.database import Base, engine
from app.routers import auth, files  # <--- important
from app.routers.files import get_current_user_id

Base.metadata.create_all(bind=engine)

app = FastAPI()

templates = Jinja2Templates(directory="app/templates")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

# include our routers
app.include_router(auth.router)
app.include_router(files.router)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    user_id = get_current_user_id(request)
    if user_id:
        return RedirectResponse(url="/files", status_code=303)
    return RedirectResponse(url="/login", status_code=303)
