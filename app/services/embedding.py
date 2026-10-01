"""
Embedding service. Loads the sentence-transformers model once (singleton)
since model load is the expensive part -- every ingestion/query call
should reuse this instance.
"""
from app.core.config import settings

_model = None


def get_model():
    from sentence_transformers import SentenceTransformer

    global _model
    if _model is None:
        _model = SentenceTransformer(settings.embedding_model)
    return _model


from typing import cast
import numpy as np

def embed_texts(texts: list[str]) -> list[list[float]]:
    model = get_model()

    vectors = cast(
        np.ndarray,
        model.encode(
            texts,
            show_progress_bar=False,
            normalize_embeddings=True,
            convert_to_numpy=True,
        ),
    )

    return vectors.tolist()


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
