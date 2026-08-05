"""
Tests for PythonAstGraphBuilder. These run against REAL Python source
snippets through the REAL `ast` module -- ast_builder.py has zero
external dependencies, so unlike most of this test suite, nothing
here needs stubbing at all.
"""
from app.graph.ast_builder import PythonAstGraphBuilder, _module_qualified_name
from app.graph.models import ClassNode, FunctionNode, GraphEdgeType, ModuleNode, SourceFile

builder = PythonAstGraphBuilder()


def _build(files: list[SourceFile]):
    """Returns the ParsedGraph directly (unwrapped from GraphBuildResult) for tests that only care about nodes/edges."""
    return builder.build(files, repo_id="repo-1", repo_name="example", source_ref="owner/example").graph


def test_module_qualified_name_handles_plain_files_and_init_files():
    assert _module_qualified_name("app/main.py") == "app.main"
    assert _module_qualified_name("app/planner/__init__.py") == "app.planner"
    assert _module_qualified_name("top_level.py") == "top_level"


def test_top_level_function_is_extracted_with_correct_metadata():
    source = "def health():\n    return {\"status\": \"ok\"}\n"
    graph = _build([SourceFile(path="app/main.py", text=source)])

    functions = [n for n in graph.nodes if isinstance(n, FunctionNode)]
    assert len(functions) == 1
    fn = functions[0]
    assert fn.name == "health"
    assert fn.qualified_name == "app.main.health"
    assert fn.path == "app/main.py"
    assert fn.start_line == 1
    assert "def health(" in fn.signature

    modules = [n for n in graph.nodes if isinstance(n, ModuleNode)]
    assert modules[0].qualified_name == "app.main"

    defines_edges = [e for e in graph.edges if e.edge_type == GraphEdgeType.DEFINES]
    assert any(e.source_id == modules[0].id and e.target_id == fn.id for e in defines_edges)


def test_class_and_method_are_extracted_with_correct_qualified_names():
    source = (
        "class Settings:\n"
        "    def load(self):\n"
        "        pass\n"
    )
    graph = _build([SourceFile(path="app/core/config.py", text=source)])

    classes = [n for n in graph.nodes if isinstance(n, ClassNode)]
    assert len(classes) == 1
    assert classes[0].qualified_name == "app.core.config.Settings"

    functions = [n for n in graph.nodes if isinstance(n, FunctionNode)]
    assert len(functions) == 1
    assert functions[0].qualified_name == "app.core.config.Settings.load"

    defines_edges = [e for e in graph.edges if e.edge_type == GraphEdgeType.DEFINES]
    assert any(e.source_id == classes[0].id and e.target_id == functions[0].id for e in defines_edges)


def test_same_repo_import_creates_edge_external_import_does_not():
    files = [
        SourceFile(path="app/main.py", text="import os\nimport app.core.config\n"),
        SourceFile(path="app/core/config.py", text="x = 1\n"),
    ]
    graph = _build(files)

    imports_edges = [e for e in graph.edges if e.edge_type == GraphEdgeType.IMPORTS]
    main_module = next(n for n in graph.nodes if isinstance(n, ModuleNode) and n.qualified_name == "app.main")
    config_module = next(
        n for n in graph.nodes if isinstance(n, ModuleNode) and n.qualified_name == "app.core.config"
    )

    # Same-repo import -> exactly one IMPORTS edge, to the real config module.
    assert len(imports_edges) == 1
    assert imports_edges[0].source_id == main_module.id
    assert imports_edges[0].target_id == config_module.id
    # `import os` (external, stdlib) must NOT produce a phantom node or edge.
    assert not any(isinstance(n, ModuleNode) and n.qualified_name == "os" for n in graph.nodes)


def test_same_file_call_creates_edge():
    source = (
        "def helper():\n"
        "    return 1\n"
        "\n"
        "def main():\n"
        "    return helper()\n"
    )
    graph = _build([SourceFile(path="app/util.py", text=source)])

    calls_edges = [e for e in graph.edges if e.edge_type == GraphEdgeType.CALLS]
    main_fn = next(n for n in graph.nodes if isinstance(n, FunctionNode) and n.name == "main")
    helper_fn = next(n for n in graph.nodes if isinstance(n, FunctionNode) and n.name == "helper")

    assert len(calls_edges) == 1
    assert calls_edges[0].source_id == main_fn.id
    assert calls_edges[0].target_id == helper_fn.id


def test_cross_file_call_is_not_resolved_v1_limitation_is_real_not_just_documented():
    """
    Two files, each defining a function named `shared`. A call to
    `shared()` in file A must NOT link to file B's `shared` -- v1 only
    resolves same-file calls. This proves the documented limitation is
    actually enforced, not just written down.
    """
    files = [
        SourceFile(path="a.py", text="def caller():\n    return shared()\n"),
        SourceFile(path="b.py", text="def shared():\n    return 42\n"),
    ]
    graph = _build(files)

    calls_edges = [e for e in graph.edges if e.edge_type == GraphEdgeType.CALLS]
    # No CALLS edge at all -- `shared` isn't defined in a.py, and v1
    # doesn't attempt cross-file resolution.
    assert len(calls_edges) == 0


