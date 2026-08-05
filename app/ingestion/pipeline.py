"""
Ingestion pipeline: the single path every source (PDF, GitHub, future
connectors) funnels through. Mirrors the architecture doc's Document
Processing Pipeline (Section 5.2), minus OCR (not in v1 scope).
"""
import uuid

from qdrant_client.http import models as qmodels
from sqlalchemy.orm import Session

from app.core import vector_store
from app.models.db_models import Document, Chunk
from app.services.chunking import chunk_text
from app.services.embedding import embed_texts


def ingest_document(
    db: Session,
    *,
    title: str,
    source_system: str,
    source_ref: str,
    raw_text: str,
    sensitivity: str = "internal",
) -> Document:
    """
    Persists a Document row, chunks the text, embeds the chunks,
    writes vectors to Qdrant, and writes pointer rows to Postgres.
    """
    vector_store.ensure_collection()

    document = Document(
        title=title,
        source_system=source_system,
        source_ref=source_ref,
        sensitivity=sensitivity,
        status="current",
    )
    db.add(document)
    db.flush()  # get document.id before we reference it

    chunks = chunk_text(raw_text, source_ref=source_ref)
    if not chunks:
        db.commit()
        return document

    vectors = embed_texts(chunks)

    points = []
    for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
        chunk_id = str(uuid.uuid4())
        points.append(
            qmodels.PointStruct(
                id=chunk_id,
                vector=vector,
                payload={
                    "document_id": document.id,
                    "document_title": document.title,
                    "chunk_index": idx,
                    "text": chunk,
                    "source_system": source_system,
                    "sensitivity": sensitivity,
                },
            )
        )
        db.add(
            Chunk(
                id=chunk_id,
                document_id=document.id,
                chunk_index=idx,
                text_preview=chunk[:200],
            )
        )

    vector_store.upsert_chunks(points)
    db.commit()
    return document
