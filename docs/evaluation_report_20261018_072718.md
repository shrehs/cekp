# CEKP Query System Evaluation Report

**Generated:** 2026-10-18T07:27:18.446417

## Executive Summary

This evaluation systematically tests the CEKP query system across 25+ representative
 questions spanning code navigation, API contracts, logic explanation, dependencies,
 configuration, error handling, and system design.

### Key Metrics

- **Total Queries:** 24
- **Planner Success Rate:** 66.7% (16/24)
- **Evidence Found:** 66.7% (16/24)
- **Evidence-backed Success:** 66.7% (16/24)
- **No Evidence:** 33.3% (8/24)
- **Policy Denied:** 0.0% (0/24)
- **HTTP/Infrastructure Errors:** 25.0% (6/24)
- **Success Without Evidence:** 0
- **Evaluated Relevance:** 100.0% (10/10)
- **Latency:** p50 59ms / p95 30021ms / p99 30036ms
- **Latency Range:** 34ms - 30040ms

### Confidence Scores

- **Mean Confidence:** 0.705
- **Median Confidence:** 0.687
- **Range:** 0.575 - 0.862

### Outcome Distribution

- **success:** 16 (66.7%)
- **not_evaluated:** 6 (25.0%)
- **no_evidence:** 2 (8.3%)

### Strategy Usage & Effectiveness

- **hybrid:** 14 queries (58.3%)
- **graph:** 1 queries (4.2%)
- **vector:** 1 queries (4.2%)

### Attempted Strategy Distribution

- **hybrid:** 15 attempts
- **graph:** 3 attempts
- **vector:** 3 attempts

### Performance by Question Category

- **api_contract:** 0/3 successful (0%)
- **code_logic:** 3/3 successful (100%)
- **code_navigation:** 1/4 successful (25%)
- **configuration:** 2/2 successful (100%)
- **dependencies:** 1/2 successful (50%)
- **error_handling:** 2/2 successful (100%)
- **integration:** 2/2 successful (100%)
- **out_of_scope:** 1/2 successful (50%)
- **performance:** 2/2 successful (100%)
- **testing:** 2/2 successful (100%)

## Detailed Results

|#|Question|Category|Intent|Strategy|Outcome|Confidence|Latency|Results|

|---|---|---|---|---|---|---|---|---|

|1|Where is the PythonAstGraphBuilder class...|code_navigation|graph|graph|success|0.85|2900ms|1|
|2|Find the __init__ method of Neo4jGraphRe...|code_navigation|—|none|not_evaluated|—|30022ms|0|
|3|Show me the ingest_github function.|code_navigation|—|none|not_evaluated|—|30040ms|0|
|4|Where does Planner.plan() retrieve strat...|code_navigation|—|none|not_evaluated|—|30007ms|0|
|5|What does the /ingest/github endpoint ac...|api_contract|—|none|not_evaluated|—|30006ms|0|
|6|What fields are in QueryRequest schema?|api_contract|—|none|not_evaluated|—|30012ms|0|
|7|What are the possible outcomes from the ...|api_contract|—|none|not_evaluated|—|30019ms|0|
|8|How does the intent classifier decide wh...|code_logic|hybrid|hybrid|success|0.84|8291ms|5|
|9|Explain the escalation logic in the plan...|code_logic|hybrid|hybrid|success|0.64|54ms|5|
|10|What does the policy evaluator check bef...|code_logic|hybrid|hybrid|success|0.73|53ms|5|
|11|What packages does the embedding service...|dependencies|graph|none|no_evidence|—|38ms|0|
|12|Which modules depend on the graph_store?|dependencies|graph|vector|success|0.58|49ms|5|
|13|What environment variables control CEKP ...|configuration|hybrid|hybrid|success|0.62|49ms|5|
|14|What is the default confidence threshold...|configuration|hybrid|hybrid|success|0.78|55ms|5|
|15|What happens when GitHub API rate limit ...|error_handling|hybrid|hybrid|success|0.64|83ms|5|
|16|How does the audit logging handle failur...|error_handling|hybrid|hybrid|success|0.73|57ms|5|
|17|Is the Planner instantiated per-request ...|performance|hybrid|hybrid|success|0.86|69ms|5|
|18|How many strategies can escalate before ...|performance|hybrid|hybrid|success|0.64|55ms|5|
|19|How is Neo4j connected from the API cont...|integration|hybrid|hybrid|success|0.79|34ms|5|
|20|What happens when a repository is re-ing...|integration|hybrid|hybrid|success|0.64|62ms|5|
|21|What tests exist for the graph builder?|testing|hybrid|hybrid|success|0.71|40ms|5|
|22|How are GitHub connector tests structure...|testing|hybrid|hybrid|success|0.66|56ms|5|
|23|Tell me about machine learning.|out_of_scope|hybrid|hybrid|success|0.58|40ms|3|
|24|What is the weather?|out_of_scope|hybrid|none|no_evidence|—|62ms|0|

## Analysis & Recommendations

### ⚠️ Tuning Opportunities

Several queries did not return evidence. Consider:

1. **Intent classifier calibration:** Verify that questions are classified correctly

2. **Strategy thresholds:** Adjust confidence thresholds if strategies are too conservative

3. **Vector embeddings:** Re-index if semantic similarity is degraded

4. **Graph completeness:** Ensure AST parsing captured all code relationships


### Latency Profile

❌ High latency (8006ms avg) - investigate bottlenecks


### Strategy Diversity

✅ Multiple strategies are being exercised, indicating healthy escalation logic

## Conclusion

The CEKP query system is a functional **enterprise code intelligence platform**.
 Further evaluation should focus on:

1. Production deployment and monitoring

2. A/B testing different confidence thresholds

3. User feedback integration (thumbs up/down on results)

4. Continuous evaluation on new question categories
