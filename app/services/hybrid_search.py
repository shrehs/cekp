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

# Absolute floor on raw cosine similarity (embeddings are normalized, so
# hit.score is a stable, comparable cosine value -- unlike BM25 below,
# which is only ever normalized RELATIVE TO ITS OWN CANDIDATE POOL and so
# has no absolute meaning). Without this floor, an off-topic query still
# gets top_k hits back from Qdrant (search always returns something), and
# whichever one is least-irrelevant then gets BM25-normalized up to 1.0,
# manufacturing a confident-looking result out of no real evidence (see
# docs/evaluation_report_20260901_184541.md, "Tell me about machine
# learning" -> success at 0.52 confidence with no genuinely relevant
# candidate in the pool). This value is a starting point, not a
# calibrated constant -- retune it empirically against
# settings.embedding_model's actual similarity distribution by rerunning
# the evaluation suite, not by assumption.
MIN_VECTOR_SCORE = 0.3


def hybrid_search(question: str, top_k: int = 5) -> list[dict]:
    query_vector = embed_query(question)
    candidate_limit = max(top_k * CANDIDATE_POOL_MULTIPLIER, 10)

    hits = vector_store.vector_search(query_vector, top_k=candidate_limit)
    hits_before_floor = len(hits)
    hits = [hit for hit in hits if hit.score >= MIN_VECTOR_SCORE]
    dropped_by_floor = hits_before_floor - len(hits)
    if not hits:
        return []

    texts = [
        hit.payload["text"]
        for hit in hits
        if hit.payload is not None
    ]
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

    valid_hits = [hit for hit in hits if hit.payload is not None]
    for hit, bm25_norm in zip(valid_hits, normalized_bm25):
        payload = hit.payload
        assert payload is not None

        combined_score = (VECTOR_WEIGHT * float(hit.score)) + (BM25_WEIGHT * bm25_norm)

        combined.append(
            {
                "chunk_id": str(hit.id),
                "document_id": payload["document_id"],
                "document_title": payload["document_title"],
                "text": payload["text"],
                "source_system": payload["source_system"],
                "score": float(round(combined_score, 4)),
                # Raw components, kept separate from "score" above so callers
                # (HybridStrategy, the eval trace) can see WHAT produced a
                # given confidence -- not just the final blended number.
                # Added after a case where two queries produced visually
                # identical combined scores across a code change and there
                # was no way to tell, after the fact, whether the vector
                # floor filter had actually removed any candidates or the
                # query's top raw cosine score simply already cleared it.
                "raw_vector_score": float(round(hit.score, 4)),
                "raw_bm25_norm": float(round(bm25_norm, 4)),
            }
        )

    combined.sort(key=lambda r: r["score"], reverse=True)
    return combined[:top_k]