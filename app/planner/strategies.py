"""
Concrete RetrievalStrategy implementations.

VectorStrategy and HybridStrategy are real. GraphStrategy is an
honest stub -- it returns StrategyOutcome.NOT_IMPLEMENTED rather than
LOW_CONFIDENCE, because "this doesn't exist yet" and "this ran and
wasn't confident" are different facts and the audit log should not
conflate them (see docs/planner.md, Known v1 Limitations).
AgenticStrategy is a minimal placeholder: it currently just runs
hybrid search twice (an approximation of "decompose and retrieve
per sub-question") rather than a full agent loop -- also called out
as a v1 limitation.
"""
import logging
import re
import time

from app.core import vector_store
from app.graph.models import ClassNode, FunctionNode, ModuleNode
from app.graph.retriever_base import GraphRetriever
from app.planner.context import PlannerContext
from app.planner.enums import StrategyName, StrategyOutcome
from app.planner.intent_classifier import ORG_DEPENDENCY_PATTERNS
from app.planner.result import RetrievalResult
from app.planner.strategy_base import RetrievalStrategy
from app.services.embedding import embed_query
from app.services.hybrid_search import hybrid_search

logger = logging.getLogger(__name__)


class VectorStrategy(RetrievalStrategy):
    """Pure vector similarity search -- no BM25 rerank."""

    def retrieve(self, context: PlannerContext) -> RetrievalResult:
        start = time.perf_counter()
        try:
            query_vector = embed_query(context.query)
            hits = vector_store.vector_search(query_vector, top_k=5)
        except Exception:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.exception("Vector strategy failed for query: %r", context.query)
            return RetrievalResult(
                documents=[],
                confidence=0.0,
                strategy_name=StrategyName.VECTOR,
                outcome=StrategyOutcome.LOW_CONFIDENCE,
                latency_ms=latency_ms,
                reasoning="Vector search unavailable because the backing vector service failed.",
                metadata={"error": "vector_infrastructure_failure"},
            )
        latency_ms = (time.perf_counter() - start) * 1000

        if not hits:
            return RetrievalResult(
                documents=[],
                confidence=0.0,
                strategy_name=StrategyName.VECTOR,
                outcome=StrategyOutcome.LOW_CONFIDENCE,
                latency_ms=latency_ms,
                reasoning="No vector hits returned.",
            )

        top_score = hits[0].score
        documents = [
            {
                "chunk_id": str(h.id),
                "document_id": h.payload["document_id"],
                "document_title": h.payload["document_title"],
                "text": h.payload["text"],
                "source_system": h.payload.get("source_system", "unknown"),
                "score": float(h.score),
            }
            for h in hits
            if h.payload is not None
        ]
        return RetrievalResult(
            documents=documents,
            confidence=top_score,  # confidence = cosine similarity, see docs/confidence.md
            strategy_name=StrategyName.VECTOR,
            outcome=StrategyOutcome.SUCCESS,
            latency_ms=latency_ms,
            reasoning=f"Vector search, top cosine similarity {top_score:.3f}.",
        )


