"""
Embedding service. Loads the sentence-transformers model once (singleton)
since model load is the expensive part -- every ingestion/query call
should reuse this instance.
"""
from sentence_transformers import SentenceTransformer

from app.core.config import settings

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(settings.embedding_model)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = get_model()
    vectors = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
    return vectors.tolist()


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
