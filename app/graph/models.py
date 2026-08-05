"""
Graph data models: typed representations of the schema in
docs/graph-schema.md. GraphBuilder produces these from AST parsing;
GraphRepository persists them to Neo4j; GraphRetriever returns them
from queries. None of these types know anything about Neo4j or Cypher
-- that's the whole point of keeping GraphBuilder testable without a
running database.
"""
from dataclasses import dataclass, field
from enum import Enum


class GraphEdgeType(str, Enum):
    CONTAINS = "contains"
    DEFINES = "defines"
    IMPORTS = "imports"
    CALLS = "calls"


@dataclass(frozen=True)
class SourceFile:
    """
    In-memory source file: path + raw text. GraphBuilder operates on a
    list of these rather than a filesystem path, because GitHub
    ingestion (app/ingestion/github_connector.py) fetches file content
    directly into memory and never writes to disk -- requiring a
    repo_path would force an unnecessary temp-directory write just to
    satisfy the interface. This also keeps GraphBuilder trivially
    testable: real Python source as a plain string, no filesystem
    needed at all.
    """
    path: str
    text: str


@dataclass(frozen=True)
class RepositoryNode:
    id: str
    name: str
    source_ref: str


@dataclass(frozen=True)
class DirectoryNode:
    id: str
    path: str


@dataclass(frozen=True)
class ModuleNode:
    """
    Named Module, not File -- Python's import system resolves at the
    module level, not the file level (see docs/graph-schema.md).
    """
    id: str
    name: str
    qualified_name: str
    path: str
    language: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class ClassNode:
    id: str
    name: str
    qualified_name: str
    path: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class FunctionNode:
    id: str
    name: str
    qualified_name: str
    signature: str
    path: str
    start_line: int
    end_line: int


# Union of all node types -- GraphBuilder produces a mix, GraphRepository
# persists a mix, GraphRetriever returns a mix depending on the query.
GraphNode = RepositoryNode | DirectoryNode | ModuleNode | ClassNode | FunctionNode


@dataclass(frozen=True)
class GraphEdge:
    edge_type: GraphEdgeType
    source_id: str
    target_id: str


@dataclass(frozen=True)
class ParsedGraph:
    """The full output of GraphBuilder for one repository -- everything GraphRepository needs to persist."""
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)


@dataclass(frozen=True)
class GraphBuildResult:
    """
    What GraphBuilder.build() actually returns -- wraps ParsedGraph with
    build metadata. Added instead of returning a bare ParsedGraph so
    that "17 files skipped, 2 syntax errors, 428 files parsed" is
    reportable without a future interface change; GraphRepository still
    only ever consumes `.graph`, so persistence code doesn't need to
    know this metadata exists.
    """
    graph: ParsedGraph
    warnings: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)