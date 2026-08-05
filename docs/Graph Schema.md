# Graph Schema — Decision and v1 Scope

## The decision

Neo4j will build a **code-structure graph** first — `Repository → Directory → File → Class/Function`, with `IMPORTS`/`CALLS`/`DEFINES` edges. The **org-dependency graph** originally sketched in `architecture.md` (`Document`/`Person`/`Policy`/`System`, with `OWNED_BY`/`SUPERSEDES`/`DEPENDS_ON`) is explicitly deferred, not abandoned.

## Why this isn't the schema `architecture.md` originally described

That schema assumed an entity-extraction step ("this document is owned by this person," "this system depends on that system," pulled out of ingested text). That step was never built — `app/ingestion/pipeline.py` only chunks and embeds; there's no NLP/entity layer. Building the org-dependency graph today would mean building that extraction pipeline first, which is a real ML problem, not a schema design problem.

The code-structure graph needs no new capability: it's directly derivable from files already ingested via GitHub (`.py`, `.js`, `.ts`) using static parsing (Python's `ast` module, or import-statement scanning for other languages) — no entity extraction, no NLP, no new ingestion source.

## Consequence: the existing demo query and classifier patterns don't apply here

Before this decision, the project's running demo query was *"which services depend on the auth service?"* — an org-dependency question with no answer in a code-structure graph (there's no `Service` node). The `IntentClassifier`'s `GRAPH_PATTERNS` (`"depends on"`, `"owner"`, `"who owns"`, `"connected to"`) were written for that same org-dependency framing.

Both are being updated (see `app/planner/intent_classifier.py` and `docs/integration-validation.md`) to also recognize code-structure questions: *"what does `app/main.py` import?"*, *"what calls `health()`?"*, *"what functions are defined in `planner.py`?"*

The org-dependency patterns are **not removed** — they stay in the classifier, they'll just keep returning `NOT_IMPLEMENTED`/`LOW_CONFIDENCE` until the org-dependency graph (and its entity-extraction prerequisite) gets built later, which is expected and fine, same as `GraphStrategy` today.

## v1 Code-Structure Schema

Nodes use `Module`, not `File` — Python's import system resolves at the module level, not the file level, so modeling it as `File` would be pretending files and modules are the same thing (they mostly are for single-file modules, but the concept that matters for `IMPORTS` edges is the module, not the file on disk).

Every node carries enough to jump straight to source, not just prove existence:

```
(:Repository {id, name, source_ref})
(:Directory {id, path})
(:Module {id, name, qualified_name, path, language, start_line, end_line})
(:Class {id, name, qualified_name, path, start_line, end_line})
(:Function {id, name, qualified_name, signature, path, start_line, end_line})

(:Repository)-[:CONTAINS]->(:Directory)
(:Directory)-[:CONTAINS]->(:Directory)      -- nested directories
(:Directory)-[:CONTAINS]->(:Module)
(:Module)-[:DEFINES]->(:Class)
(:Module)-[:DEFINES]->(:Function)
(:Module)-[:IMPORTS]->(:Module)              -- same-repo imports only in v1 (see limitations)
(:Function)-[:CALLS]->(:Function)            -- same-file calls only in v1 (see limitations)
```

**`qualified_name` everywhere, not just `name`.** `name: "authenticate"` collides the moment two files define a function with that name. `qualified_name: "auth.login.authenticate"` doesn't. Same for classes: `name: "Session"` collides constantly (it's a common name); `qualified_name: "requests.sessions.Session"` doesn't. `name` stays for display/search; `qualified_name` is the thing queries and disambiguation should actually key on.

**`start_line`/`end_line` on every node.** Without them, "show me `authenticate()`" can tell you *that* it exists and *which file* it's in, but not where to actually look. Cheap to capture during AST parsing, expensive to retrofit later.

## v1 limitations of the code-structure graph (stated up front, not discovered later)

