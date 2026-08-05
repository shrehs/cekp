"""
Neo4jGraphRepository: the real GraphRepository implementation. Every
Cypher CREATE/MERGE statement in this codebase lives here --
GraphBuilder never touches Neo4j, GraphRetriever (once it exists)
never writes.

Design notes, since these were deliberate choices worth being explicit
about:

- No APOC. Edge types are a small, closed set (CONTAINS/DEFINES/
  IMPORTS/CALLS), so a literal relationship keyword per Cypher
  statement (one statement per GraphEdgeType present in a given
  persist() call) is simpler and safer than dynamic relationship types
  via apoc.merge.relationship -- no plugin dependency, no string
  injection surface (the keyword always comes from our own closed
  enum, never from external input).

- `SET n += row` instead of listing fields per node type. Each row is
  built via dataclasses.asdict() on the actual node, so this one
  Cypher pattern works identically for all five node types --
  RepositoryNode/DirectoryNode/ModuleNode/ClassNode/FunctionNode --
  without hardcoding field lists per label. Adding a field to a node
  dataclass flows through automatically.

- Edges are matched by id WITHOUT a label (`MATCH (a {id: ...})`, not
  `MATCH (a:Module {id: ...})`). This is correct -- ids are globally
  unique across labels via their type-prefixed scheme ("module:...",
  "class:...", "function:...:L<line>") -- but not index-optimal
  without a label hint, since Neo4j's uniqueness constraints (created
  in create_constraints()) are label-scoped. Acceptable for v1 repo
  sizes; worth revisiting with a label lookup pass if persist() ever
  becomes a bottleneck on large repos.

- Node upserts and edge upserts, batched via UNWIND, happen in ONE
  execute_write transaction per persist() call -- not the naive
  per-row session.run() loop that would need a later "batch
  transactions" refactor. There's no benefit to writing the slow
  version first here; UNWIND is the correct approach from the start.

Untested against a live Neo4j by Claude -- this sandbox has no Neo4j
and no `neo4j` driver installed. The Python-side logic (grouping nodes
by label, grouping edges by type, row shapes) IS verified for real via
tests/test_neo4j_repository.py using a fake driver that records what
Cypher/params would have been sent, without executing anything. The
actual Cypher semantics against a real database are verified only by
scripts/validate_neo4j_repository.py, which you need to run yourself.
"""
import dataclasses
from collections import defaultdict

from app.graph.models import (
    ClassNode,
    DirectoryNode,
    FunctionNode,
    GraphEdgeType,
    ModuleNode,
    ParsedGraph,
    RepositoryNode,
)
from app.graph.repository_base import GraphRepository

NODE_LABELS = {
    RepositoryNode: "Repository",
    DirectoryNode: "Directory",
    ModuleNode: "Module",
    ClassNode: "Class",
    FunctionNode: "Function",
}


class Neo4jGraphRepository(GraphRepository):
    def __init__(self, driver):
        """
        driver: a neo4j.Driver (or anything satisfying the same
        .session() -> context manager with .execute_write(fn)
        interface -- see tests/test_neo4j_repository.py's FakeDriver
        for what that surface actually needs to be).
        """
        self._driver = driver

    def create_constraints(self) -> None:
        def _create(tx):
            for label in NODE_LABELS.values():
                tx.run(
                    f"CREATE CONSTRAINT {label.lower()}_id IF NOT EXISTS "
                    f"FOR (n:{label}) REQUIRE n.id IS UNIQUE"
                )

        with self._driver.session() as session:
            session.execute_write(_create)

    def persist(self, graph: ParsedGraph) -> None:
        nodes_by_label: dict[str, list[dict]] = defaultdict(list)
        for node in graph.nodes:
            label = NODE_LABELS.get(type(node))
            if label is None:
                continue  # defensive -- every GraphNode variant is mapped above
            nodes_by_label[label].append(dataclasses.asdict(node))

        edges_by_type: dict[GraphEdgeType, list[dict]] = defaultdict(list)
        for edge in graph.edges:
            edges_by_type[edge.edge_type].append(
                {"source_id": edge.source_id, "target_id": edge.target_id}
            )

        def _write(tx):
            # Nodes first -- edges reference node ids that must already exist.
            for label, rows in nodes_by_label.items():
                tx.run(
                    f"""
                    UNWIND $rows AS row
                    MERGE (n:{label} {{id: row.id}})
                    SET n += row
                    """,
                    rows=rows,
                )
            for edge_type, rows in edges_by_type.items():
                tx.run(
                    f"""
                    UNWIND $rows AS row
                    MATCH (a {{id: row.source_id}})
                    MATCH (b {{id: row.target_id}})
                    MERGE (a)-[:{edge_type.value.upper()}]->(b)
                    """,
                    rows=rows,
                )

        with self._driver.session() as session:
            session.execute_write(_write)

    def clear_repository(self, repo_id: str) -> None:
        def _clear(tx):
            tx.run(
                """
                MATCH (r:Repository {id: $repo_id})
                OPTIONAL MATCH (r)-[:CONTAINS|DEFINES*0..]->(n)
                DETACH DELETE n, r
                """,
                repo_id=f"repo:{repo_id}",
            )
            # CONTAINS|DEFINES covers Repository->Directory->Module (CONTAINS)
            # AND Module/Class->Class/Function (DEFINES) in one traversal --
            # a CONTAINS-only pattern would miss Class/Function nodes
            # entirely, since those hang off DEFINES, not CONTAINS.
            # IMPORTS/CALLS edges need no separate deletion -- DETACH DELETE
            # removes every relationship attached to a deleted node
            # regardless of type.

        with self._driver.session() as session:
            session.execute_write(_clear)