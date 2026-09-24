# P1 Lessons Learned & Architectural Insights

**Date:** 2026-09-01  
**Context:** Reflection on P1 journey from ingestion bugs through validation  
**Audience:** Future development, project retrospective

---

## The Core Insight: Confidence Without Evidence

### The Bug That Opened Everything

Your original evaluator returned:
```json
{
  "confidence": 0.7,
  "documents": 0,
  "planner_outcome": "success"
}
```

This is a **category error**. You can't have confidence without evidence. This bug hid the real problem: **the retrieval system wasn't actually working**, but the metrics looked good.

### Why This Matters

It's the difference between:
- **Truthful confidence:** "We found 5 documents with 68% confidence they answer your question"
- **Deceiving confidence:** "We're 70% confident... by the way, we found nothing"

### The Fix

Add `final_documents_count` to every response. Make it impossible to hide zero results behind positive confidence.

**Implication:** Observability > Polished Metrics. Always.

---

## The Retrieval Stack: Where Real Work Happens

### P1 Journey

```
1. Document ingestion
   ↓ Bug: Rate limiting, missing Git binary, bad auth
   ↓ Fix: Add GitHub PAT support, install git in Docker
   
2. Vector storage
   ↓ Bug: Payload field names don't match schema
   ↓ Fix: Align VectorStrategy to actual Qdrant payload
   
3. Planner orchestration
   ↓ Bug: Metrics fabricated, outcome logic wrong
   ↓ Fix: Compute outcomes from real strategy results
   
4. Error handling
   ↓ Bug: Infrastructure failures crash requests
   ↓ Fix: Degrade to LOW_CONFIDENCE, log exception
   
5. Response contract
   ↓ Bug: numpy.bool_ breaks JSON serialization
   ↓ Fix: Cast to native float/bool at source
```

### Architecture Validation

