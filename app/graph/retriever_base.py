"""
GraphRetriever: runs read-only Cypher queries against what
GraphRepository persisted. The only place Cypher MATCH statements
should live -- GraphRetriever never writes.

Method set matches "Example queries this graph can answer" in
docs/graph-schema.md exactly, so there's no drift between what the
schema doc promises and what the interface actually exposes.

Every string identifier parameter below accepts EITHER a fully
qualified name ("app.planner.planner") OR a short/partial name
("planner"), resolved internally (exact match first, then suffix
match on qualified_name, e.g. ".planner"). This is deliberate: a real
GraphStrategy extracts tokens from free-text questions ("which
modules import auth?"), not full dotted qualified names -- pushing
fuzzy resolution into the retriever means GraphStrategy doesn't need
its own matching logic, and the resolution strategy lives in exactly
one place. If a short name matches more than one node, implementations
should return/use the first match by a deterministic ordering (e.g.
qualified_name) rather than silently picking arbitrarily -- ambiguity
should be visible in behavior, not hidden by nondeterminism.
"""
from abc import ABC, abstractmethod

from app.graph.models import ClassNode, FunctionNode, ModuleNode


class GraphRetriever(ABC):
    @abstractmethod
    def get_module_imports(self, module_reference: str) -> list[ModuleNode]:
        """What does this module import? (outgoing IMPORTS edges). Same-repo modules only (v1 limitation)."""
        raise NotImplementedError

    @abstractmethod
    def get_importers_of(self, module_reference: str) -> list[ModuleNode]:
        """
        Which modules import this one? (incoming IMPORTS edges -- the
        reverse of get_module_imports). 'Which modules import auth?'
        needs this direction, not the forward one.
        """
        raise NotImplementedError

    @abstractmethod
    def get_functions_defined_in(self, module_reference: str) -> list[FunctionNode]:
        """What functions are defined in this module?"""
        raise NotImplementedError

    @abstractmethod
    def get_classes_defined_in(self, module_reference: str) -> list[ClassNode]:
        """What classes are defined in this module?"""
        raise NotImplementedError

    @abstractmethod
    def find_function(self, function_reference: str) -> FunctionNode | None:
        """
        'Show me authenticate()' -- resolve straight to its node (path
        + start_line/end_line), not just confirm it exists somewhere.
        """
        raise NotImplementedError

    @abstractmethod
    def find_class(self, class_reference: str) -> ClassNode | None:
        """
        'Where is HTTPAdapter defined?' -- the class counterpart to
        find_function. Needed because "where is X defined" doesn't
        know in advance whether X is a function or a class.
        """
        raise NotImplementedError

    @abstractmethod
    def get_callers_of(self, function_reference: str) -> list[FunctionNode]:
        """
        What calls this function? Same-file call resolution only in
        v1 (see docs/graph-schema.md limitations) -- do not attempt
        cross-file symbol resolution here; that's a real static
        analysis problem, deliberately deferred.
        """
        raise NotImplementedError