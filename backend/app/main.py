from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, Base
from .routers import analytics, upload, campaigns

# Create all tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Campaign Analysis Dashboard API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router, prefix="/api/upload", tags=["upload"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(campaigns.router, prefix="/api/campaigns", tags=["campaigns"])

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

# Serve static files from the frontend directory
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend")

@app.get("/")
def read_root():
    return FileResponse(os.path.join(frontend_dir, "index.html"))

app.mount("/", StaticFiles(directory=frontend_dir), name="static")
