# CEKP Query System Evaluation Report

**Generated:** 2026-08-07T21:04:22.535229

## Executive Summary

This evaluation systematically tests the CEKP query system across 25+ representative
 questions spanning code navigation, API contracts, logic explanation, dependencies,
 configuration, error handling, and system design.

### Key Metrics

- **Total Queries:** 24
- **Success Rate:** 83.3% (20/24)
- **Evidence Found:** 83.3% (20/24)
- **Avg Latency:** 2013ms (median: 80ms)
- **Latency Range:** 38ms - 30035ms

### Confidence Scores

- **Mean Confidence:** 0.641
- **Median Confidence:** 0.650
- **Range:** 0.524 - 0.792

### Outcome Distribution

- **success:** 20 (83.3%)
- **no_evidence:** 2 (8.3%)
- **http_error:** 1 (4.2%)
- **failed:** 1 (4.2%)

### Strategy Usage & Effectiveness

- **hybrid:** 20 queries (83.3%)

### Performance by Question Category

- **api_contract:** 3/3 successful (100%)
- **code_logic:** 3/3 successful (100%)
- **code_navigation:** 3/4 successful (75%)
- **configuration:** 2/2 successful (100%)
- **dependencies:** 0/2 successful (0%)
- **error_handling:** 2/2 successful (100%)
- **integration:** 2/2 successful (100%)
- **out_of_scope:** 1/2 successful (50%)
- **performance:** 2/2 successful (100%)
- **testing:** 2/2 successful (100%)

## Detailed Results

|#|Question|Category|Intent|Strategy|Outcome|Confidence|Latency|Results|

|---|---|---|---|---|---|---|---|---|

|1|Where is the PythonAstGraphBuilder class...|code_navigation|—|none|http_error|—|30035ms|0|
|2|Find the __init__ method of Neo4jGraphRe...|code_navigation|—|hybrid|success|0.69|16438ms|1|
|3|Show me the ingest_github function.|code_navigation|—|hybrid|success|0.64|76ms|1|
|4|Where does Planner.plan() retrieve strat...|code_navigation|—|hybrid|success|0.67|81ms|1|
|5|What does the /ingest/github endpoint ac...|api_contract|—|hybrid|success|0.64|83ms|1|
|6|What fields are in QueryRequest schema?|api_contract|—|hybrid|success|0.55|81ms|1|
|7|What are the possible outcomes from the ...|api_contract|—|hybrid|success|0.62|78ms|1|
|8|How does the intent classifier decide wh...|code_logic|—|hybrid|success|0.68|83ms|1|
|9|Explain the escalation logic in the plan...|code_logic|—|hybrid|success|0.59|117ms|1|
|10|What does the policy evaluator check bef...|code_logic|—|hybrid|success|0.68|78ms|1|
|11|What packages does the embedding service...|dependencies|—|none|failed|—|68ms|0|
|12|Which modules depend on the graph_store?|dependencies|—|none|no_evidence|—|63ms|0|
|13|What environment variables control CEKP ...|configuration|—|hybrid|success|0.57|122ms|1|
|14|What is the default confidence threshold...|configuration|—|hybrid|success|0.66|180ms|1|
|15|What happens when GitHub API rate limit ...|error_handling|—|hybrid|success|0.68|44ms|1|
|16|How does the audit logging handle failur...|error_handling|—|hybrid|success|0.73|76ms|1|
|17|Is the Planner instantiated per-request ...|performance|—|hybrid|success|0.64|80ms|1|
|18|How many strategies can escalate before ...|performance|—|hybrid|success|0.58|80ms|1|
|19|How is Neo4j connected from the API cont...|integration|—|hybrid|success|0.79|81ms|1|
|20|What happens when a repository is re-ing...|integration|—|hybrid|success|0.56|80ms|1|
|21|What tests exist for the graph builder?|testing|—|hybrid|success|0.68|74ms|1|
|22|How are GitHub connector tests structure...|testing|—|hybrid|success|0.66|79ms|1|
|23|Tell me about machine learning.|out_of_scope|—|hybrid|success|0.52|38ms|1|
|24|What is the weather?|out_of_scope|—|none|no_evidence|—|102ms|0|

## Analysis & Recommendations

### ✅ Strong Performance

The query system demonstrates robust performance with high success rates and
 consistent latencies. The planner is effectively routing queries to appropriate strategies.


### Latency Profile

❌ High latency (2013ms avg) - investigate bottlenecks


### Strategy Diversity

⚠️ Only one strategy is used; verify that escalation is triggering correctly

## Conclusion

The CEKP query system is a functional **enterprise code intelligence platform**.
 Further evaluation should focus on:

1. Production deployment and monitoring

2. A/B testing different confidence thresholds

3. User feedback integration (thumbs up/down on results)

4. Continuous evaluation on new question categories