class HybridStrategy(RetrievalStrategy):
    """Vector + BM25 rerank. Wraps the existing hybrid_search service as-is."""

    def retrieve(self, context: PlannerContext) -> RetrievalResult:
        start = time.perf_counter()
        try:
            results = hybrid_search(context.query, top_k=5)
        except Exception:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.exception("Hybrid strategy failed for query: %r", context.query)
            return RetrievalResult(
                documents=[],
                confidence=0.0,
                strategy_name=StrategyName.HYBRID,
                outcome=StrategyOutcome.LOW_CONFIDENCE,
                latency_ms=latency_ms,
                reasoning="Hybrid search unavailable because the backing vector service failed.",
                metadata={"error": "hybrid_infrastructure_failure"},
            )
        latency_ms = (time.perf_counter() - start) * 1000

        if not results:
            return RetrievalResult(
                documents=[],
                confidence=0.0,
                strategy_name=StrategyName.HYBRID,
                outcome=StrategyOutcome.LOW_CONFIDENCE,
                latency_ms=latency_ms,
                reasoning="No hybrid search results.",
            )

        top_score = results[0]["score"]
        return RetrievalResult(
            documents=results,
            # confidence = weighted(vector_score, bm25_score), see docs/confidence.md
            confidence=top_score,
            strategy_name=StrategyName.HYBRID,
            outcome=StrategyOutcome.SUCCESS,
            latency_ms=latency_ms,
            reasoning=f"Hybrid search, top combined score {top_score:.3f}.",
            # Was always None before -- every success trace showed
            # "metadata": null with no way to tell, after the fact, what
            # actually produced a given confidence. Surfacing the winning
            # candidate's raw components here so a low-looking-legitimate
            # score (e.g. an off-topic query's top hit) can be diagnosed
            # from the trace/eval report directly, instead of guessing.
            metadata={
                "top_raw_vector_score": results[0].get("raw_vector_score"),
                "top_raw_bm25_norm": results[0].get("raw_bm25_norm"),
            },
        )


