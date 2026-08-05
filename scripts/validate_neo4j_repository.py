"""
Validates Neo4jGraphRepository against a REAL Neo4j instance. This is
the confirmation that the Cypher in neo4j_repository.py is actually
correct -- tests/test_neo4j_repository.py only proves the Python-side
query construction is right, using a fake driver that never touches a
real database.

The core check: persist the same graph TWICE. Node count and edge
count must be IDENTICAL after both runs -- that's what proves MERGE +
the uniqueness constraints + the stable line-number-disambiguated ids
are actually working together correctly, not just individually.

Usage:
  docker compose -f docker/docker-compose.yml exec api python scripts/validate_neo4j_repository.py
  docker compose -f docker/docker-compose.yml exec api python scripts/validate_neo4j_repository.py --local-path /app/data/requests --repo-id requests
"""
import argparse
import os
import sys
import time

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for candidate in ("/app", _REPO_ROOT):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from neo4j import GraphDatabase  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.graph.ast_builder import PythonAstGraphBuilder  # noqa: E402
from app.graph.models import SourceFile  # noqa: E402
from app.graph.neo4j_repository import Neo4jGraphRepository  # noqa: E402

SKIP_DIRS = {".git", "__pycache__", "node_modules", "venv", ".venv", "build", "dist", "egg-info"}


def load_local_files(local_path: str) -> list[SourceFile]:
    files = []
    for root, dirs, filenames in os.walk(local_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.endswith(".egg-info")]
        for filename in filenames:
            if filename.endswith(".py"):
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, local_path).replace(os.sep, "/")
                with open(full_path, encoding="utf-8", errors="replace") as f:
                    files.append(SourceFile(path=rel_path, text=f.read()))
    return files


