"""
Neo4jGraphRetriever: the real GraphRetriever implementation. Every
Cypher MATCH (read) statement in this codebase lives here --
GraphRepository never reads, GraphBuilder never touches Neo4j at all.

Fuzzy resolution pattern used throughout: `node.qualified_name = $ref
OR node.qualified_name ENDS WITH $suffix OR node.name = $ref`, where
$suffix is `"." + $ref`. This lets GraphStrategy call these methods
with a short token pulled from a free-text question ("auth",
"authenticate") without needing its own name-resolution logic --
see retriever_base.py's module docstring for the full rationale.

Where a reference could match more than one node (a short name isn't
unique across the whole graph), results are ordered by qualified_name
so "which one wins" is deterministic, not arbitrary -- ambiguity is
visible in the data (caller can inspect all matches if they want),
not hidden by whatever order Neo4j happened to return rows in.

Untested against a live Neo4j by Claude, same caveat as
neo4j_repository.py -- verified via tests/test_neo4j_retriever.py
using a fake driver that records queries without executing them, plus
static reasoning about the Cypher. Real semantic correctness needs a
live run, same as everywhere else in the graph subsystem.
"""
import logging
import time

from app.graph.models import ClassNode, FunctionNode, ModuleNode
from app.graph.retriever_base import GraphRetriever

logger = logging.getLogger(__name__)

_FUZZY_MATCH_WHERE = "(node.qualified_name = $ref OR node.qualified_name ENDS WITH $suffix OR node.name = $ref)"


def _run_and_log(session, query: str, method_name: str, **params):
    """
    Wraps session.run() with timing + a debug log line, for operator
    visibility into individual Cypher call latency in container logs --
    distinct from GraphStrategy's retrieval_ms, which bundles this same
    call together with network round-trip and is reported per-request
    via /query/trace, not per-line in logs.
    """
    start = time.perf_counter()
    result = session.run(query, **params)
    records = list(result)  # materialize now so the timer reflects actual query completion, not lazy iteration later
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.debug("Neo4jGraphRetriever.%s: %.2fms, %d record(s)", method_name, elapsed_ms, len(records))
    return records


def _module_from_record(record, key: str) -> ModuleNode:
    node = record[key]
    return ModuleNode(
        id=node["id"], name=node["name"], qualified_name=node["qualified_name"],
        path=node["path"], language=node["language"],
        start_line=node["start_line"], end_line=node["end_line"],
    )


def _class_from_record(record, key: str) -> ClassNode:
    node = record[key]
    return ClassNode(
        id=node["id"], name=node["name"], qualified_name=node["qualified_name"],
        path=node["path"], start_line=node["start_line"], end_line=node["end_line"],
    )


def _function_from_record(record, key: str) -> FunctionNode:
    node = record[key]
    return FunctionNode(
        id=node["id"], name=node["name"], qualified_name=node["qualified_name"],
        signature=node["signature"], path=node["path"],
        start_line=node["start_line"], end_line=node["end_line"],
    )


