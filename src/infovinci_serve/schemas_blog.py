"""Pydantic models (camelCase JSON for TS)."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

_JSON = ConfigDict(ser_json_by_alias=True)


class PostSummary(BaseModel):
    model_config = _JSON

    id: UUID
    slug: str
    title: str
    date_iso: str = Field(serialization_alias="dateISO")
    category: str
    summary: str
    image_variant: int = Field(serialization_alias="imageVariant", ge=1, le=9)


class PaginatedPosts(BaseModel):
    model_config = _JSON

    items: list[PostSummary]
    total: int
    page: int
    page_size: int = Field(serialization_alias="pageSize", ge=1)


class PostFull(BaseModel):
    model_config = _JSON

    id: UUID
    slug: str
    title: str
    date_iso: str = Field(serialization_alias="dateISO")
    category: str
    summary: str
    body: str
    image_variant: int = Field(serialization_alias="imageVariant", ge=1, le=9)
    rich_doc: dict[str, Any] | list[Any] | None = Field(default=None, serialization_alias="richDoc")


def row_to_summary(row) -> PostSummary:
    return PostSummary(
        id=UUID(row.id),
        slug=row.slug,
        title=row.title,
        date_iso=row.date_iso,
        category=row.category,
        summary=row.summary,
        image_variant=row.image_variant,
    )


def row_to_full(row) -> PostFull:
    m = json.loads(row.rich_doc_json) if row.rich_doc_json else None
    return PostFull(
        id=UUID(row.id),
        slug=row.slug,
        title=row.title,
        date_iso=row.date_iso,
        category=row.category,
        summary=row.summary,
        body=row.body,
        image_variant=row.image_variant,
        rich_doc=m,
    )
