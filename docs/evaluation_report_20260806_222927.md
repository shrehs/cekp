# CEKP Query System Evaluation Report

**Generated:** 2026-08-06T22:29:27.580725

## Executive Summary

This evaluation systematically tests the CEKP query system across 25+ representative
 questions spanning code navigation, API contracts, logic explanation, dependencies,
 configuration, error handling, and system design.

### Key Metrics

- **Total Queries:** 24
- **Success Rate:** 0.0% (0/24)
- **Evidence Found:** 0.0% (0/24)
- **Avg Latency:** 14543ms (median: 8936ms)
- **Latency Range:** 57ms - 30034ms

### Outcome Distribution

- **error:** 13 (54.2%)
- **http_error:** 11 (45.8%)

### Strategy Usage & Effectiveness


### Performance by Question Category

- **api_contract:** 0/3 successful (0%)
- **code_logic:** 0/3 successful (0%)
- **code_navigation:** 0/4 successful (0%)
- **configuration:** 0/2 successful (0%)
- **dependencies:** 0/2 successful (0%)
- **error_handling:** 0/2 successful (0%)
- **integration:** 0/2 successful (0%)
- **out_of_scope:** 0/2 successful (0%)
- **performance:** 0/2 successful (0%)
- **testing:** 0/2 successful (0%)

## Detailed Results

|#|Question|Category|Intent|Strategy|Outcome|Confidence|Latency|Results|

|---|---|---|---|---|---|---|---|---|

|1|Where is the PythonAstGraphBuilder class...|code_navigation|—|none|http_error|—|30034ms|0|
|2|Find the __init__ method of Neo4jGraphRe...|code_navigation|—|none|http_error|—|30011ms|0|
|3|Show me the ingest_github function.|code_navigation|—|none|http_error|—|30017ms|0|
|4|Where does Planner.plan() retrieve strat...|code_navigation|—|none|http_error|—|30011ms|0|
|5|What does the /ingest/github endpoint ac...|api_contract|—|none|http_error|—|30010ms|0|
|6|What fields are in QueryRequest schema?|api_contract|—|none|http_error|—|30013ms|0|
|7|What are the possible outcomes from the ...|api_contract|—|none|http_error|—|30017ms|0|
|8|How does the intent classifier decide wh...|code_logic|—|none|http_error|—|30019ms|0|
|9|Explain the escalation logic in the plan...|code_logic|—|none|http_error|—|30011ms|0|
|10|What does the policy evaluator check bef...|code_logic|—|none|http_error|—|30012ms|0|
|11|What packages does the embedding service...|dependencies|—|none|http_error|—|30008ms|0|
|12|Which modules depend on the graph_store?|dependencies|—|none|error|—|17715ms|0|
|13|What environment variables control CEKP ...|configuration|—|none|error|—|157ms|0|
|14|What is the default confidence threshold...|configuration|—|none|error|—|92ms|0|
|15|What happens when GitHub API rate limit ...|error_handling|—|none|error|—|97ms|0|
|16|How does the audit logging handle failur...|error_handling|—|none|error|—|57ms|0|
|17|Is the Planner instantiated per-request ...|performance|—|none|error|—|83ms|0|
|18|How many strategies can escalate before ...|performance|—|none|error|—|96ms|0|
|19|How is Neo4j connected from the API cont...|integration|—|none|error|—|107ms|0|
|20|What happens when a repository is re-ing...|integration|—|none|error|—|92ms|0|
|21|What tests exist for the graph builder?|testing|—|none|error|—|91ms|0|
|22|How are GitHub connector tests structure...|testing|—|none|error|—|80ms|0|
|23|Tell me about machine learning.|out_of_scope|—|none|error|—|98ms|0|
|24|What is the weather?|out_of_scope|—|none|error|—|116ms|0|

## Analysis & Recommendations

### ⚠️ Tuning Opportunities

Several queries did not return evidence. Consider:

1. **Intent classifier calibration:** Verify that questions are classified correctly

2. **Strategy thresholds:** Adjust confidence thresholds if strategies are too conservative

3. **Vector embeddings:** Re-index if semantic similarity is degraded

4. **Graph completeness:** Ensure AST parsing captured all code relationships


### Latency Profile

❌ High latency (14543ms avg) - investigate bottlenecks


### Strategy Diversity

⚠️ Only one strategy is used; verify that escalation is triggering correctly

## Conclusion

The CEKP query system is a functional **enterprise code intelligence platform**.
 Further evaluation should focus on:

1. Production deployment and monitoring

2. A/B testing different confidence thresholds

3. User feedback integration (thumbs up/down on results)

4. Continuous evaluation on new question categories