class GraphStrategy(RetrievalStrategy):
    """
    Real implementation. Not a stub as of this version -- see
    docs/graph-schema.md and docs/planner.md for the history (this was
    NOT_IMPLEMENTED for most of this project; the GRAPH_PATTERNS in
    intent_classifier.py routing here don't guarantee this strategy
    can answer every graph-shaped question -- see the sub-classifier
    below, which is a second, more specific classification step run
    only on queries already routed here).

    Sub-classification: which SPECIFIC kind of graph question this is
    (imports / importers-of / functions-in / classes-in / callers-of /
    where-is-X-defined), plus extracting a target reference token from
    the free text. This is simple regex, not real NLU -- same
    philosophy as IntentClassifier itself, and the same honesty about
    it: a query that doesn't match any sub-pattern, or whose extracted
    reference doesn't resolve to anything in the graph, returns
    LOW_CONFIDENCE (the strategy ran, found nothing usable), not
    NOT_IMPLEMENTED (which now specifically means "this capability
    doesn't exist" -- it does, it just couldn't answer THIS question).
    """

    # (retriever_method_name, compiled_pattern) -- checked in order,
    # first match wins. Patterns are deliberately specific (e.g.
    # requiring "defined in" for functions_in/classes_in) so
    # "which functions call X" doesn't accidentally match functions_in
    # just because it contains the word "functions".
    #
    # For class->method patterns, we use two capture groups: (method_name, class_name).
    # _classify() extracts both and joins them as "method_name:class_name" for special handling.
    _SUB_PATTERNS = [
    (
        "get_importers_of",
        re.compile(
            r"(?:which|what)\s+modules?\s+imports?\s+([\w./]+)",
            re.IGNORECASE,
        ),
    ),
    (
        "get_importers_of",
        re.compile(
            r"(?:list\s+)?modules?\s+that\s+imports?\s+([\w./]+)",
            re.IGNORECASE,
        ),
    ),
    (
        "get_module_imports",
        re.compile(
            r"what\s+does\s+([\w./]+)\s+imports?",
            re.IGNORECASE,
        ),
    ),
    (
        "get_module_imports",
        re.compile(
            r"what\s+imports?\s+does\s+([\w./]+)\s+have",
            re.IGNORECASE,
        ),
    ),
    (
        "get_callers_of",
        re.compile(
            r"(?:which\s+functions?|who)\s+calls?\s+([\w./]+)",
            re.IGNORECASE,
        ),
    ),
    (
        "get_callers_of",
        re.compile(
            r"what\s+calls?\s+([\w./]+)",
            re.IGNORECASE,
        ),
    ),
    (
        "get_callers_of",
        re.compile(
            r"(?:list\s+)?callers?\s+of\s+([\w./]+)",
            re.IGNORECASE,
        ),
    ),
    (
        "get_functions_defined_in",
        re.compile(
            r"(?:what|which|list)?\s*functions?\s+(?:are\s+)?defined\s+in\s+([\w./]+)",
            re.IGNORECASE,
        ),
    ),
    (
        "get_classes_defined_in",
        re.compile(
            r"(?:what|which|list)?\s*class(?:es)?\s+(?:are\s+)?defined\s+in\s+([\w./]+)",
            re.IGNORECASE,
        ),
    ),
    (
        "get_classes_defined_in",
        re.compile(
            r"(?:what|which|list)\s+class(?:es)?\s+in\s+([\w./]+)",
            re.IGNORECASE,
        ),
    ),
    (
        "find_method_of_class",
        re.compile(
            r"(?:find|show\s+me|locate)\s+"
            r"(?:the\s+)?([\w_]+)\s+"
            r"(?:method\s+)?of\s+"
            r"(?:the\s+)?([\w./]+)",
            re.IGNORECASE,
        ),
    ),
    (
        "find_method_of_class",
        re.compile(
            r"(?:find|show\s+me|locate)\s+"
            r"(?:the\s+)?([\w./]+)\s*\.\s*([\w_]+)",
            re.IGNORECASE,
        ),
    ),
    (
        "find_symbol",
        re.compile(
            r"where\s+is\s+(?:the\s+)?([\w./]+)"
            r"(?:\s+(?:class|function|method|module))?"
            r"\s+defined",
            re.IGNORECASE,
        ),
    ),
    (
        "find_symbol",
        re.compile(
            r"(?:find|show\s+me|locate)\s+"
            r"(?:the\s+)?([\w./]+)"
            r"\s+(?:class|function|method)\b",
            re.IGNORECASE,
        ),
    ),
    ]

    def __init__(self, retriever: GraphRetriever | None = None):
        self._retriever = retriever  # lazily constructed on first use if not injected -- see _get_retriever()

    def _get_retriever(self) -> GraphRetriever:
        if self._retriever is None:
            # Lazy imports: avoids requiring the `neo4j` package just to
            # import this module or instantiate GraphStrategy -- only
            # actually needed if retrieve() runs without an injected
            # retriever (i.e. never, in tests that inject a fake one).
            from app.core.graph_store import get_driver
            from app.graph.neo4j_retriever import Neo4jGraphRetriever

            self._retriever = Neo4jGraphRetriever(get_driver())
        return self._retriever

    def retrieve(self, context: PlannerContext) -> RetrievalResult:
        start = time.perf_counter()
        query = context.query or ""

        classify_start = time.perf_counter()
        is_org_dependency = any(re.search(p, query, re.IGNORECASE) for p in ORG_DEPENDENCY_PATTERNS)
        classification = None if is_org_dependency else self._classify(query)

        if classification is None:
            method_name = None
            reference = None
        else:
            method_name, reference = classification
        classification_ms = (time.perf_counter() - classify_start) * 1000

        if is_org_dependency:
            # Recognized as an org-dependency question ("which services
            # depend on X") -- a distinct, real capability that isn't
            # built yet (needs entity extraction; see docs/graph-schema.md),
            # not "couldn't parse this at all". Keep NOT_IMPLEMENTED for
            # this specific case even though GraphStrategy is otherwise
            # real now -- conflating this with LOW_CONFIDENCE would erase
            # a distinction the rest of this project has been careful
            # about (see docs/planner.md).
            return RetrievalResult(
                documents=[],
                confidence=0.0,
                strategy_name=StrategyName.GRAPH,
                outcome=StrategyOutcome.NOT_IMPLEMENTED,
                latency_ms=(time.perf_counter() - start) * 1000,
                reasoning="Recognized as an org-dependency graph question, which requires "
                "entity extraction not yet built (see docs/graph-schema.md) -- distinct from "
                "the code-structure graph, which is implemented.",
                metadata={"classification_ms": classification_ms},
            )
        
        if method_name is None or reference is None:
            return RetrievalResult(
                documents=[],
                confidence=0.0,
                strategy_name=StrategyName.GRAPH,
                outcome=StrategyOutcome.LOW_CONFIDENCE,
                latency_ms=(time.perf_counter() - start) * 1000,
                reasoning="Could not determine which kind of graph question this is (no sub-pattern matched).",
                metadata={"classification_ms": classification_ms},
            )

        retriever = self._get_retriever()

        # "retrieval_ms" bundles network round-trip + server-side Cypher
        # execution -- these can't be cleanly separated from the Python
        # client without Neo4j server-side query profiling (PROFILE/
        # EXPLAIN change query semantics; server-side logging is a
        # separate, heavier instrumentation this doesn't attempt). Don't
        # report a fake 3-way split implying more precision than the
        # client can actually observe.
        retrieval_start = time.perf_counter()
        try:
            if method_name == "find_method_of_class":
                # reference is "method_name:class_name"
                parts = reference.split(":")
                if len(parts) == 2:
                    method_ref, class_ref = parts
                    node = retriever.get_methods_of_class(class_ref, method_ref)
                    results = [node] if node is not None else []
                else:
                    results = []
            elif method_name == "find_symbol":
                # "where is X defined" doesn't know in advance whether X
                # is a function or a class -- try both, function first.
                node = retriever.find_function(reference)
                if node is None:
                    node = retriever.find_class(reference)
                results = [node] if node is not None else []
            else:
                results = getattr(retriever, method_name)(reference)
        except Exception as e:
            return RetrievalResult(
                documents=[],
                confidence=0.0,
                strategy_name=StrategyName.GRAPH,
                outcome=StrategyOutcome.ERROR,
                latency_ms=(time.perf_counter() - start) * 1000,
                reasoning=f"Graph query failed: {e}",
                metadata={
                    "classification_ms": classification_ms,
                    "retrieval_ms": (time.perf_counter() - retrieval_start) * 1000,
                },
            )
        retrieval_ms = (time.perf_counter() - retrieval_start) * 1000

        format_start = time.perf_counter()
        documents = [_node_to_doc(n) for n in results]
        formatting_ms = (time.perf_counter() - format_start) * 1000

        latency_ms = (time.perf_counter() - start) * 1000
        metadata = {
            "classification_ms": classification_ms,
            "retrieval_ms": retrieval_ms,  # network round-trip + server-side Cypher execution, combined
            "formatting_ms": formatting_ms,
            "method": method_name,
            "reference": reference,
        }

        if not documents:
            return RetrievalResult(
                documents=[],
                confidence=0.0,
                strategy_name=StrategyName.GRAPH,
                outcome=StrategyOutcome.LOW_CONFIDENCE,
                latency_ms=latency_ms,
                reasoning=f"Recognized as a '{method_name}' question (target: '{reference}'), "
                f"but nothing in the graph matched.",
                metadata=metadata,
            )

        return RetrievalResult(
            documents=documents,
            # Confidence is a near-binary heuristic here, not a
            # similarity score -- see docs/confidence.md: "did the
            # traversal find something at all" is the real signal for
            # a graph strategy, unlike vector/hybrid's continuous scores.
            confidence=0.85,
            strategy_name=StrategyName.GRAPH,
            outcome=StrategyOutcome.SUCCESS,
            latency_ms=latency_ms,
            reasoning=f"Graph query '{method_name}' on '{reference}' returned {len(documents)} result(s).",
            metadata=metadata,
        )

    @classmethod
    def _classify(cls, query: str) -> tuple[str, str] | None:
        for method_name, pattern in cls._SUB_PATTERNS:
            match = pattern.search(query)
            if match:
                # For class->method patterns, extract both method and class name
                if method_name == "find_method_of_class" and match.groups().__len__() >= 2:
                    group1 = match.group(1).rstrip("()").strip(".")
                    group2 = match.group(2).rstrip("()").strip(".")
                    
                    # Detect pattern: "method_name of ClassName" vs "ClassName.method_name"
                    # For "method_name of ClassName": group1 is method, group2 is class
                    # For "ClassName.method_name": group1 is class, group2 is method
                    # Heuristic: if group1 starts with uppercase AND group2 starts with underscore,
                    # or if group1 contains dots (module path), then group1 is the class
                    if ("." in group1) or (group1 and group1[0].isupper() and group2.startswith("_")):
                        # Pattern: "ClassName.method_name" -> group1=class, group2=method
                        method_ref, class_ref = group2, group1
                    else:
                        # Pattern: "method_name of ClassName" -> group1=method, group2=class
                        method_ref, class_ref = group1, group2
                    
                    reference = f"{method_ref}:{class_ref}"
                else:
                    reference = match.group(1).rstrip("()").strip(".")
                return method_name, reference

        return None, None