def test_attribute_calls_are_not_resolved_v1_limitation():
    """self.method() / obj.method() calls are explicitly out of scope for v1."""
    source = (
        "class Thing:\n"
        "    def helper(self):\n"
        "        return 1\n"
        "    def main(self):\n"
        "        return self.helper()\n"
    )
    graph = _build([SourceFile(path="thing.py", text=source)])

    calls_edges = [e for e in graph.edges if e.edge_type == GraphEdgeType.CALLS]
    assert len(calls_edges) == 0  # self.helper() is an Attribute call, not resolved in v1


def test_unparseable_file_is_skipped_not_fatal():
    files = [
        SourceFile(path="broken.py", text="def broken(:\n    this is not valid python\n"),
        SourceFile(path="fine.py", text="def works():\n    return True\n"),
    ]
    graph = _build(files)  # must not raise

    modules = [n for n in graph.nodes if isinstance(n, ModuleNode)]
    assert len(modules) == 1
    assert modules[0].qualified_name == "fine"


def test_non_python_files_are_ignored_entirely():
    files = [
        SourceFile(path="README.md", text="# Hello"),
        SourceFile(path="main.py", text="def f():\n    pass\n"),
    ]
    graph = _build(files)

    modules = [n for n in graph.nodes if isinstance(n, ModuleNode)]
    assert len(modules) == 1
    assert modules[0].path == "main.py"


def test_directory_hierarchy_is_built_correctly_for_nested_paths():
    files = [SourceFile(path="app/planner/planner.py", text="x = 1\n")]
    graph = _build(files)

    from app.graph.models import DirectoryNode

    dirs = {n.path: n for n in graph.nodes if isinstance(n, DirectoryNode)}
    assert "app" in dirs
    assert "app/planner" in dirs

    contains_edges = [e for e in graph.edges if e.edge_type == GraphEdgeType.CONTAINS]
    repo_node = graph.nodes[0]
    module_node = next(n for n in graph.nodes if isinstance(n, ModuleNode))

    # Repository -> app -> app/planner -> module, all as CONTAINS edges.
    assert any(e.source_id == repo_node.id and e.target_id == dirs["app"].id for e in contains_edges)
    assert any(e.source_id == dirs["app"].id and e.target_id == dirs["app/planner"].id for e in contains_edges)
    assert any(e.source_id == dirs["app/planner"].id and e.target_id == module_node.id for e in contains_edges)


def test_module_at_repo_root_links_directly_to_repository():
    files = [SourceFile(path="main.py", text="x = 1\n")]
    graph = _build(files)

    repo_node = graph.nodes[0]
    module_node = next(n for n in graph.nodes if isinstance(n, ModuleNode))
    contains_edges = [e for e in graph.edges if e.edge_type == GraphEdgeType.CONTAINS]

    assert any(e.source_id == repo_node.id and e.target_id == module_node.id for e in contains_edges)


def test_multiple_names_imported_from_same_module_produces_one_edge_not_several():
    """
    Regression test: 'from x import a, b, c' should produce ONE IMPORTS
    edge to module x, not one per imported name. Found via dogfooding
    against this repo's own planner.py, which does exactly this.
    """
    files = [
        SourceFile(path="app/main.py", text="from app.core.config import Settings, DEBUG, VERSION\n"),
        SourceFile(path="app/core/config.py", text="Settings = None\nDEBUG = True\nVERSION = 1\n"),
    ]
    graph = _build(files)

    imports_edges = [e for e in graph.edges if e.edge_type == GraphEdgeType.IMPORTS]
    assert len(imports_edges) == 1


def test_skipped_files_are_reported_not_silently_dropped():
    files = [
        SourceFile(path="README.md", text="# Hello"),
        SourceFile(path="package.json", text="{}"),
        SourceFile(path="main.py", text="x = 1\n"),
    ]
    result = builder.build(files, repo_id="repo-1", repo_name="example", source_ref="owner/example")

    assert set(result.skipped_files) == {"README.md", "package.json"}
    assert result.parse_errors == []


def test_parse_errors_are_reported_with_the_failing_path_and_message():
    files = [
        SourceFile(path="broken.py", text="def broken(:\n    invalid\n"),
        SourceFile(path="fine.py", text="x = 1\n"),
    ]
    result = builder.build(files, repo_id="repo-1", repo_name="example", source_ref="owner/example")

    assert len(result.parse_errors) == 1
    assert result.parse_errors[0].startswith("broken.py:")
    assert result.skipped_files == []  # broken.py IS a .py file -- it's a parse error, not a skip


