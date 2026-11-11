"""FastAPI: blog REST (posts list + post detail) and /health."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from infovinci_serve.blog_routes import router as blog_router
from infovinci_serve.db import init_db, seed_from_json_if_empty


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    seed_from_json_if_empty()
    yield


app = FastAPI(title="infovinci-serve", version="0.3.0", lifespan=lifespan)

_cors_origins = os.environ.get(
    "CORS_ALLOW_ORIGINS",
    "http://127.0.0.1:5173,http://localhost:5173",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(blog_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "infovinci-serve"}


def main() -> None:
    host = os.environ.get("CHAT_BFF_HOST", "127.0.0.1")
    port = int(os.environ.get("CHAT_BFF_PORT", "8080"))
    uvicorn.run(
        "infovinci_serve.main:app",
        host=host,
        port=port,
        reload=os.environ.get("CHAT_BFF_RELOAD", "").lower() in ("1", "true", "yes"),
    )
