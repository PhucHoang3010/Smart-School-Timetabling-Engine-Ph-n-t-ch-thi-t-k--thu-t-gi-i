from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .api.v1.optimization_router import router
from .api.v1.auth_router import router as auth_router
from .core.auth import seed_demo_users
from .core.database import Base, engine_db
from .models import *

app = FastAPI(title="Smart School Timetabling API", version="5.0.0")
app.include_router(router)
app.include_router(auth_router)
Base.metadata.create_all(bind=engine_db)
seed_demo_users()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
app.mount("/", StaticFiles(directory=PROJECT_ROOT, html=True), name="frontend")