class Neo4jGraphRetriever(GraphRetriever):
    def __init__(self, driver):
        self._driver = driver

    def get_module_imports(self, module_reference: str) -> list[ModuleNode]:
        query = f"""
            MATCH (node:Module)
            WHERE {_FUZZY_MATCH_WHERE}
            WITH node LIMIT 1
            MATCH (node)-[:IMPORTS]->(imported:Module)
            RETURN imported
            ORDER BY imported.qualified_name
        """
        with self._driver.session() as session:
            records = _run_and_log(session, query, "get_module_imports", ref=module_reference, suffix=f".{module_reference}")
            return [_module_from_record(r, "imported") for r in records]

    def get_importers_of(self, module_reference: str) -> list[ModuleNode]:
        query = f"""
            MATCH (node:Module)
            WHERE {_FUZZY_MATCH_WHERE}
            WITH node LIMIT 1
            MATCH (importer:Module)-[:IMPORTS]->(node)
            RETURN importer
            ORDER BY importer.qualified_name
        """
        with self._driver.session() as session:
            records = _run_and_log(session, query, "get_importers_of", ref=module_reference, suffix=f".{module_reference}")
            return [_module_from_record(r, "importer") for r in records]

    def get_functions_defined_in(self, module_reference: str) -> list[FunctionNode]:
        query = f"""
            MATCH (node:Module)
            WHERE {_FUZZY_MATCH_WHERE}
            WITH node LIMIT 1
            MATCH (node)-[:DEFINES]->(fn:Function)
            RETURN fn
            ORDER BY fn.qualified_name
        """
        with self._driver.session() as session:
            records = _run_and_log(session, query, "get_functions_defined_in", ref=module_reference, suffix=f".{module_reference}")
            return [_function_from_record(r, "fn") for r in records]

    def get_classes_defined_in(self, module_reference: str) -> list[ClassNode]:
        query = f"""
            MATCH (node:Module)
            WHERE {_FUZZY_MATCH_WHERE}
            WITH node LIMIT 1
            MATCH (node)-[:DEFINES]->(cls:Class)
            RETURN cls
            ORDER BY cls.qualified_name
        """
        with self._driver.session() as session:
            records = _run_and_log(session, query, "get_classes_defined_in", ref=module_reference, suffix=f".{module_reference}")
            return [_class_from_record(r, "cls") for r in records]

    def find_function(self, function_reference: str) -> FunctionNode | None:
        query = """
            MATCH (fn:Function)
            WHERE (fn.qualified_name = $ref OR fn.qualified_name ENDS WITH $suffix OR fn.name = $ref)
            RETURN fn
            ORDER BY fn.qualified_name, fn.start_line
            LIMIT 1
        """
        with self._driver.session() as session:
            records = _run_and_log(session, query, "find_function", ref=function_reference, suffix=f".{function_reference}")
            return _function_from_record(records[0], "fn") if records else None

    def find_class(self, class_reference: str) -> ClassNode | None:
        query = """
            MATCH (cls:Class)
            WHERE (cls.qualified_name = $ref OR cls.qualified_name ENDS WITH $suffix OR cls.name = $ref)
            RETURN cls
            ORDER BY cls.qualified_name
            LIMIT 1
        """
        with self._driver.session() as session:
            records = _run_and_log(session, query, "find_class", ref=class_reference, suffix=f".{class_reference}")
            return _class_from_record(records[0], "cls") if records else None

    def get_methods_of_class(self, class_reference: str, method_name: str) -> FunctionNode | None:
        """
        Find a specific method of a class. This is more precise than
        global function search and avoids ambiguity when method names
        like __init__ are common across many classes.
        
        Returns: FunctionNode if found, None otherwise. Only returns one
        method per class (matches the pattern "ClassName.method_name").
        """
        query = f"""
            MATCH (cls:Class)
            WHERE {_FUZZY_MATCH_WHERE}
            WITH cls LIMIT 1
            MATCH (cls)-[:DEFINES]->(method:Function)
            WHERE method.name = $method_ref
            RETURN method
            ORDER BY method.qualified_name, method.start_line
            LIMIT 1
        """
        with self._driver.session() as session:
            records = _run_and_log(
                session, query, "get_methods_of_class",
                ref=class_reference, suffix=f".{class_reference}", method_ref=method_name
            )
            return _function_from_record(records[0], "method") if records else None

    def get_callers_of(self, function_reference: str) -> list[FunctionNode]:
        query = """
            MATCH (target:Function)
            WHERE (target.qualified_name = $ref OR target.qualified_name ENDS WITH $suffix OR target.name = $ref)
            WITH target
            ORDER BY target.qualified_name, target.start_line
            LIMIT 1
            MATCH (caller:Function)-[:CALLS]->(target)
            RETURN caller
            ORDER BY caller.qualified_name
        """
        with self._driver.session() as session:
            records = _run_and_log(session, query, "get_callers_of", ref=function_reference, suffix=f".{function_reference}")
            return [_function_from_record(r, "caller") for r in records]