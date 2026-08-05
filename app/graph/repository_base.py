"""
GraphRepository: persists a ParsedGraph to Neo4j. The only place
Cypher CREATE/MERGE statements should live -- GraphBuilder never
touches Neo4j, GraphRetriever never writes.

Not implemented yet -- interface only, defined before the Neo4j
persistence logic itself gets written (see docs/graph-schema.md,
"Interface separation").
"""
from abc import ABC, abstractmethod

from app.graph.models import ParsedGraph


class GraphRepository(ABC):
    @abstractmethod
    def persist(self, graph: ParsedGraph) -> None:
        """
        Write every node and edge in graph to Neo4j. Should be
        idempotent for a given repository -- re-ingesting the same
        repo should not create duplicate nodes (MERGE, not CREATE, on
        whatever uniquely identifies each node -- id or qualified_name).
        """
        raise NotImplementedError

    @abstractmethod
    def clear_repository(self, repo_id: str) -> None:
        """
        Remove all nodes/edges belonging to a given repository. Needed
        so re-ingesting a repo after its source has changed doesn't
        leave stale nodes (a deleted function whose node never gets
        removed) alongside the new, correct ones.
        """
        raise NotImplementedError