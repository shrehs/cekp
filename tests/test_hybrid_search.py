from types import SimpleNamespace

from app.services import hybrid_search


def _hit(score: float, text: str = "evidence"):
    return SimpleNamespace(
        id="chunk-1",
        score=score,
        payload={
            "document_id": "doc-1",
            "document_title": "Example",
            "text": text,
            "source_system": "test",
        },
    )


def test_vector_evidence_floor_rejects_off_topic_candidates(monkeypatch):
    monkeypatch.setattr(hybrid_search, "embed_query", lambda _: [0.1])
    monkeypatch.setattr(
        hybrid_search.vector_store,
        "vector_search",
        lambda *_args, **_kwargs: [_hit(0.29)],
    )

    assert hybrid_search.hybrid_search("unrelated question") == []


def test_hybrid_score_preserves_vector_and_bm25_components(monkeypatch):
    monkeypatch.setattr(hybrid_search, "embed_query", lambda _: [0.1])
    monkeypatch.setattr(
        hybrid_search.vector_store,
        "vector_search",
        lambda *_args, **_kwargs: [_hit(0.9, "auth service dependency")],
    )

    result = hybrid_search.hybrid_search("auth service", top_k=1)

    assert result[0]["raw_vector_score"] == 0.9
    assert result[0]["raw_bm25_norm"] == 0.0
    assert result[0]["score"] == 0.54