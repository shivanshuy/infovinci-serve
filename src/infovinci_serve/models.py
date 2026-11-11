"""Blog post rows: UUID primary key + slug."""

from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from infovinci_serve.db import Base


class BlogPostRow(Base):
    __tablename__ = "blog_posts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(String(192), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False, default="Article")
    date_iso: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    image_variant: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    rich_doc_json: Mapped[str | None] = mapped_column(Text, nullable=True)
