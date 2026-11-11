"""Embed Infovinci blog posts into a local ChromaDB collection.

This is adapted from the `doc-embedder` Chroma pattern, but uses the local
Infovinci SQLite blog rows instead of scraping external web pages.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils import embedding_functions
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import select

from infovinci_serve.db import SessionLocal, init_db, seed_from_json_if_empty
from infovinci_serve.models import BlogPostRow

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DEFAULT_VECTOR_DB_PATH = str(Path.cwd() / "data" / "infovinci_chroma")
DEFAULT_COLLECTION_NAME = "infovinci_blog_posts"
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L12-v2"
DEFAULT_RETRIEVAL_COUNT = 10

_collection_cache: Any = None


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using %s", name, raw, default)
        return default


def _rich_doc_blocks(rich_doc_json: str | None) -> list[dict[str, Any]]:
    if not rich_doc_json:
        return []
    try:
        rich_doc = json.loads(rich_doc_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(rich_doc, dict):
        return []
    blocks = rich_doc.get("contents") or []
    return [block for block in blocks if isinstance(block, dict)]


def _block_to_text(block: dict[str, Any]) -> str:
    block_type = str(block.get("type", "")).strip()
    if block_type in {"header", "subHeader", "text"}:
        return str(block.get("text", "")).strip()
    if block_type == "code":
        code = str(block.get("code", "")).strip()
        return f"Code:\n{code}" if code else ""
    if block_type == "image":
        src = str(block.get("src", "")).strip()
        return f"Image: {src}" if src else ""
    if block_type in {"reference", "link"}:
        text = str(block.get("text", "")).strip()
        href = str(block.get("href", "")).strip()
        return f"{text}: {href}".strip(": ")
    return ""


def post_to_document(row: BlogPostRow) -> Document:
    """Flatten one blog row into a LangChain document for chunking."""
    parts = [
        f"Title: {row.title}",
        f"Slug: {row.slug}",
        f"Category: {row.category}",
        f"Date: {row.date_iso}",
        f"Summary: {row.summary}",
    ]
    if row.body:
        parts.append(row.body)

    parts.extend(text for block in _rich_doc_blocks(row.rich_doc_json) if (text := _block_to_text(block)))

    return Document(
        page_content="\n\n".join(parts),
        metadata={
            "post_id": row.id,
            "slug": row.slug,
            "title": row.title,
            "category": row.category,
            "dateISO": row.date_iso,
            "url": f"/post/{row.id}",
        },
    )


def load_blog_documents() -> list[Document]:
    init_db()
    seed_from_json_if_empty()

    with SessionLocal() as db:
        rows = db.scalars(select(BlogPostRow).order_by(BlogPostRow.date_iso.desc())).all()

    return [post_to_document(row) for row in rows]


def get_collection():
    global _collection_cache
    if _collection_cache is not None:
        return _collection_cache

    db_path = os.environ.get("INFOVINCI_VECTOR_DB_PATH", DEFAULT_VECTOR_DB_PATH)
    collection_name = os.environ.get("INFOVINCI_VECTOR_COLLECTION", DEFAULT_COLLECTION_NAME)
    embedding_model = os.environ.get("INFOVINCI_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)

    Path(db_path).expanduser().resolve().mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=db_path)
    embed_func = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=embedding_model,
    )
    _collection_cache = client.get_or_create_collection(collection_name, embedding_function=embed_func)
    return _collection_cache


def clear_collection(collection) -> None:
    existing = collection.get()
    ids = existing.get("ids") or []
    if ids:
        logger.info("Deleting %s existing vector chunks", len(ids))
        collection.delete(ids=ids)


def embed_blog_posts(reset: bool = True) -> int:
    chunk_size = _env_int("INFOVINCI_CHUNK_SIZE", 700)
    chunk_overlap = _env_int("INFOVINCI_CHUNK_OVERLAP", 80)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    collection = get_collection()
    if reset:
        clear_collection(collection)

    documents = load_blog_documents()
    chunks = splitter.split_documents(documents)

    ids: list[str] = []
    metadatas: list[dict[str, Any]] = []
    texts: list[str] = []
    for index, chunk in enumerate(chunks):
        slug = str(chunk.metadata["slug"])
        ids.append(f"{slug}_{index}")
        metadatas.append({**chunk.metadata, "chunk_index": index})
        texts.append(chunk.page_content)

    if texts:
        collection.add(documents=texts, metadatas=metadatas, ids=ids)

    logger.info(
        "Embedded %s posts into %s chunks in collection %r",
        len(documents),
        len(texts),
        collection.name,
    )
    return len(texts)


def _rag_disabled() -> bool:
    return os.environ.get("INFOVINCI_SKIP_RAG", "").lower() in {"1", "true", "yes"}


def retrieve_blog_context(query: str, n_results: int | None = None) -> str:
    """Return a compact context block from the blog vector index."""
    if _rag_disabled():
        return ""
    search = query.strip()
    if not search:
        return ""

    result_count = n_results or _env_int("INFOVINCI_RETRIEVAL_COUNT", DEFAULT_RETRIEVAL_COUNT)
    try:
        collection = get_collection()
        results = collection.query(query_texts=[search], n_results=result_count)
    except Exception as exc:
        logger.warning("Blog vector retrieval failed: %s", exc)
        return ""

    documents = (results.get("documents") or [[]])[0]
    metadatas = (results.get("metadatas") or [[]])[0]
    if not documents:
        logger.info("RAG: no blog chunks matched query=%r", search[:80])
        return ""

    logger.info("RAG: matched %s blog chunks for query=%r", len(documents), search[:80])
    context_parts: list[str] = []
    for index, document in enumerate(documents):
        metadata = metadatas[index] if index < len(metadatas) and isinstance(metadatas[index], dict) else {}
        title = str(metadata.get("title") or "Untitled")
        slug = str(metadata.get("slug") or "")
        url = str(metadata.get("url") or "")
        context_parts.append(
            "\n".join(
                [
                    f"Source {index + 1}: {title}",
                    f"Slug: {slug}",
                    f"URL: {url}",
                    str(document).strip(),
                ],
            ),
        )

    return "\n\n---\n\n".join(context_parts)


def main() -> None:
    reset = os.environ.get("INFOVINCI_VECTOR_RESET", "1").lower() not in {"0", "false", "no"}
    embed_blog_posts(reset=reset)


if __name__ == "__main__":
    main()
