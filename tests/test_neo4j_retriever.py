"""
Tests for Neo4jGraphRetriever using a fake driver: records what
query+params were sent (proving the fuzzy-match WHERE clause and
params are constructed correctly) and returns canned records (proving
the record-to-dataclass conversion is correct). Does NOT prove the
Cypher is semantically correct against a real database -- that needs
scripts/validate_neo4j_repository.py's live counterpart for the
retriever (not yet written -- see the response text for why).
"""
from app.graph.models import ClassNode, FunctionNode, ModuleNode
from app.graph.neo4j_retriever import Neo4jGraphRetriever


class FakeResult:
    def __init__(self, records: list[dict]):
        self._records = records

    def __iter__(self):
        return iter(self._records)

    def single(self):
        return self._records[0] if self._records else None


class FakeSession:
    def __init__(self, canned_results: list[FakeResult]):
        self._canned_results = list(canned_results)
        self.calls: list[tuple[str, dict]] = []  # (query, params)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query, **params):
        self.calls.append((query, params))
        return self._canned_results.pop(0) if self._canned_results else FakeResult([])


class FakeDriver:
    def __init__(self, canned_results: list[FakeResult] | None = None):
        self._canned_results = canned_results or []
        self.last_session: FakeSession | None = None

    def session(self):
        self.last_session = FakeSession(self._canned_results)
        return self.last_session


def _module_node_props(qn: str) -> dict:
    return {
        "id": f"module:{qn}", "name": qn.split(".")[-1], "qualified_name": qn,
        "path": f"{qn.replace('.', '/')}.py", "language": "python",
        "start_line": 1, "end_line": 10,
    }


def _function_node_props(qn: str, line: int = 5) -> dict:
    return {
        "id": f"function:{qn}:L{line}", "name": qn.split(".")[-1], "qualified_name": qn,
        "signature": f"def {qn.split('.')[-1]}()", "path": f"{qn.replace('.', '/')}.py",
        "start_line": line, "end_line": line + 1,
    }


def test_get_module_imports_uses_fuzzy_match_where_clause_and_correct_params():
    driver = FakeDriver(canned_results=[FakeResult([{"imported": _module_node_props("app.core.config")}])])
    retriever = Neo4jGraphRetriever(driver)

    results = retriever.get_module_imports("config")

    query, params = driver.last_session.calls[0]
    assert "MATCH (node:Module)" in query
    assert "qualified_name = $ref" in query
    assert "qualified_name ENDS WITH $suffix" in query
    assert params == {"ref": "config", "suffix": ".config"}

    assert len(results) == 1
    assert isinstance(results[0], ModuleNode)
    assert results[0].qualified_name == "app.core.config"


def test_get_functions_defined_in_converts_records_to_function_nodes():
    driver = FakeDriver(canned_results=[
        FakeResult([
            {"fn": _function_node_props("app.main.health")},
            {"fn": _function_node_props("app.main.on_startup")},
        ])
    ])
    retriever = Neo4jGraphRetriever(driver)

    results = retriever.get_functions_defined_in("app.main")

    assert len(results) == 2
    assert all(isinstance(r, FunctionNode) for r in results)
    assert {r.qualified_name for r in results} == {"app.main.health", "app.main.on_startup"}


def test_get_classes_defined_in_converts_records_to_class_nodes():
    driver = FakeDriver(canned_results=[
        FakeResult([{"cls": {
            "id": "class:app.core.config.Settings", "name": "Settings",
            "qualified_name": "app.core.config.Settings", "path": "app/core/config.py",
            "start_line": 10, "end_line": 30,
        }}])
    ])
    retriever = Neo4jGraphRetriever(driver)

    results = retriever.get_classes_defined_in("config")

    assert len(results) == 1
    assert isinstance(results[0], ClassNode)
    assert results[0].qualified_name == "app.core.config.Settings"


def test_find_function_returns_none_when_no_match():
    driver = FakeDriver(canned_results=[FakeResult([])])
    retriever = Neo4jGraphRetriever(driver)

    result = retriever.find_function("nonexistent_function")

    assert result is None


def test_find_function_returns_single_node_when_found():
    driver = FakeDriver(canned_results=[FakeResult([{"fn": _function_node_props("app.main.health")}])])
    retriever = Neo4jGraphRetriever(driver)

    result = retriever.find_function("health")

    assert isinstance(result, FunctionNode)
    assert result.qualified_name == "app.main.health"

    query, params = driver.last_session.calls[0]
    assert "LIMIT 1" in query  # exactly one result even if multiple match


def test_get_callers_of_two_query_shape_resolves_target_then_finds_callers():
    """
    get_callers_of does target resolution AND caller lookup in one
    Cypher statement (via the intermediate WITH), not two separate
    round trips -- confirm that's still what's actually being sent.
    """
    driver = FakeDriver(canned_results=[FakeResult([{"caller": _function_node_props("app.main.on_startup")}])])
    retriever = Neo4jGraphRetriever(driver)

    results = retriever.get_callers_of("health")

    assert len(driver.last_session.calls) == 1  # one round trip, not two
    query, params = driver.last_session.calls[0]
    assert "MATCH (target:Function)" in query
    assert "MATCH (caller:Function)-[:CALLS]->(target)" in query
    assert params == {"ref": "health", "suffix": ".health"}
    assert len(results) == 1
    assert results[0].qualified_name == "app.main.on_startup"


def test_get_importers_of_is_the_reverse_direction_of_get_module_imports():
    """
    'Which modules import auth?' needs incoming IMPORTS edges, not
    outgoing -- confirm the Cypher direction is actually reversed
    (importer -> node), not accidentally identical to get_module_imports.
    """
    driver = FakeDriver(canned_results=[FakeResult([{"importer": _module_node_props("app.main")}])])
    retriever = Neo4jGraphRetriever(driver)

    results = retriever.get_importers_of("config")

    query, params = driver.last_session.calls[0]
    assert "MATCH (importer:Module)-[:IMPORTS]->(node)" in query
    assert "RETURN importer" in query
    assert len(results) == 1
    assert results[0].qualified_name == "app.main"


def test_find_class_returns_none_when_no_match():
    driver = FakeDriver(canned_results=[FakeResult([])])
    retriever = Neo4jGraphRetriever(driver)

    assert retriever.find_class("NonexistentClass") is None


def test_find_class_returns_class_node_when_found():
    driver = FakeDriver(canned_results=[FakeResult([{"cls": {
        "id": "class:app.planner.planner.Planner", "name": "Planner",
        "qualified_name": "app.planner.planner.Planner", "path": "app/planner/planner.py",
        "start_line": 40, "end_line": 100,
    }}])])
    retriever = Neo4jGraphRetriever(driver)

    result = retriever.find_class("Planner")

    assert isinstance(result, ClassNode)
    assert result.qualified_name == "app.planner.planner.Planner"
    assert result.start_line == 40