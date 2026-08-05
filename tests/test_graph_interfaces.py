"""
Contract tests for the graph interfaces (app/graph/). These aren't
testing real graph logic -- there isn't any yet, per docs/graph-schema.md's
"Interface separation" (AST parsing, Neo4j persistence, and Cypher
queries are all future work). What's being tested here is that the
ABCs actually enforce their contracts, and that a minimal concrete
implementation satisfying each interface is possible -- same
philosophy as testing RetrievalStrategy's contract before any real
strategy existed.
"""
import pytest

from app.graph.builder_base import GraphBuilder
from app.graph.models import (
    ClassNode,
    DirectoryNode,
    FunctionNode,
    GraphBuildResult,
    GraphEdge,
    GraphEdgeType,
    ModuleNode,
    ParsedGraph,
    RepositoryNode,
)
from app.graph.repository_base import GraphRepository
from app.graph.retriever_base import GraphRetriever


def test_graph_builder_cannot_be_instantiated_without_implementing_build():
    with pytest.raises(TypeError):
        GraphBuilder()


def test_graph_repository_cannot_be_instantiated_without_implementing_all_methods():
    with pytest.raises(TypeError):
        GraphRepository()


def test_graph_retriever_cannot_be_instantiated_without_implementing_all_methods():
    with pytest.raises(TypeError):
        GraphRetriever()


def test_minimal_concrete_builder_satisfies_the_interface():
    class MinimalBuilder(GraphBuilder):
        def build(self, files, repo_id, repo_name, source_ref):
            return GraphBuildResult(graph=ParsedGraph())

    builder = MinimalBuilder()
    result = builder.build([], "repo-1", "example", "owner/example")
    assert isinstance(result, GraphBuildResult)
    assert result.graph.nodes == []
    assert result.graph.edges == []
    assert result.skipped_files == []
    assert result.parse_errors == []


def test_minimal_concrete_repository_satisfies_the_interface():
    class MinimalRepository(GraphRepository):
        def create_constraints(self):
            pass

        def persist(self, graph):
            pass

        def clear_repository(self, repo_id):
            pass

    repo = MinimalRepository()
    repo.create_constraints()        # should not raise
    repo.persist(ParsedGraph())      # should not raise
    repo.clear_repository("repo-1")  # should not raise


def test_minimal_concrete_retriever_satisfies_the_interface():
    class MinimalRetriever(GraphRetriever):
        def get_module_imports(self, module_reference):
            return []

        def get_importers_of(self, module_reference):
            return []

        def get_functions_defined_in(self, module_reference):
            return []

        def get_classes_defined_in(self, module_reference):
            return []

        def find_function(self, function_reference):
            return None

        def find_class(self, class_reference):
            return None

        def get_callers_of(self, function_reference):
            return []

    retriever = MinimalRetriever()
    assert retriever.get_module_imports("app.main") == []
    assert retriever.find_function("app.main.health") is None


def test_parsed_graph_holds_a_mix_of_node_types_and_typed_edges():
    """Confirms the data model actually matches docs/graph-schema.md's shape."""
    repo = RepositoryNode(id="repo-1", name="example", source_ref="owner/example")
    directory = DirectoryNode(id="dir-1", path="app")
    module = ModuleNode(
        id="mod-1", name="main", qualified_name="app.main", path="app/main.py",
        language="python", start_line=1, end_line=40,
    )
    cls = ClassNode(
        id="cls-1", name="Settings", qualified_name="app.core.config.Settings",
        path="app/core/config.py", start_line=10, end_line=30,
    )
    fn = FunctionNode(
        id="fn-1", name="health", qualified_name="app.main.health",
        signature="def health() -> dict", path="app/main.py", start_line=25, end_line=27,
    )
    edge = GraphEdge(edge_type=GraphEdgeType.CONTAINS, source_id="repo-1", target_id="dir-1")

    graph = ParsedGraph(nodes=[repo, directory, module, cls, fn], edges=[edge])

    assert len(graph.nodes) == 5
    assert graph.edges[0].edge_type == GraphEdgeType.CONTAINS
    # Every node type the schema doc promises is actually representable:
    assert isinstance(graph.nodes[2], ModuleNode)
    assert graph.nodes[2].qualified_name == "app.main"  # not just "name" -- avoids collisions