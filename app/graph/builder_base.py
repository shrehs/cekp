"""
GraphBuilder: converts source code (via AST) into a ParsedGraph.
Deliberately knows nothing about Neo4j or Cypher -- that separation is
what makes this fully unit-testable against real Python source with
zero Docker/Neo4j dependency (same principle as the rest of this
codebase: strategies, the intent classifier, etc. are all tested
without live infrastructure wherever the logic allows it).

Takes a list of SourceFile (path + text), not a filesystem path.
GitHub ingestion (app/ingestion/github_connector.py) fetches file
content directly into memory and never writes to disk -- requiring a
repo_path would force an unnecessary temp-directory write just to
satisfy this interface. Revised before any real implementation
existed, so this cost nothing; see docs/graph-schema.md's Architecture
Freeze Policy reference -- this qualifies as an implementation-driven
correction, not speculative redesign.
"""
from abc import ABC, abstractmethod

from app.graph.models import GraphBuildResult, SourceFile


class GraphBuilder(ABC):
    @abstractmethod
    def build(self, files: list[SourceFile], repo_id: str, repo_name: str, source_ref: str) -> GraphBuildResult:
        """
        Parse all ingestible files in `files` and return a
        GraphBuildResult: the ParsedGraph (Repository/Directory/Module/
        Class/Function nodes plus CONTAINS/DEFINES/IMPORTS/CALLS edges,
        per docs/graph-schema.md) plus build metadata -- which files
        were skipped (non-Python) and which failed to parse (syntax
        errors), so that information is reportable without another
        interface change later.

        Must not raise for individual unparseable files -- record them
        in parse_errors and skip them (same principle as
        app/ingestion/github_connector.py skipping unreadable files
        rather than failing the whole ingest). Should raise only for
        genuine failures (files is malformed input, etc).
        """
        raise NotImplementedError