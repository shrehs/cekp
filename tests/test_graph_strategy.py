"""
Tests for GraphStrategy's sub-classification and dispatch logic, using
a FakeRetriever injected via the constructor -- never touches the
lazy default (Neo4j) path. Verifies: which retriever method gets
called for which question phrasing, that the extracted reference token
is correct, confidence/outcome assignment, and that a retriever
exception becomes StrategyOutcome.ERROR rather than propagating.
"""
from app.graph.models import ClassNode, FunctionNode, ModuleNode
from app.graph.retriever_base import GraphRetriever
from app.planner.context import PlannerContext
from app.planner.enums import StrategyOutcome
from app.planner.strategies import GraphStrategy


class FakeRetriever(GraphRetriever):
    """Records every call made to it; returns pre-configured results per method."""

    def __init__(self, results: dict[str, object] | None = None, raises: bool = False):
        self.results = results or {}
        self.raises = raises
        self.calls: list[tuple[str, str]] = []  # (method_name, reference)

    def _record(self, method_name: str, reference: str):
        self.calls.append((method_name, reference))
        if self.raises:
            raise RuntimeError("simulated Neo4j failure")
        return self.results.get(method_name, [] if method_name != "find_function" and method_name != "find_class" else None)

    def get_module_imports(self, module_reference):
        return self._record("get_module_imports", module_reference)

    def get_importers_of(self, module_reference):
        return self._record("get_importers_of", module_reference)

    def get_functions_defined_in(self, module_reference):
        return self._record("get_functions_defined_in", module_reference)

    def get_classes_defined_in(self, module_reference):
        return self._record("get_classes_defined_in", module_reference)

    def find_function(self, function_reference):
        return self._record("find_function", function_reference)

    def find_class(self, class_reference):
        return self._record("find_class", class_reference)

    def get_callers_of(self, function_reference):
        return self._record("get_callers_of", function_reference)

    def get_methods_of_class(self, class_reference: str, method_name: str):
        # Record with a special marker to capture both class and method
        self.calls.append(("get_methods_of_class", f"{method_name}:{class_reference}"))
        if self.raises:
            raise RuntimeError("simulated Neo4j failure")
        return self.results.get("get_methods_of_class", None)


def _ctx(query: str) -> PlannerContext:
    return PlannerContext(query=query)


def test_which_modules_import_routes_to_get_importers_of():
    module = ModuleNode(id="module:app.main", name="main", qualified_name="app.main",
                         path="app/main.py", language="python", start_line=1, end_line=10)
    retriever = FakeRetriever(results={"get_importers_of": [module]})
    strategy = GraphStrategy(retriever=retriever)

    result = strategy.retrieve(_ctx("Which modules import auth?"))

    assert retriever.calls == [("get_importers_of", "auth")]
    assert result.outcome == StrategyOutcome.SUCCESS
    assert result.documents[0]["qualified_name"] == "app.main"


def test_what_does_x_import_routes_to_get_module_imports():
    module = ModuleNode(id="module:os", name="os", qualified_name="os",
                         path="os.py", language="python", start_line=1, end_line=1)
    retriever = FakeRetriever(results={"get_module_imports": [module]})
    strategy = GraphStrategy(retriever=retriever)

    result = strategy.retrieve(_ctx("What does app.main import?"))

    assert retriever.calls == [("get_module_imports", "app.main")]
    assert result.outcome == StrategyOutcome.SUCCESS


def test_which_functions_call_routes_to_get_callers_of_not_functions_defined_in():
    """The exact collision this was designed to avoid: 'functions' appearing in the query shouldn't trigger functions_defined_in."""
    fn = FunctionNode(id="function:app.main.on_startup:L5", name="on_startup",
                       qualified_name="app.main.on_startup", signature="def on_startup()",
                       path="app/main.py", start_line=5, end_line=6)
    retriever = FakeRetriever(results={"get_callers_of": [fn]})
    strategy = GraphStrategy(retriever=retriever)

    result = strategy.retrieve(_ctx("Which functions call health()?"))

    assert retriever.calls == [("get_callers_of", "health")]  # trailing () stripped
    assert result.outcome == StrategyOutcome.SUCCESS


def test_functions_defined_in_requires_defined_in_phrase():
    fn = FunctionNode(id="function:app.main.health:L8", name="health",
                       qualified_name="app.main.health", signature="def health()",
                       path="app/main.py", start_line=8, end_line=9)
    retriever = FakeRetriever(results={"get_functions_defined_in": [fn]})
    strategy = GraphStrategy(retriever=retriever)

    result = strategy.retrieve(_ctx("Which functions are defined in app.main?"))

    assert retriever.calls == [("get_functions_defined_in", "app.main")]
    assert result.outcome == StrategyOutcome.SUCCESS


def test_classes_defined_in():
    cls = ClassNode(id="class:app.core.config.Settings", name="Settings",
                     qualified_name="app.core.config.Settings", path="app/core/config.py",
                     start_line=10, end_line=30)
    retriever = FakeRetriever(results={"get_classes_defined_in": [cls]})
    strategy = GraphStrategy(retriever=retriever)

    result = strategy.retrieve(_ctx("What classes are defined in config?"))

    assert retriever.calls == [("get_classes_defined_in", "config")]
    assert result.documents[0]["type"] == "class"