**What works:**
- ✅ Modular strategies (Vector, Hybrid, Graph stubs)
- ✅ Escalation logic (try strategies in order)
- ✅ Policy enforcement (block unauthorized access)
- ✅ Threshold filtering (don't return low-confidence results)
- ✅ Audit trail (every attempt recorded)

**What needs work:**
- ⚠️ Graph integration (currently denied, needs query refinement)
- ⚠️ Pattern extraction (regex is fragile, needs redesign)
- ⚠️ Entity understanding (can't extract "class.method" from natural language)

---

## The Vector Payload Schema Bug: Root Cause Analysis

### What Happened

Ingestion pipeline stores:
```python
payload = {
    "document_id": uuid,
    "document_title": "app/graph/ast_builder.py",
    "text": "class PythonAstGraphBuilder...",
    "source_system": "github",
    "sensitivity": "internal",
}
```

Retrieval strategy expected:
```python
{
    "document_id": uuid,
    "title": "app/graph/ast_builder.py",      # ← Wrong field name
    "content": "class PythonAstGraphBuilder...",  # ← Wrong field name
}
```

**KeyError: 'title'**

### Why It Was Missed

1. **Hybrid strategy had it right** — no one checked if Vector matched
2. **No contract validation** — ingestion and retrieval didn't share schemas
3. **No schema versioning** — payload format evolved without tests
4. **Manual field mapping** — prone to typos and drift

### Lesson Learned

**Explicit contracts prevent data model drift.** The ingestion pipeline should export a schema; the retrieval layer should validate against it.

```python
# What should exist
class QdrantPayloadSchema(BaseModel):
    document_id: str
    document_title: str
    text: str
    source_system: str
    sensitivity: str

# Every upsert validates
def upsert_chunks(points: list[PointStruct]):
    for point in points:
        QdrantPayloadSchema(**point.payload)  # Validates
    client.upsert(...)
```

---

## The Classification Limitation: Regex Fragility

### Current State

**Working patterns:**
```python
GRAPH_PATTERNS = {
    "imports": r"(?:import|import.*from|what.*import)",
    "location": r"(?:find|where|locate|show).*defined",
    "callers": r"(?:calls|who.*calls|what.*calls)",
}
```

**Problem:** Each new question type needs new regex. Coverage grows linearly. Maintenance is quadratic.

### Why Regex Plateaus

```
Queries  | Success Rate
1-10     | 95% (patterns match common cases)
10-30    | 85% (edge cases, ambiguity)
30-100   | 60% (patterns overlap, conflicts)
100+     | Unmaintainable
```

Each new pattern risks **breaking existing patterns** (overlaps, ambiguity).

### The Fix (P2.2)

Move from:
```
Question → Regex match → Graph operation
```

To:
```
Question → Learned intent + Extracted entities → Graph operation
```

This scales because:
- Intent learning is automatic (no new regex per query type)
- Entity extraction is reusable (same extractor for all graph queries)
- Graph operations are composable (combine simple operations)

### Why It Matters

It's the difference between:
- **Brittle system:** Adding 10 queries requires 10 regex reviews
- **Robust system:** Adding 10 queries requires no code changes (just training data)

---

## Policy Enforcement: Working As Designed

### Current Behavior

Graph queries are denied by policy:
```python
if not self.policy.is_authorized("graph", context):
    # Record attempt as DENIED_BY_POLICY
    # Escalate to next strategy (vector)
    continue
```

Results: Graceful fallback, no errors, attempt recorded.

### Why This Is Right

**Security principle:** Deny by default, then enable. Graph access was denied in v1 by design. When Neo4j integration is ready, unlock it via policy update. No code changes needed.

### Future State (P2+)

```python
# In config or policy file
GRAPH_ACCESS_ALLOWED = {
    "import_analysis": True,     # "what does X import"
    "method_lookup": True,       # "find __init__ of Class"
    "file_contents": False,      # Save for v2 (needs caching)
}

# Policy evaluator checks
if not policy.is_authorized(strategy, context):
    # Still graceful fallback
```

**Lesson:** Separate authorization from capability. The graph strategy can fail gracefully whether policy denies it or the feature isn't ready.

---

## Error Handling: Graceful Degradation Works

### The Journey

**Before:** Infrastructure failures crashed requests
```python
try:
    result = strategy.retrieve(context)
except Exception:
    raise  # ← Crashes user's request
```

**After:** Log exception, degrade to LOW_CONFIDENCE
```python
try:
    result = strategy.retrieve(context)
except Exception:
    logger.exception("Strategy %s failed...", strategy_name)
    return RetrievalResult(
        documents=[],
        confidence=0.0,
        outcome=StrategyOutcome.LOW_CONFIDENCE,
        reasoning="Strategy failed; vector infrastructure down",
    )
    # ← Request still succeeds with honest response
```

### Why This Works

1. **User gets a response:** Doesn't hang or see 500
2. **System is honest:** Says "no evidence" not "success"
3. **Debugging is possible:** Exception logged in trace endpoint
4. **Escalation works:** Falls through to next strategy

### The Principle

**Never let a retrieval strategy crash the user's request.** Degrade gracefully and log what happened.

---

## Type Safety: Pylance Caught Real Bugs

### The Issue

numpy.bool_ broke JSON serialization:
```python
confidence = bm25_scores[0]  # numpy.float64 or numpy.bool_
# Later...
json.dumps({"confidence": confidence})  # ← Crashes if numpy.bool_
```

### The Fix

```python
# Cast at the source (where numpy enters the pipeline)
confidence = float(hit.score)  # Native float, not numpy.float64
```

### Lesson

Pylance type hints caught this before it happened in production. The hint was:
```python
def retrieve(...) -> RetrievalResult:
    # RetrievalResult.confidence: float
    # But we're passing numpy.float64
```

**Type safety isn't pedantic.** It's a cheap (free) way to catch real bugs.

---

## What Worked: Modular Strategy Architecture

### Why Strategies Are Good

```python
class RetrievalStrategy(ABC):
    @abstractmethod
    def retrieve(self, context: PlannerContext) -> RetrievalResult:
        pass
```

Each strategy is:
- ✅ **Independent:** Doesn't depend on other strategies
- ✅ **Testable:** Can mock/stub in unit tests
- ✅ **Replaceable:** Can swap implementations
- ✅ **Observable:** Each has its own latency, confidence, outcome

### Why This Enabled P1 Success

We could:
1. Test Vector in isolation (found payload bug)
2. Verify Hybrid worked independently (it did)
3. Stub Graph (policy-denied it, no panic)
4. Run regression tests without full stack

**Modularity enabled surgical debugging.**

### Future Strategies

The same pattern scales for:
- LLM-powered strategies (ask Copilot for complex analysis)
- Semantic similarity over documentation
- Cross-repo dependency analysis
- Code ownership/RBAC lookups

---

## Audit Trail: The Unsung Hero

### Every Query Recorded

```python
# In audit_log table
{
    "query": "Where is PythonAstGraphBuilder?",
    "strategy_attempts": [
        {"strategy": "graph", "outcome": "denied_by_policy"},
        {"strategy": "vector", "outcome": "success", "confidence": 0.68},
    ],
    "planner_outcome": "success",
    "confidence": 0.68,
    "timestamp": "2026-09-01T18:28:24",
    "user": "...",
    "department": "...",
}
```

### Why This Matters

1. **Debugging:** What went wrong? Check attempts array.
2. **Quality:** Which questions succeed? Which fail consistently?
3. **Compliance:** Who asked what, when?
4. **Tuning:** Which confidence thresholds work best?

### The Principle

**Measure everything that matters.** The audit log is the system's memory. Without it, every outage is a mystery.

---

## What Didn't Work (and Why)

### Docker Build Timeouts

**Problem:** PyPI downloads timed out during image build  
**Root cause:** Network latency, not app bug  
**Resolution:** Used local venv for validation  
**Lesson:** Separate app bugs from infrastructure issues. Local validation is fast feedback.

### Graph Classifier Patterns

**Problem:** "Classes in planner.py" didn't classify to graph  
**Root cause:** Patterns were too specific ("find classes of file" → no regex match)  
**Resolution:** Falls back to vector (sub-threshold)  
**Lesson:** Graph patterns need redesign (P2.2). Regex is a dead end.

### Symbol Navigation

**Problem:** `__init__` queries treat it as global symbol  
**Root cause:** No context about class/method relationships  
**Resolution:** Falls back to vector (noisy results)  
**Lesson:** Need entity extraction, not just regex patterns (P2.1).

---

## If You Were to Redo P1

1. **Start with schema validation** (prevent payload mismatches early)
2. **Add `final_documents_count` from day one** (never hide zero results)
3. **Test strategies in isolation** (catch Vector bug immediately)
4. **Type hints from the start** (Pylance catches numpy issues)
5. **Audit trail as first-class** (not an afterthought)

---

## The Bigger Picture

### Month 1 (P1): Foundation
- ✅ Core retrieval working (Vector + Hybrid)
- ✅ Planner orchestration correct
- ✅ Error handling graceful
- ✅ Audit trail complete

### Month 2 (P2): Quality
- 🔄 Graph query refinement
- 🔄 Pattern extraction redesign
- 🔄 Entity understanding
- 🔄 Observability improvements

### Month 3 (P3): Scale
- ❌ Fine-tuning embeddings
- ❌ RBAC integration
- ❌ Caching and optimization
- ❌ Production monitoring

---

## Conclusion

**P1 wasn't about feature completeness. It was about getting the foundation right:**
- Data contract between ingestion and retrieval
- Honest metrics (no confidence without evidence)
- Graceful error handling (infrastructure failures don't break UX)
- Modular architecture (strategies can evolve independently)
- Complete audit trail (debugging and compliance)

P2 builds on this foundation. P3 builds on P2.

The system works because we prioritized **correctness** over **coverage**. The 83.3% benchmark isn't the goal; **trustworthy metrics** are.

---

## Decision for P2

**Recommended approach:**
1. Keep P1 as-is (don't touch working code)
2. Implement P2.1 (symbol navigation, low risk)
3. Implement P2.2 (architecture redesign, high value)
4. Document P2.3 (evaluator transparency)

This positions Month 2 for graph quality without destabilizing Month 1's foundation.