def _node_to_doc(node) -> dict:
    """Converts a graph node (Module/Class/Function) into the same list[dict] shape RetrievalResult.documents expects everywhere else."""
    if isinstance(node, ModuleNode):
        return {
            "type": "module",
            "qualified_name": node.qualified_name,
            "path": node.path,
            "text": f"Module {node.qualified_name} ({node.path})",
        }
    if isinstance(node, ClassNode):
        return {
            "type": "class",
            "qualified_name": node.qualified_name,
            "path": node.path,
            "start_line": node.start_line,
            "end_line": node.end_line,
            "text": f"Class {node.qualified_name} ({node.path}:{node.start_line})",
        }
    if isinstance(node, FunctionNode):
        return {
            "type": "function",
            "qualified_name": node.qualified_name,
            "signature": node.signature,
            "path": node.path,
            "start_line": node.start_line,
            "end_line": node.end_line,
            "text": f"{node.signature} ({node.path}:{node.start_line})",
        }
    return {"type": "unknown", "text": str(node)}


class AgenticStrategy(RetrievalStrategy):
    """
    Minimal placeholder for multi-hop/agentic retrieval. v1 approximates
    this by running hybrid search directly -- a real decomposition loop
    (sub-question generation + iterative retrieval) is future work.
    """

    def retrieve(self, context: PlannerContext) -> RetrievalResult:
        start = time.perf_counter()
        try:
            results = hybrid_search(context.query, top_k=8)
        except Exception:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.exception("Agentic strategy failed for query: %r", context.query)
            return RetrievalResult(
                documents=[],
                confidence=0.0,
                strategy_name=StrategyName.AGENTIC,
                outcome=StrategyOutcome.LOW_CONFIDENCE,
                latency_ms=latency_ms,
                reasoning="Agentic search unavailable because the backing vector service failed.",
                metadata={"error": "agentic_infrastructure_failure"},
            )
        latency_ms = (time.perf_counter() - start) * 1000

        if not results:
            return RetrievalResult(
                documents=[],
                confidence=0.0,
                strategy_name=StrategyName.AGENTIC,
                outcome=StrategyOutcome.LOW_CONFIDENCE,
                latency_ms=latency_ms,
                reasoning="No results from underlying hybrid search.",
            )

        # confidence = planner heuristic: average of top-3 combined scores,
        # deliberately conservative since this isn't true multi-hop yet.
        top_n = results[:3]
        avg_score = sum(r["score"] for r in top_n) / len(top_n)
        return RetrievalResult(
            documents=results,
            confidence=avg_score,
            strategy_name=StrategyName.AGENTIC,
            outcome=StrategyOutcome.SUCCESS,
            latency_ms=latency_ms,
            reasoning=(
                "Agentic strategy is a v1 placeholder (single hybrid-search "
                f"pass, not true decomposition); avg top-3 score {avg_score:.3f}."
            ),
        )