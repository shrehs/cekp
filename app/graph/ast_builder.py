"""
PythonAstGraphBuilder: the first real GraphBuilder implementation.
Parses Python source (via the stdlib `ast` module) into a ParsedGraph
matching docs/graph-schema.md.

Scope, matching the documented v1 limitations exactly (not more, not
less):
- Python files only (`.py`). Non-Python files are ignored entirely --
  they're already covered by vector/hybrid retrieval; this graph is a
  Python-specific view, not a replacement.
- Top-level classes, top-level functions, and methods on top-level
  classes only. Nested functions/closures are not represented as
  separate nodes in v1 -- deliberately, to avoid a much larger surface
  before the simple case is proven out.
- IMPORTS edges only for imports that resolve to another module in the
  SAME build() call (i.e. same repo). External package imports
  (`import requests`) are simply not linked to a Module node -- no
  attempt to fabricate a node for something outside the repo.
- CALLS edges only for simple same-file `name()` calls where `name`
  matches a function defined in the same file. Attribute calls
  (`self.foo()`, `obj.method()`, `module.func()`) are NOT resolved in
  v1 -- this is the "don't over-engineer call resolution" boundary
  from docs/graph-schema.md, taken literally.
"""
import ast
import posixpath

from app.graph.builder_base import GraphBuilder
from app.graph.models import (
    ClassNode,
    DirectoryNode,
    FunctionNode,
    GraphBuildResult,
    GraphEdge,
    GraphEdgeType,
    ModuleNode,
    ParsedGraph,
    RepositoryNode,
    SourceFile,
)


def _module_qualified_name(path: str) -> str:
    """'app/planner/__init__.py' -> 'app.planner'; 'app/main.py' -> 'app.main'"""
    without_ext = path[:-3] if path.endswith(".py") else path
    parts = without_ext.split("/")
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    try:
        args_str = ast.unparse(node.args)
    except Exception:
        args_str = "..."  # malformed args shouldn't fail the whole file
    return f"{prefix} {node.name}({args_str})"


def _end_line(node: ast.AST, fallback: int) -> int:
    return getattr(node, "end_lineno", None) or fallback


def _relative_import_base(module_qn: str, is_package_init: bool, level: int) -> str:
    """
    Python's relative-import semantics: level=1 ('from . import x') means
    'the current package'. For a regular module pkg.sub.mod, that's
    pkg.sub -- drop the module's own name. For pkg/sub/__init__.py
    itself (module_qn == 'pkg.sub', since _module_qualified_name already
    strips '__init__'), the module's own qualified_name IS the package,
    so level=1 resolves to itself, not its parent -- get this wrong and
    every relative import inside every __init__.py in a repo resolves
    one level too high.
    """
    parts = module_qn.split(".")
    if not is_package_init:
        parts = parts[:-1]  # drop the module's own name to get its containing package
    extra_up = level - 1
    if extra_up > 0:
        parts = parts[:-extra_up] if len(parts) >= extra_up else []
    return ".".join(parts)


