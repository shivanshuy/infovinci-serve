"""GET /posts (paginated summaries) and GET /post/{post_id} (full body)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from infovinci_serve.db import get_db
from infovinci_serve.models import BlogPostRow
from infovinci_serve.schemas_blog import PaginatedPosts, PostFull, row_to_full, row_to_summary

router = APIRouter(tags=["blog"])


@router.get("/posts", response_model=PaginatedPosts)
def list_posts(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50, alias="pageSize"),
    q: str | None = Query(None, description="Search post titles."),
    db: Session = Depends(get_db),
):
    page_size = min(50, max(1, page_size))
    offset = (page - 1) * page_size

    stmt = select(BlogPostRow)
    count_stmt = select(func.count()).select_from(BlogPostRow)
    search = (q or "").strip()
    if search:
        condition = BlogPostRow.title.ilike(f"%{search}%")
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt
        .order_by(BlogPostRow.date_iso.desc())
        .offset(offset)
        .limit(page_size),
    ).all()

    return PaginatedPosts(
        items=[row_to_summary(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/post/{post_id}", response_model=PostFull)
def get_post(post_id: UUID, db: Session = Depends(get_db)):
    row = db.scalar(select(BlogPostRow).where(BlogPostRow.id == str(post_id)))
    if row is None:
        raise HTTPException(status_code=404, detail="post_not_found")
    return row_to_full(row)
