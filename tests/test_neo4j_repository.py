"""
Tests for Neo4jGraphRepository using a FakeDriver that records every
Cypher statement + params passed to tx.run(), instead of executing
anything. This verifies the Python-side logic genuinely, right now,
without a live Neo4j: correct node/edge grouping, correct row shapes,
correct relationship keywords, correct constraint statements.

What this does NOT verify: that the Cypher is actually semantically
correct against a real database (MERGE behaving idempotently, the
constraint syntax being valid, etc.) -- that's
scripts/validate_neo4j_repository.py's job, which needs a live Neo4j.
"""
from app.graph.models import (
    ClassNode,
    DirectoryNode,
    FunctionNode,
    GraphEdge,
    GraphEdgeType,
    ModuleNode,
    ParsedGraph,
    RepositoryNode,
)
from app.graph.neo4j_repository import Neo4jGraphRepository


class FakeTransaction:
    def __init__(self):
        self.queries: list[tuple[str, dict]] = []  # (query_string, params)

    def run(self, query, **params):
        self.queries.append((query, params))


class FakeSession:
    def __init__(self):
        self.tx = FakeTransaction()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute_write(self, fn):
        return fn(self.tx)


class FakeDriver:
    def __init__(self):
        self.last_session = None

    def session(self):
        self.last_session = FakeSession()
        return self.last_session


def _sample_graph() -> ParsedGraph:
    repo = RepositoryNode(id="repo:cekp", name="cekp", source_ref="local/cekp")
    directory = DirectoryNode(id="dir:app", path="app")
    module = ModuleNode(
        id="module:app.main", name="main", qualified_name="app.main",
        path="app/main.py", language="python", start_line=1, end_line=10,
    )
    cls = ClassNode(
        id="class:app.core.config.Settings", name="Settings",
        qualified_name="app.core.config.Settings", path="app/core/config.py",
        start_line=5, end_line=20,
    )
    fn = FunctionNode(
        id="function:app.main.health:L8", name="health",
        qualified_name="app.main.health", signature="def health()",
        path="app/main.py", start_line=8, end_line=9,
    )
    edges = [
        GraphEdge(GraphEdgeType.CONTAINS, "repo:cekp", "dir:app"),
        GraphEdge(GraphEdgeType.CONTAINS, "dir:app", "module:app.main"),
        GraphEdge(GraphEdgeType.DEFINES, "module:app.main", "function:app.main.health:L8"),
        GraphEdge(GraphEdgeType.IMPORTS, "module:app.main", "class:app.core.config.Settings"),
    ]
    return ParsedGraph(nodes=[repo, directory, module, cls, fn], edges=edges)


def test_create_constraints_issues_one_statement_per_label():
    driver = FakeDriver()
    repo = Neo4jGraphRepository(driver)

    repo.create_constraints()

    queries = [q for q, _ in driver.last_session.tx.queries]
    assert len(queries) == 5  # Repository, Directory, Module, Class, Function
    assert any("FOR (n:Module)" in q and "REQUIRE n.id IS UNIQUE" in q for q in queries)
    assert any("FOR (n:Function)" in q for q in queries)
    assert all("IF NOT EXISTS" in q for q in queries)


def test_persist_groups_nodes_by_label_with_correct_row_shape():
    driver = FakeDriver()
    repo = Neo4jGraphRepository(driver)

    repo.persist(_sample_graph())

    queries = driver.last_session.tx.queries
    module_query = next((q, p) for q, p in queries if "MERGE (n:Module" in q)
    query_str, params = module_query

    assert "UNWIND $rows AS row" in query_str
    assert "SET n += row" in query_str
    assert len(params["rows"]) == 1
    assert params["rows"][0]["qualified_name"] == "app.main"
    assert params["rows"][0]["id"] == "module:app.main"


def test_persist_writes_nodes_before_edges():
    driver = FakeDriver()
    repo = Neo4jGraphRepository(driver)

    repo.persist(_sample_graph())

    queries = [q for q, _ in driver.last_session.tx.queries]
    node_query_indices = [i for i, q in enumerate(queries) if "MERGE (n:" in q]
    edge_query_indices = [i for i, q in enumerate(queries) if "MERGE (a)-[:" in q]

    assert node_query_indices  # some node queries exist
    assert edge_query_indices  # some edge queries exist
    assert max(node_query_indices) < min(edge_query_indices)  # ALL node writes before ANY edge write


def test_persist_groups_edges_by_type_with_correct_relationship_keyword():
    driver = FakeDriver()
    repo = Neo4jGraphRepository(driver)

    repo.persist(_sample_graph())

    queries = driver.last_session.tx.queries
    imports_query = next((q, p) for q, p in queries if "MERGE (a)-[:IMPORTS]->(b)" in q)
    query_str, params = imports_query

    assert len(params["rows"]) == 1
    assert params["rows"][0] == {"source_id": "module:app.main", "target_id": "class:app.core.config.Settings"}


def test_persist_edge_match_is_label_agnostic():
    """
    Confirms the deliberate design choice: edge MATCH clauses don't
    specify a label, since ids are globally unique across labels via
    the type-prefixed id scheme. If this ever changes, a lot of
    queries would need updating, so worth a test that pins the
    current, intentional shape.
    """
    driver = FakeDriver()
    repo = Neo4jGraphRepository(driver)

    repo.persist(_sample_graph())

    edge_queries = [q for q, _ in driver.last_session.tx.queries if "MERGE (a)-[:" in q]
    for q in edge_queries:
        assert "MATCH (a {id: row.source_id})" in q
        assert "MATCH (b {id: row.target_id})" in q
        # explicitly NOT "MATCH (a:SomeLabel {id: ...})"


def test_clear_repository_prefixes_repo_id_and_traverses_contains_and_defines():
    driver = FakeDriver()
    repo = Neo4jGraphRepository(driver)

    repo.clear_repository("cekp")

    query_str, params = driver.last_session.tx.queries[0]
    assert params["repo_id"] == "repo:cekp"  # prefixed, matching PythonAstGraphBuilder's id() scheme
    assert "CONTAINS|DEFINES" in query_str  # both traversed -- DEFINES-only children would be missed by CONTAINS alone
    assert "DETACH DELETE" in query_str


def test_empty_graph_produces_no_queries():
    """Persisting an empty graph shouldn't blow up or emit pointless empty UNWIND statements."""
    driver = FakeDriver()
    repo = Neo4jGraphRepository(driver)

    repo.persist(ParsedGraph())

    assert driver.last_session.tx.queries == []