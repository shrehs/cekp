"""
Neo4j driver singleton, mirroring vector_store.py's pattern for the
Qdrant client -- one shared driver instance, lazily constructed on
first use.
"""
from neo4j import Driver, GraphDatabase

from app.core.config import settings

_driver: Driver | None = None


def get_driver() -> Driver:
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            connection_timeout=settings.neo4j_connection_timeout_seconds,
            max_transaction_retry_time=settings.neo4j_max_transaction_retry_seconds,
        )
    return _driver