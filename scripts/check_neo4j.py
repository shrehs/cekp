"""
Standalone Neo4j connectivity check. Deliberately does NOT go through
GraphRepository -- that has no real implementation yet (still just an
ABC). This just confirms the driver can connect and run a query,
before any Cypher-writing code gets built against it.

Usage:
  docker compose -f docker/docker-compose.yml exec api python scripts/check_neo4j.py
"""
import sys

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError

sys.path.insert(0, "/app")
from app.core.config import settings  # noqa: E402


def main():
    print(f"Connecting to {settings.neo4j_uri} as user '{settings.neo4j_user}'...")

    try:
        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        driver.verify_connectivity()
        print("PASS  Driver connected and verified connectivity.")
    except ServiceUnavailable as e:
        print(f"FAIL  Could not reach Neo4j at {settings.neo4j_uri}: {e}")
        print("      Is the neo4j container up? docker compose -f docker/docker-compose.yml ps")
        sys.exit(1)
    except AuthError as e:
        print(f"FAIL  Connected, but authentication failed: {e}")
        print("      Check CEKP_NEO4J_USER / CEKP_NEO4J_PASSWORD match the neo4j container's NEO4J_AUTH.")
        sys.exit(1)

    try:
        with driver.session() as session:
            result = session.run("RETURN 1 AS value")
            value = result.single()["value"]
            if value == 1:
                print("PASS  Query executed successfully (RETURN 1 -> 1).")
            else:
                print(f"FAIL  Query returned unexpected value: {value}")
                sys.exit(1)
    except Exception as e:
        print(f"FAIL  Connected, but query execution failed: {e}")
        sys.exit(1)
    finally:
        driver.close()

    print("\nNeo4j is reachable and responding to queries. Ready for GraphRepository implementation.")


if __name__ == "__main__":
    main()