class PythonAstGraphBuilder(GraphBuilder):
    def build(self, files: list[SourceFile], repo_id: str, repo_name: str, source_ref: str) -> GraphBuildResult:
        nodes: list = [RepositoryNode(id=f"repo:{repo_id}", name=repo_name, source_ref=source_ref)]
        edges: list[GraphEdge] = []

        python_files = [f for f in files if f.path.endswith(".py")]
        skipped_files = [f.path for f in files if not f.path.endswith(".py")]
        parse_errors: list[str] = []

        # Pass 1: parse every file, build Module/Class/Function nodes.
        # Keep the parsed AST + qualified names around for pass 2 (imports/calls),
        # which needs the full registry of what's in this repo before it can
        # decide what resolves and what doesn't.
        parsed_modules = {}  # qualified_name -> (SourceFile, ast.Module, ModuleNode)
        module_functions_by_file = {}  # module qualified_name -> {func_name: FunctionNode}

        for source_file in python_files:
            try:
                tree = ast.parse(source_file.text)
            except SyntaxError as e:
                parse_errors.append(f"{source_file.path}: {e}")
                continue  # unparseable file -- skip it, don't fail the whole build

            module_qn = _module_qualified_name(source_file.path)
            line_count = len(source_file.text.splitlines()) or 1
            module_node = ModuleNode(
                id=f"module:{module_qn}",
                name=module_qn.split(".")[-1],
                qualified_name=module_qn,
                path=source_file.path,
                language="python",
                start_line=1,
                end_line=line_count,
            )
            nodes.append(module_node)
            parsed_modules[module_qn] = (source_file, tree, module_node)
            module_functions_by_file[module_qn] = {}

            for stmt in tree.body:
                if isinstance(stmt, ast.ClassDef):
                    class_qn = f"{module_qn}.{stmt.name}"
                    class_node = ClassNode(
                        id=f"class:{class_qn}",
                        name=stmt.name,
                        qualified_name=class_qn,
                        path=source_file.path,
                        start_line=stmt.lineno,
                        end_line=_end_line(stmt, stmt.lineno),
                    )
                    nodes.append(class_node)
                    edges.append(GraphEdge(GraphEdgeType.DEFINES, module_node.id, class_node.id))

                    for member in stmt.body:
                        if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            method_qn = f"{class_qn}.{member.name}"
                            method_node = FunctionNode(
                                # Line-number suffix, not just method_qn: a class
                                # can legitimately have two sibling FunctionDefs
                                # sharing a name (@property + @x.setter pairs,
                                # @typing.overload stacks) -- found via dogfooding
                                # against psf/requests, where this produced
                                # genuine duplicate node IDs. qualified_name stays
                                # clean/human-readable and CAN still collide in
                                # that case -- resolving "which one" is a
                                # GraphRetriever concern later, not an AST bug now.
                                id=f"function:{method_qn}:L{member.lineno}",
                                name=member.name,
                                qualified_name=method_qn,
                                signature=_function_signature(member),
                                path=source_file.path,
                                start_line=member.lineno,
                                end_line=_end_line(member, member.lineno),
                            )
                            nodes.append(method_node)
                            edges.append(GraphEdge(GraphEdgeType.DEFINES, class_node.id, method_node.id))
                            # Methods are keyed by simple name for same-file call
                            # resolution, same as top-level functions -- v1 does
                            # not distinguish "a call to this method" from "a call
                            # to a same-named top-level function" beyond that. If
                            # a name collides (e.g. property getter/setter), the
                            # later definition wins here -- same-file CALLS
                            # resolution for that name will point at whichever
                            # sibling was parsed last, a known v1 imprecision.
                            module_functions_by_file[module_qn][member.name] = method_node

                elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    func_qn = f"{module_qn}.{stmt.name}"
                    func_node = FunctionNode(
                        id=f"function:{func_qn}:L{stmt.lineno}",  # see comment above on method ids
                        name=stmt.name,
                        qualified_name=func_qn,
                        signature=_function_signature(stmt),
                        path=source_file.path,
                        start_line=stmt.lineno,
                        end_line=_end_line(stmt, stmt.lineno),
                    )
                    nodes.append(func_node)
                    edges.append(GraphEdge(GraphEdgeType.DEFINES, module_node.id, func_node.id))
                    module_functions_by_file[module_qn][stmt.name] = func_node

        # Pass 2: IMPORTS edges (same-repo modules only) and CALLS edges
        # (same-file, simple Name() calls only).
        for module_qn, (source_file, tree, module_node) in parsed_modules.items():
            # Dedup within this module: `from x import a, b, c` should
            # produce ONE edge to x, not one per imported name.
            seen_import_targets: set[str] = set()
            is_package_init = source_file.path.endswith("__init__.py")

            def _link_if_resolved(candidates: list[str]) -> None:
                """Try each candidate in order; the first that resolves to a real module wins, regardless of whether it's already linked (matches the original single-target-per-statement semantics)."""
                target = None
                for candidate in candidates:
                    target = parsed_modules.get(candidate)
                    if target is not None:
                        break
                if target is not None and target[2].id not in seen_import_targets:
                    edges.append(GraphEdge(GraphEdgeType.IMPORTS, module_node.id, target[2].id))
                    seen_import_targets.add(target[2].id)

            for stmt in ast.walk(tree):
                if isinstance(stmt, ast.Import):
                    for alias in stmt.names:
                        _link_if_resolved([alias.name])
                        # else: external package (e.g. `import requests`) --
                        # not in this repo, not linked. Not an error.

                elif isinstance(stmt, ast.ImportFrom):
                    if stmt.level == 0:
                        if not stmt.module:
                            continue  # defensive; level 0 always has a module in practice
                        for alias in stmt.names:
                            # Try "from foo.bar import baz" as importing module
                            # foo.bar.baz first (submodule import); fall back to
                            # foo.bar (importing a name from that module).
                            _link_if_resolved([f"{stmt.module}.{alias.name}", stmt.module])
                    else:
                        # Relative import -- resolved now (was previously
                        # skipped entirely in v1, which turned out to miss
                        # most of a typical package's real internal import
                        # graph: intra-package imports are conventionally
                        # relative, not absolute).
                        base = _relative_import_base(module_qn, is_package_init, stmt.level)
                        if stmt.module:
                            # from .foo import bar  /  from ..foo.bar import baz
                            full_module = f"{base}.{stmt.module}" if base else stmt.module
                            for alias in stmt.names:
                                _link_if_resolved([f"{full_module}.{alias.name}", full_module])
                        else:
                            # from . import x  /  from .. import x
                            for alias in stmt.names:
                                candidate = f"{base}.{alias.name}" if base else alias.name
                                _link_if_resolved([candidate])

            # CALLS: walk every function/method body in this file, look for
            # simple Name() calls matching another function in the SAME file.
            same_file_functions = module_functions_by_file[module_qn]
            for func_name, func_node in same_file_functions.items():
                func_ast = _find_function_ast(tree, func_name)
                if func_ast is None:
                    continue
                seen_call_targets: set[str] = set()  # dedup: calling the same helper twice in one function body shouldn't produce two edges
                for call_node in ast.walk(func_ast):
                    if isinstance(call_node, ast.Call) and isinstance(call_node.func, ast.Name):
                        called_name = call_node.func.id
                        if called_name in same_file_functions and called_name != func_name:
                            target_node = same_file_functions[called_name]
                            if target_node.id not in seen_call_targets:
                                edges.append(GraphEdge(GraphEdgeType.CALLS, func_node.id, target_node.id))
                                seen_call_targets.add(target_node.id)
                        # else: not resolvable in v1 (external, attribute call,
                        # or genuinely undefined) -- not linked, not an error.

        # Directory + Repository CONTAINS structure, built only from directories
        # that lead to at least one included (Python) module.
        directory_nodes: dict[str, DirectoryNode] = {}
        repo_node_id = nodes[0].id
        for module_qn, (source_file, _, module_node) in parsed_modules.items():
            dir_path = posixpath.dirname(source_file.path)
            if not dir_path:
                edges.append(GraphEdge(GraphEdgeType.CONTAINS, repo_node_id, module_node.id))
                continue

            parts = dir_path.split("/")
            parent_id = repo_node_id
            built_path = ""
            for part in parts:
                built_path = f"{built_path}/{part}" if built_path else part
                if built_path not in directory_nodes:
                    dir_node = DirectoryNode(id=f"dir:{built_path}", path=built_path)
                    directory_nodes[built_path] = dir_node
                    nodes.append(dir_node)
                    edges.append(GraphEdge(GraphEdgeType.CONTAINS, parent_id, dir_node.id))
                parent_id = directory_nodes[built_path].id
            edges.append(GraphEdge(GraphEdgeType.CONTAINS, parent_id, module_node.id))

        return GraphBuildResult(
            graph=ParsedGraph(nodes=nodes, edges=edges),
            skipped_files=skipped_files,
            parse_errors=parse_errors,
        )


def _find_function_ast(tree: ast.Module, name: str):
    """
    Locate a top-level function OR a method (one level of class nesting)
    by simple name. v1 scope matches module_functions_by_file's own
    scope: top-level functions and methods on top-level classes, no
    deeper nesting.
    """
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name == name:
            return stmt
        if isinstance(stmt, ast.ClassDef):
            for member in stmt.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and member.name == name:
                    return member
    return None