def test_where_is_x_defined_tries_function_first_then_class():
    cls = ClassNode(id="class:app.planner.planner.Planner", name="Planner",
                     qualified_name="app.planner.planner.Planner", path="app/planner/planner.py",
                     start_line=40, end_line=100)
    retriever = FakeRetriever(results={"find_function": None, "find_class": cls})
    strategy = GraphStrategy(retriever=retriever)

    result = strategy.retrieve(_ctx("Where is Planner defined?"))

    assert retriever.calls == [("find_function", "Planner"), ("find_class", "Planner")]
    assert result.outcome == StrategyOutcome.SUCCESS
    assert result.documents[0]["type"] == "class"


def test_where_is_x_defined_stops_at_function_if_found_does_not_also_check_class():
    fn = FunctionNode(id="function:app.main.health:L8", name="health",
                       qualified_name="app.main.health", signature="def health()",
                       path="app/main.py", start_line=8, end_line=9)
    retriever = FakeRetriever(results={"find_function": fn})
    strategy = GraphStrategy(retriever=retriever)

    result = strategy.retrieve(_ctx("Where is health defined?"))

    assert retriever.calls == [("find_function", "health")]  # find_class never called
    assert result.documents[0]["type"] == "function"


def test_no_matching_sub_pattern_returns_low_confidence_not_not_implemented():
    """
    Once GraphStrategy is real, a question that doesn't match any
    sub-pattern is honestly "couldn't parse this," not "this capability
    doesn't exist" -- NOT_IMPLEMENTED is reserved for the latter.
    """
    retriever = FakeRetriever()
    strategy = GraphStrategy(retriever=retriever)

    result = strategy.retrieve(_ctx("asdkfjaslkdfj nonsense"))

    assert retriever.calls == []
    assert result.outcome == StrategyOutcome.LOW_CONFIDENCE
    assert result.confidence == 0.0


def test_matched_pattern_but_no_graph_results_is_low_confidence():
    retriever = FakeRetriever(results={"get_module_imports": []})
    strategy = GraphStrategy(retriever=retriever)

    result = strategy.retrieve(_ctx("What does nonexistent_module import?"))

    assert result.outcome == StrategyOutcome.LOW_CONFIDENCE
    assert result.documents == []


def test_retriever_exception_becomes_error_outcome_not_propagated():
    retriever = FakeRetriever(raises=True)
    strategy = GraphStrategy(retriever=retriever)

    result = strategy.retrieve(_ctx("What does app.main import?"))  # should not raise

    assert result.outcome == StrategyOutcome.ERROR
    assert "simulated Neo4j failure" in result.reasoning


def test_org_dependency_question_returns_not_implemented_not_low_confidence():
    """
    Regression test for a real consequence of making GraphStrategy real:
    without this check, an org-dependency question ("which services
    depend on X") would fall through to generic LOW_CONFIDENCE instead
    of the honest NOT_IMPLEMENTED -- silently erasing the distinction
    this project has maintained throughout (see docs/planner.md) between
    "this capability doesn't exist" and "ran, found nothing."
    """
    retriever = FakeRetriever()
    strategy = GraphStrategy(retriever=retriever)

    result = strategy.retrieve(_ctx("Which services depend on the auth service?"))

    assert retriever.calls == []  # never even attempts a graph query for this category
    assert result.outcome == StrategyOutcome.NOT_IMPLEMENTED
    assert result.confidence == 0.0


def test_find_method_of_class_pattern_method_of_classname():
    """
    Regression test for class->method resolution bug: "Find the __init__ method of Neo4jGraphRepository"
    should not search for a global __init__ function (which may match many nodes and timeout),
    but rather search specifically for __init__ within the context of Neo4jGraphRepository class.
    """
    method = FunctionNode(id="function:app.graph.neo4j_retriever.Neo4jGraphRetriever.__init__:L42",
                          name="__init__", qualified_name="app.graph.neo4j_retriever.Neo4jGraphRetriever.__init__",
                          signature="def __init__(self, driver)",
                          path="app/graph/neo4j_retriever.py", start_line=42, end_line=43)
    retriever = FakeRetriever(results={"get_methods_of_class": method})
    strategy = GraphStrategy(retriever=retriever)

    result = strategy.retrieve(_ctx("Find the __init__ method of Neo4jGraphRepository"))

    assert retriever.calls == [("get_methods_of_class", "__init__:Neo4jGraphRepository")]
    assert result.outcome == StrategyOutcome.SUCCESS
    assert result.documents[0]["type"] == "function"
    assert result.documents[0]["qualified_name"] == "app.graph.neo4j_retriever.Neo4jGraphRetriever.__init__"


def test_find_method_of_class_pattern_classname_dot_method():
    """
    Alternative syntax: ClassName.method_name should also resolve via get_methods_of_class.
    """
    method = FunctionNode(id="function:app.core.config.Settings.__init__:L10",
                          name="__init__", qualified_name="app.core.config.Settings.__init__",
                          signature="def __init__(self)",
                          path="app/core/config.py", start_line=10, end_line=11)
    retriever = FakeRetriever(results={"get_methods_of_class": method})
    strategy = GraphStrategy(retriever=retriever)

    result = strategy.retrieve(_ctx("Show me Settings.__init__"))

    assert retriever.calls == [("get_methods_of_class", "__init__:Settings")]
    assert result.outcome == StrategyOutcome.SUCCESS
    assert result.documents[0]["qualified_name"] == "app.core.config.Settings.__init__"