def test_property_getter_setter_pair_does_not_produce_duplicate_node_ids():
    """
    Regression test for the exact bug found dogfooding against psf/requests:
    @property + @x.setter (or @typing.overload stacks) are two real
    ast.FunctionDef siblings sharing the same name -- id must disambiguate
    via line number, or they collide.
    """
    source = (
        "class Thing:\n"
        "    @property\n"
        "    def value(self):\n"
        "        return self._value\n"
        "\n"
        "    @value.setter\n"
        "    def value(self, v):\n"
        "        self._value = v\n"
    )
    graph = _build([SourceFile(path="thing.py", text=source)])

    functions = [n for n in graph.nodes if isinstance(n, FunctionNode)]
    ids = [f.id for f in functions]

    assert len(functions) == 2                    # both getter and setter represented
    assert len(ids) == len(set(ids))               # and their ids are genuinely unique
    assert all(f.qualified_name == "thing.Thing.value" for f in functions)  # same human-readable name, as expected
    assert {f.start_line for f in functions} == {3, 7}  # disambiguated by line number


def test_relative_import_from_dot_resolves_to_containing_package():
    """'from . import x' inside a non-__init__ module resolves to that module's own package."""
    files = [
        SourceFile(path="pkg/mod.py", text="from . import sibling\n"),
        SourceFile(path="pkg/sibling.py", text="y = 1\n"),
        SourceFile(path="pkg/__init__.py", text=""),
    ]
    graph = _build(files)

    imports_edges = [e for e in graph.edges if e.edge_type == GraphEdgeType.IMPORTS]
    mod = next(n for n in graph.nodes if isinstance(n, ModuleNode) and n.qualified_name == "pkg.mod")
    sibling = next(n for n in graph.nodes if isinstance(n, ModuleNode) and n.qualified_name == "pkg.sibling")

    assert any(e.source_id == mod.id and e.target_id == sibling.id for e in imports_edges)


def test_relative_import_from_dot_submodule_resolves_correctly():
    """'from .foo import bar' resolves to the current package's foo submodule."""
    files = [
        SourceFile(path="pkg/mod.py", text="from .auth import HTTPBasicAuth\n"),
        SourceFile(path="pkg/auth.py", text="class HTTPBasicAuth: pass\n"),
    ]
    graph = _build(files)

    imports_edges = [e for e in graph.edges if e.edge_type == GraphEdgeType.IMPORTS]
    mod = next(n for n in graph.nodes if isinstance(n, ModuleNode) and n.qualified_name == "pkg.mod")
    auth = next(n for n in graph.nodes if isinstance(n, ModuleNode) and n.qualified_name == "pkg.auth")

    assert any(e.source_id == mod.id and e.target_id == auth.id for e in imports_edges)


def test_relative_import_inside_init_py_uses_its_own_package_not_parent():
    """
    The __init__.py special case: inside pkg/__init__.py (qualified_name
    == 'pkg'), 'from . import x' means 'import pkg.x', NOT 'import
    <parent of pkg>.x'. Get this wrong and every relative import inside
    every __init__.py in a repo resolves one level too high.
    """
    files = [
        SourceFile(path="pkg/__init__.py", text="from . import sibling\n"),
        SourceFile(path="pkg/sibling.py", text="y = 1\n"),
    ]
    graph = _build(files)

    imports_edges = [e for e in graph.edges if e.edge_type == GraphEdgeType.IMPORTS]
    pkg_init = next(n for n in graph.nodes if isinstance(n, ModuleNode) and n.qualified_name == "pkg")
    sibling = next(n for n in graph.nodes if isinstance(n, ModuleNode) and n.qualified_name == "pkg.sibling")

    assert any(e.source_id == pkg_init.id and e.target_id == sibling.id for e in imports_edges)


def test_relative_import_two_levels_up():
    """'from .. import x' from pkg/sub/mod.py resolves relative to pkg (sub's parent)."""
    files = [
        SourceFile(path="pkg/sub/mod.py", text="from .. import top\n"),
        SourceFile(path="pkg/top.py", text="z = 1\n"),
    ]
    graph = _build(files)

    imports_edges = [e for e in graph.edges if e.edge_type == GraphEdgeType.IMPORTS]
    mod = next(n for n in graph.nodes if isinstance(n, ModuleNode) and n.qualified_name == "pkg.sub.mod")
    top = next(n for n in graph.nodes if isinstance(n, ModuleNode) and n.qualified_name == "pkg.top")

    assert any(e.source_id == mod.id and e.target_id == top.id for e in imports_edges)


def test_calling_the_same_helper_twice_produces_one_calls_edge_not_two():
    """
    Regression test for the exact discrepancy found via the Neo4j
    idempotency validation (builder emitted 176 edges, Neo4j persisted
    171 after MERGE collapsed duplicates): a function calling the same
    helper twice in its body should produce ONE CALLS edge, not two --
    matching how IMPORTS already dedupes multiple names from the same
    module. Without this, the builder's own edge count doesn't match
    the graph's actual logical relationship count, relying on Neo4j's
    MERGE to silently paper over the difference instead.
    """
    source = (
        "def helper():\n"
        "    return 1\n"
        "\n"
        "def main():\n"
        "    return helper() + helper() + helper()\n"
    )
    graph = _build([SourceFile(path="app/util.py", text=source)])

    calls_edges = [e for e in graph.edges if e.edge_type == GraphEdgeType.CALLS]
    assert len(calls_edges) == 1