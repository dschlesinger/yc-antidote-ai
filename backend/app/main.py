"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import documents, session
from app.services import moss_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    await moss_service.ensure_index()
    yield


app = FastAPI(title="Antidote AI", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(session.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