def count_repo_nodes_and_edges(session, repo_id: str) -> tuple[int, int]:
    """
    Scoped to this repo's own subgraph (Repository -> CONTAINS|DEFINES* ->
    everything it owns), not a global count -- so this is meaningful even
    if the database has other repos' data in it from previous runs.
    """
    node_result = session.run(
        """
        MATCH (r:Repository {id: $repo_id})
        OPTIONAL MATCH (r)-[:CONTAINS|DEFINES*0..]->(n)
        RETURN count(DISTINCT n) AS node_count
        """,
        repo_id=f"repo:{repo_id}",
    )
    node_count = node_result.single()["node_count"]

    edge_result = session.run(
        """
        MATCH (r:Repository {id: $repo_id})
        OPTIONAL MATCH (r)-[:CONTAINS|DEFINES*0..]->(n)
        WITH r, collect(DISTINCT n) AS descendants
        WITH [r] + descendants AS repo_nodes
        UNWIND repo_nodes AS a
        MATCH (a)-[rel]->(b)
        WHERE b IN repo_nodes
        RETURN count(DISTINCT rel) AS edge_count
        """,
        repo_id=f"repo:{repo_id}",
    )
    edge_record = edge_result.single()
    edge_count = edge_record["edge_count"] if edge_record else 0

    return node_count, edge_count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-path", default=os.path.join(_REPO_ROOT, "app"))
    parser.add_argument("--repo-id", default="cekp-validation")
    parser.add_argument("--keep", action="store_true", help="don't clear_repository() at the end")
    args = parser.parse_args()

    print(f"Loading .py files from {args.local_path}...")
    files = load_local_files(args.local_path)
    print(f"Found {len(files)} Python files")

    print("Building graph via PythonAstGraphBuilder...")
    build_result = PythonAstGraphBuilder().build(
        files, repo_id=args.repo_id, repo_name=args.repo_id, source_ref=args.local_path
    )
    graph = build_result.graph
    print(f"Built {len(graph.nodes)} nodes, {len(graph.edges)} edges "
          f"({len(build_result.skipped_files)} skipped, {len(build_result.parse_errors)} parse errors)")

    driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
    repository = Neo4jGraphRepository(driver)

    print("\nClearing any pre-existing data for this repo-id (clean slate for the idempotency check)...")
    repository.clear_repository(args.repo_id)

    print("Creating constraints...")
    repository.create_constraints()

    print("\n=== Persist #1 ===")
    t0 = time.time()
    repository.persist(graph)
    print(f"Completed in {time.time() - t0:.3f}s")

    with driver.session() as session:
        nodes_1, edges_1 = count_repo_nodes_and_edges(session, args.repo_id)
    print(f"Nodes: {nodes_1}, Edges: {edges_1}")

    print("\n=== Persist #2 (same graph, unmodified) ===")
    t0 = time.time()
    repository.persist(graph)
    print(f"Completed in {time.time() - t0:.3f}s")

    with driver.session() as session:
        nodes_2, edges_2 = count_repo_nodes_and_edges(session, args.repo_id)
    print(f"Nodes: {nodes_2}, Edges: {edges_2}")

    print("\n=== Idempotency check ===")
    if nodes_1 == nodes_2 and edges_1 == edges_2:
        print(f"PASS  Counts identical after re-persisting: {nodes_1} nodes, {edges_1} edges.")
        idempotent = True
    else:
        print(f"FAIL  Counts changed: nodes {nodes_1} -> {nodes_2}, edges {edges_1} -> {edges_2}")
        print("      This means MERGE is not behaving idempotently -- check constraint creation")
        print("      succeeded, and that node/edge ids are genuinely stable across builds.")
        idempotent = False

    print("\n=== Sample query: node counts by label ===")
    with driver.session() as session:
        result = session.run(
            """
            MATCH (r:Repository {id: $repo_id})
            OPTIONAL MATCH (r)-[:CONTAINS|DEFINES*0..]->(n)
            RETURN labels(n) AS labels, count(*) AS count
            ORDER BY count DESC
            """,
            repo_id=f"repo:{args.repo_id}",
        )
        for record in result:
            print(f"  {record['labels']}: {record['count']}")

    print("\n=== Sample query: edge counts by relationship type ===")
    print("(catches an accidentally-missing relationship type immediately -- e.g. if")
    print(" CALLS silently never got persisted, this would show CALLS: 0 or absent entirely)")
    with driver.session() as session:
        result = session.run(
            """
            MATCH (r:Repository {id: $repo_id})
            OPTIONAL MATCH (r)-[:CONTAINS|DEFINES*0..]->(n)
            WITH r, collect(DISTINCT n) AS descendants
            WITH [r] + descendants AS repo_nodes
            UNWIND repo_nodes AS a
            MATCH (a)-[rel]->(b)
            WHERE b IN repo_nodes
            RETURN type(rel) AS rel_type, count(*) AS count
            ORDER BY count DESC
            """,
            repo_id=f"repo:{args.repo_id}",
        )
        for record in result:
            print(f"  {record['rel_type']}: {record['count']}")

    print("\n=== Sample query: an actual traversal (proves the graph is queryable, not just structurally sound) ===")
    with driver.session() as session:
        # Pick any Module this repo actually has and show what it DEFINES,
        # rather than hardcoding a qualified_name that may not exist in
        # whatever --local-path was parsed.
        sample = session.run(
            """
            MATCH (r:Repository {id: $repo_id})-[:CONTAINS|DEFINES*0..]->(m:Module)
            RETURN m.qualified_name AS qn LIMIT 1
            """,
            repo_id=f"repo:{args.repo_id}",
        ).single()

        if sample:
            qn = sample["qn"]
            print(f"  Querying: what does '{qn}' define?")
            defines_result = session.run(
                "MATCH (m:Module {qualified_name: $qn})-[:DEFINES]->(defined) "
                "RETURN labels(defined) AS labels, defined.qualified_name AS qn LIMIT 10",
                qn=qn,
            )
            rows = list(defines_result)
            if rows:
                for row in rows:
                    print(f"    {row['labels']} {row['qn']}")
            else:
                print(f"    (nothing -- '{qn}' defines no classes/functions directly, which can be correct for a small/import-only module)")
        else:
            print("  (no Module nodes found for this repo -- nothing to traverse)")

    if not args.keep:
        print(f"\nClearing repo-id '{args.repo_id}' (pass --keep to leave data for Neo4j Browser inspection)...")
        repository.clear_repository(args.repo_id)
    else:
        print(f"\nData kept. Inspect at http://localhost:7474 -- e.g.:")
        print(f"  MATCH (r:Repository {{id: 'repo:{args.repo_id}'}})-[:CONTAINS|DEFINES*0..]->(n) RETURN r, n LIMIT 200")

    driver.close()
    sys.exit(0 if idempotent else 1)


if __name__ == "__main__":
    main()