"""
Hybrid retrieval service (Month 1 scope). Combines vector similarity
with BM25 keyword scoring: vector search pulls a candidate pool, BM25
reranks it so exact terms (error codes, names, IDs) aren't lost to
pure semantic similarity.

This is the "Hybrid Search" primitive referenced by the Adaptive
Retrieval Planner (architecture doc, Section 5.5) -- the planner itself
is Month 2 scope; this module is one of the tools it will call.
"""
from rank_bm25 import BM25Okapi

from app.core import vector_store
from app.services.embedding import embed_query

CANDIDATE_POOL_MULTIPLIER = 4  # pull more candidates than top_k so BM25 has something to rerank
VECTOR_WEIGHT = 0.6
BM25_WEIGHT = 0.4


def hybrid_search(question: str, top_k: int = 5) -> list[dict]:
    query_vector = embed_query(question)
    candidate_limit = max(top_k * CANDIDATE_POOL_MULTIPLIER, 10)

    hits = vector_store.vector_search(query_vector, top_k=candidate_limit)
    if not hits:
        return []

    texts = [hit.payload["text"] for hit in hits]
    tokenized_corpus = [t.lower().split() for t in texts]
    tokenized_query = question.lower().split()

    bm25 = BM25Okapi(tokenized_corpus)
    bm25_scores = bm25.get_scores(tokenized_query)

    # Normalize BM25 scores to 0-1 so they're combinable with cosine similarity.
    # bm25.get_scores() returns a numpy array -- cast to native float here,
    # at the source, rather than downstream. numpy.float64 happens to
    # subclass Python's float (so it silently "works" almost everywhere,
    # including json.dumps), but numpy.bool_ does NOT subclass bool -- so a
    # later comparison like `confidence >= threshold` on an un-cast numpy
    # float produces a numpy.bool_ that breaks JSON serialization. Casting
    # here, at the one place numpy enters this pipeline, prevents that
    # class of bug regardless of what happens downstream.
    max_bm25 = float(max(bm25_scores)) if max(bm25_scores) > 0 else 1.0
    normalized_bm25 = [float(s) / max_bm25 for s in bm25_scores]

    combined = []
    for hit, bm25_norm in zip(hits, normalized_bm25):
        combined_score = (VECTOR_WEIGHT * float(hit.score)) + (BM25_WEIGHT * bm25_norm)
        combined.append(
            {
                "chunk_id": str(hit.id),
                "document_id": hit.payload["document_id"],
                "document_title": hit.payload["document_title"],
                "text": hit.payload["text"],
                "source_system": hit.payload["source_system"],
                "score": float(round(combined_score, 4)),
            }
        )

    combined.sort(key=lambda r: r["score"], reverse=True)
    return combined[:top_k]