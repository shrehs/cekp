from prometheus_client import Counter, Gauge, Histogram


# ---------------------------------------------------------------------------
# CEKP query-level metrics
# ---------------------------------------------------------------------------

QUERY_TOTAL = Counter(
    "cekp_queries_total",
    "Total number of CEKP queries processed.",
)

QUERY_OUTCOME_TOTAL = Counter(
    "cekp_query_outcomes_total",
    "CEKP query outcomes.",
    ["outcome"],
)

QUERY_DURATION = Histogram(
    "cekp_query_duration_seconds",
    "End-to-end CEKP query duration.",
    buckets=(
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
        30.0,
        60.0,
    ),
)

# ---------------------------------------------------------------------------
# Planner / retrieval metrics
# ---------------------------------------------------------------------------

RETRIEVAL_STRATEGY_TOTAL = Counter(
    "cekp_retrieval_strategy_total",
    "Number of CEKP queries resolved by each retrieval strategy.",
    ["strategy"],
)

RETRIEVAL_ATTEMPTS_TOTAL = Counter(
    "cekp_retrieval_attempts_total",
    "Number of retrieval strategy attempts.",
    ["strategy", "outcome"],
)

RETRIEVAL_DURATION = Histogram(
    "cekp_retrieval_duration_seconds",
    "Duration of individual retrieval strategy attempts.",
    ["strategy"],
    buckets=(
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
        30.0,
    ),
)

RETRIEVED_DOCUMENTS = Histogram(
    "cekp_retrieved_documents",
    "Number of documents returned by successful CEKP queries.",
    buckets=(0, 1, 2, 3, 5, 10, 20, 50, 100),
)

PLANNER_CONFIDENCE = Histogram(
    "cekp_planner_confidence",
    "Final planner confidence for successful queries.",
    buckets=(
        0.0,
        0.25,
        0.5,
        0.6,
        0.7,
        0.8,
        0.9,
        1.0,
    ),
)

ACTIVE_QUERIES = Gauge(
    "cekp_active_queries",
    "Number of CEKP queries currently being processed.",
)