- **Python only.** `ast` gives a real parse tree; other languages would need per-language parsers (or a shared one like `tree-sitter`) — not built in v1.
- **Same-repo imports only**, but **both absolute and relative are resolved.** `from .auth import HTTPBasicAuth`, `from . import sibling`, and `from .. import top` all resolve correctly, including the `__init__.py` special case (a package's own `__init__.py` is the level-1 base for itself, not its parent — get this wrong and every relative import inside every `__init__.py` in a repo resolves one level too high). External package imports (`import requests`) are recorded as unresolved and not linked to a `Module` node.
- **Same-file call resolution only**, and **only simple `name()` calls** — `self.method()`/`obj.method()`/`module.func()` (any `ast.Attribute` call target) are NOT resolved in v1. Cross-file call resolution requires real symbol resolution — deferred, and would misattribute calls to same-named functions in different files if attempted naively right now.
- **Node IDs disambiguate by line number, not just qualified name.** Two `ast.FunctionDef` siblings can legitimately share a name in real Python — `@property`/`@x.setter` pairs, `@typing.overload` stacks — found via dogfooding against `psf/requests` (property/overload-heavy, as most type-hinted libraries are), where the initial version used bare `qualified_name` as the ID and silently collided. `qualified_name` stays clean and human-readable and *can* still collide in that case (both really are "the same logical name"); resolving "which one" for a `find_function(qualified_name)` lookup is a `GraphRetriever` concern for later, not an AST-parsing bug to hide now. Same-file `CALLS` resolution for a colliding name currently points at whichever sibling was parsed last — a known, small v1 imprecision.
- **No inheritance/polymorphism awareness.** A `Class` node doesn't yet capture `extends`/`implements` relationships.

Both bugs above were found the same way: running the real builder against a real, sizable repository (`psf/requests`, 37 files) rather than trusting synthetic unit tests alone — the duplicate-ID bug in particular affected 9 of 635 functions, a pattern sparse enough that no reasonable synthetic test set would have stumbled onto it by chance.

**A third bug, found via the Neo4j idempotency check rather than the builder's own validation script:** persisting a graph produced fewer edges in Neo4j (171) than the builder emitted (176). Root cause: `IMPORTS` edges were explicitly deduped per module (`seen_import_targets`), but `CALLS` edges had no equivalent guard — a function calling the same helper twice in its body emitted two identical `(source, target, CALLS)` edges, which Neo4j's `MERGE` correctly (and silently) collapsed into one relationship. Fixed by adding the same per-caller dedup to `CALLS` that `IMPORTS` already had, proven via a synthetic regression test (a function calling the same helper three times → exactly one `CALLS` edge). The builder's own `integrity_check()` (in `scripts/validate_graph_builder.py`) was also generalized at the same time — it previously only checked for duplicate `IMPORTS` edges specifically, which is exactly why this `CALLS` duplication went undetected by the builder's own validation and only surfaced via the Neo4j idempotency count mismatch instead. It now checks duplicates across any `(source, target, edge_type)` triple.

## Example queries this graph can answer

- "What does `app/api/query.py` import?" → `MATCH (m:Module {path: 'app/api/query.py'})-[:IMPORTS]->(imported) RETURN imported`
- "What functions are defined in `planner.py`?" → `MATCH (m:Module {path: '...planner.py'})-[:DEFINES]->(fn:Function) RETURN fn`
- "What calls `build_user_response`?" → `MATCH (caller:Function)-[:CALLS]->(fn:Function {qualified_name: 'app.planner.planner.build_user_response'}) RETURN caller` (same-file only, per the limitation above)
- "Show me `authenticate()`" → `MATCH (fn:Function {qualified_name: 'auth.login.authenticate'}) RETURN fn.path, fn.start_line, fn.end_line` — jumps straight to source, not just "yes it exists somewhere."

## Interface separation — defined before any Neo4j code is written

Four responsibilities, four interfaces, so graph logic stays testable without a running Neo4j instance. Implemented as thin ABCs in `app/graph/` — no logic yet, just the contracts:

- **`GraphBuilder`** (`app/graph/builder_base.py`, real implementation in `app/graph/ast_builder.py`'s `PythonAstGraphBuilder`) — AST → graph objects (nodes/edges as plain Python data, no Neo4j awareness at all).

**Interface revised before implementation, for a real reason.** `build()` originally took a `repo_path` (disk path). GitHub ingestion (`app/ingestion/github_connector.py`) fetches file content directly into memory and never writes to disk — a `repo_path` would have forced an unnecessary temp-directory write just to satisfy the interface. Changed to `build(files: list[SourceFile], ...)` where `SourceFile` is just `{path, text}`, matching what ingestion already produces. Nothing real depended on the old signature yet, so this cost nothing — exactly the kind of implementation-driven correction the Architecture Freeze Policy allows.

**`PythonAstGraphBuilder` is real, not a stub** — parses actual Python source via the stdlib `ast` module. Verified two ways: 12 unit tests against synthetic source (covering the documented limitations explicitly — same-file-only calls, same-repo-only imports, attribute calls unresolved, unparseable files skipped, non-Python files ignored), and a direct dogfooding run against this repo's own `app/planner/` files. The dogfooding run caught a real bug — `from x import a, b, c` was producing one `IMPORTS` edge per imported name instead of one per module pair — fixed and covered by a regression test (`test_multiple_names_imported_from_same_module_produces_one_edge_not_several`).
- **`GraphRepository`** (`app/graph/repository_base.py`, real implementation in `app/graph/neo4j_repository.py`'s `Neo4jGraphRepository`) — persists `GraphBuilder`'s output to Neo4j. The only place Cypher `CREATE`/`MERGE` statements live. Three methods: `create_constraints()` (idempotent schema setup, called once, independent of any repo), `persist(graph)` (upserts nodes then edges, in that order, batched via `UNWIND` — one statement per node label and per edge type present, not a naive per-row loop), `clear_repository(repo_id)`. Deliberately has **no read method** — reads belong on `GraphRetriever`; adding one here would undo the write/read separation this split exists for.

**Design choices worth being explicit about:** no APOC (edge types are a small closed enum, so a literal relationship keyword per Cypher statement is simpler and safer than dynamic relationship types); `SET n += row` instead of per-label field lists (one Cypher pattern works for all five node types via `dataclasses.asdict()`); edge `MATCH` clauses are label-agnostic (`MATCH (a {id: ...})`, not `MATCH (a:Module {id: ...})`) — correct since ids are globally unique via their type-prefixed scheme, but not index-optimal without a label hint, a known v1 tradeoff.

**Verified two ways, at two different confidence levels.** `tests/test_neo4j_repository.py` uses a fake driver that records exactly what Cypher/params would be sent, without executing anything — this genuinely proves the Python-side grouping and query construction (7 tests, run for real, no stubbing needed). It does **not** prove the Cypher is semantically correct against a real database. `scripts/validate_neo4j_repository.py` is the real confirmation: persists the same graph twice against a live Neo4j and asserts node/edge counts are identical — the actual idempotency proof that `MERGE` + the uniqueness constraints + the line-number-disambiguated ids all work together, not just individually. That script has not been run — it needs your live Neo4j.
- **`GraphRetriever`** (`app/graph/retriever_base.py`) — runs read-only Cypher queries against what `GraphRepository` persisted. The only place Cypher `MATCH` statements live.
- **`GraphStrategy`** (`app/planner/strategies.py`) — **real, not a stub.** Sub-classifies which specific code-structure question this is (imports / importers-of / functions-in / classes-in / callers-of / where-is-X-defined) via a second, more specific regex pass on queries already routed to `GRAPH`, extracts a target reference token, and calls the matching `GraphRetriever` method. Org-dependency questions ("which services depend on X") are checked first and still return `NOT_IMPLEMENTED` — that's a distinct, real capability gap, not "couldn't parse this text," and conflating the two would erase a distinction this project has maintained throughout (see `docs/planner.md`). Confidence is a near-binary heuristic (`0.85` if the graph returned something, `0.0` if not), consistent with `docs/confidence.md`'s point that graph confidence isn't a similarity score like vector/hybrid's.

Data models (`app/graph/models.py`): typed dataclasses matching this schema exactly (`RepositoryNode`, `DirectoryNode`, `ModuleNode`, `ClassNode`, `FunctionNode`, `GraphEdge`, `ParsedGraph`) — verified via `tests/test_graph_interfaces.py` to import and run with zero infrastructure dependency (no qdrant/sentence_transformers/Neo4j needed even to stub).

`GraphBuilder` can be fully unit-tested against real Python source (via `ast`) with zero Docker/Neo4j dependency — same principle as everything else in this codebase (Month 1's validation checklist, the planner's fake-strategy tests). `GraphRepository`/`GraphRetriever` are the only two things that actually need a live Neo4j to test meaningfully.

## Canonical graph validation scenario

Now that `GraphStrategy` is real, this is the standard end-to-end check — the same role `/query/trace`'s org-dependency query played during planner validation, now applied to the capability that actually works:

```
Ingest a real repo
  → Query: "Which functions are defined in sessions.py?"
  → Planner classifies -> graph ranked first
  → GraphStrategy sub-classifies -> get_functions_defined_in, reference "sessions.py"
  → Neo4jGraphRetriever queries Neo4j
  → StrategyOutcome.SUCCESS, confidence clears threshold
  → PlannerOutcome.SUCCESS
```

This is reflected in `docs/integration-validation.md` and `scripts/validate.sh` — no longer informational-only, since the capability being checked is real, not pending.

## Deferred: org-dependency graph

When entity extraction exists (a real future milestone, not scheduled yet), the original schema in `architecture.md` becomes buildable as an *additional* graph alongside this one — not a replacement. `GraphStrategy` would then need to decide (or the classifier would need to route) between "this is a code-structure question" and "this is an org-dependency question," which is a real design question to solve later, not now.