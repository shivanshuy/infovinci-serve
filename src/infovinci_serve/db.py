"""SQLite engine, sessions, init + optional JSON seed."""

from __future__ import annotations

import json
import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

INFOVINCI_SQLITE_PATH = os.environ.get(
    "INFOVINCI_SQLITE_PATH",
    str(Path.cwd() / "data" / "infovinci.db"),
)


class Base(DeclarativeBase):
    pass


def _ensure_parent_dir(path: str) -> None:
    Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


_engine = create_engine(
    f"sqlite:///{Path(INFOVINCI_SQLITE_PATH).expanduser().resolve()}",
    connect_args={"check_same_thread": False},
    echo=os.environ.get("SQLALCHEMY_ECHO", "").lower() in ("1", "true", "yes"),
)
SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False, class_=Session)


def init_db() -> None:
    import infovinci_serve.models  # noqa: F401 — register BlogPostRow with Base.metadata

    _ensure_parent_dir(INFOVINCI_SQLITE_PATH)
    Base.metadata.create_all(bind=_engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def seed_from_json_if_empty() -> None:
    """Insert rows from INFOVINCI_SEED_JSON when blog_posts is empty."""
    from infovinci_serve.models import BlogPostRow  # noqa: PLC0415

    seed_path = Path(
        os.environ.get("INFOVINCI_SEED_JSON", str(Path.cwd() / "data" / "seed_posts.json")),
    ).expanduser()

    with SessionLocal() as db:
        total = db.scalar(select(func.count()).select_from(BlogPostRow)) or 0
        if total > 0:
            return
        if not seed_path.is_file():
            return
        raw = json.loads(seed_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return
        for row in raw:
            if not isinstance(row, dict) or "id" not in row or "slug" not in row:
                continue
            rich = row.get("richDoc")
            rich_s = json.dumps(rich) if rich is not None else None
            db.add(
                BlogPostRow(
                    id=str(row["id"]),
                    slug=str(row["slug"]),
                    title=str(row["title"]),
                    category=str(row.get("category", "Article")),
                    date_iso=str(row["dateISO"]),
                    summary=str(row.get("summary", "")),
                    body=str(row.get("body", "")),
                    image_variant=int(row.get("imageVariant", 1)),
                    rich_doc_json=rich_s,
                ),
            )
        db.commit()
