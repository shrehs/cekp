# CEKP Query System Evaluation Report

**Generated:** 2026-09-01T18:28:24.158001

## Executive Summary

This evaluation systematically tests the CEKP query system across 25+ representative
 questions spanning code navigation, API contracts, logic explanation, dependencies,
 configuration, error handling, and system design.

### Key Metrics

- **Total Queries:** 24
- **Success Rate:** 83.3% (20/24)
- **Evidence Found:** 83.3% (20/24)
- **Avg Latency:** 1494ms (median: 42ms)
- **Latency Range:** 34ms - 30019ms

### Confidence Scores

- **Mean Confidence:** 0.649
- **Median Confidence:** 0.650
- **Range:** 0.524 - 0.850

### Outcome Distribution

- **success:** 20 (83.3%)
- **no_evidence:** 2 (8.3%)
- **http_error:** 1 (4.2%)
- **failed:** 1 (4.2%)

### Strategy Usage & Effectiveness

- **hybrid:** 19 queries (79.2%)
- **graph:** 1 queries (4.2%)

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

|1|Where is the PythonAstGraphBuilder class...|code_navigation|graph|graph|success|0.85|3932ms|1|
|2|Find the __init__ method of Neo4jGraphRe...|code_navigation|—|none|http_error|—|30019ms|0|
|3|Show me the ingest_github function.|code_navigation|hybrid|hybrid|success|0.64|987ms|5|
|4|Where does Planner.plan() retrieve strat...|code_navigation|hybrid|hybrid|success|0.67|59ms|5|
|5|What does the /ingest/github endpoint ac...|api_contract|hybrid|hybrid|success|0.64|41ms|5|
|6|What fields are in QueryRequest schema?|api_contract|hybrid|hybrid|success|0.55|41ms|5|
|7|What are the possible outcomes from the ...|api_contract|hybrid|hybrid|success|0.62|42ms|5|
|8|How does the intent classifier decide wh...|code_logic|hybrid|hybrid|success|0.68|47ms|5|
|9|Explain the escalation logic in the plan...|code_logic|hybrid|hybrid|success|0.59|37ms|5|
|10|What does the policy evaluator check bef...|code_logic|hybrid|hybrid|success|0.68|39ms|5|
|11|What packages does the embedding service...|dependencies|graph|none|failed|—|76ms|0|
|12|Which modules depend on the graph_store?|dependencies|graph|none|no_evidence|—|34ms|0|
|13|What environment variables control CEKP ...|configuration|hybrid|hybrid|success|0.57|47ms|5|
|14|What is the default confidence threshold...|configuration|hybrid|hybrid|success|0.66|55ms|5|
|15|What happens when GitHub API rate limit ...|error_handling|hybrid|hybrid|success|0.68|45ms|5|
|16|How does the audit logging handle failur...|error_handling|hybrid|hybrid|success|0.73|40ms|5|
|17|Is the Planner instantiated per-request ...|performance|hybrid|hybrid|success|0.64|37ms|5|
|18|How many strategies can escalate before ...|performance|hybrid|hybrid|success|0.58|35ms|5|
|19|How is Neo4j connected from the API cont...|integration|hybrid|hybrid|success|0.79|37ms|5|
|20|What happens when a repository is re-ing...|integration|hybrid|hybrid|success|0.56|35ms|5|
|21|What tests exist for the graph builder?|testing|hybrid|hybrid|success|0.68|36ms|5|
|22|How are GitHub connector tests structure...|testing|hybrid|hybrid|success|0.66|44ms|5|
|23|Tell me about machine learning.|out_of_scope|hybrid|hybrid|success|0.52|42ms|5|
|24|What is the weather?|out_of_scope|hybrid|none|no_evidence|—|55ms|0|

## Analysis & Recommendations

### ✅ Strong Performance

The query system demonstrates robust performance with high success rates and
 consistent latencies. The planner is effectively routing queries to appropriate strategies.


### Latency Profile

⚠️ Acceptable latency (1494ms avg) - consider batch operations for scale


### Strategy Diversity

✅ Multiple strategies are being exercised, indicating healthy escalation logic

## Conclusion

The CEKP query system is a functional **enterprise code intelligence platform**.
 Further evaluation should focus on:

1. Production deployment and monitoring

2. A/B testing different confidence thresholds

3. User feedback integration (thumbs up/down on results)

4. Continuous evaluation on new question categories
