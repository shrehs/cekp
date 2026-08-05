"""
Qdrant client wrapper. Owns collection creation and the raw
upsert/search calls used by the retrieval layer.
"""
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import settings

_client: QdrantClient | None = None


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    return _client


def ensure_collection() -> None:
    """Create the chunks collection if it doesn't already exist. Idempotent."""
    client = get_client()
    existing = [c.name for c in client.get_collections().collections]
    if settings.qdrant_collection in existing:
        return

    client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=qmodels.VectorParams(
            size=settings.embedding_dim,
            distance=qmodels.Distance.COSINE,
        ),
    )


def upsert_chunks(points: list[qmodels.PointStruct]) -> None:
    client = get_client()
    client.upsert(collection_name=settings.qdrant_collection, points=points)


def vector_search(query_vector: list[float], top_k: int = 5, query_filter: qmodels.Filter | None = None):
    client = get_client()
    return client.search(
        collection_name=settings.qdrant_collection,
        query_vector=query_vector,
        limit=top_k,
        query_filter=query_filter,
    )
