# CEKP Query System Evaluation Report

**Generated:** 2026-10-08T03:06:58.180863

## Executive Summary

This evaluation systematically tests the CEKP query system across 25+ representative
 questions spanning code navigation, API contracts, logic explanation, dependencies,
 configuration, error handling, and system design.

### Key Metrics

- **Total Queries:** 24
- **Planner Success Rate:** 91.7% (22/24)
- **Evidence Found:** 91.7% (22/24)
- **Evidence-backed Success:** 91.7% (22/24)
- **No Evidence:** 8.3% (2/24)
- **Policy Denied:** 0.0% (0/24)
- **HTTP/Infrastructure Errors:** 0.0% (0/24)
- **Success Without Evidence:** 0
- **Evaluated Relevance:** 100.0% (10/10)
- **Latency:** p50 59ms / p95 113ms / p99 120ms
- **Latency Range:** 36ms - 121ms

### Confidence Scores

- **Mean Confidence:** 0.698
- **Median Confidence:** 0.653
- **Range:** 0.575 - 0.862

### Outcome Distribution

- **success:** 22 (91.7%)
- **no_evidence:** 2 (8.3%)

### Strategy Usage & Effectiveness

- **hybrid:** 20 queries (83.3%)
- **graph:** 1 queries (4.2%)
- **vector:** 1 queries (4.2%)

### Attempted Strategy Distribution

- **hybrid:** 21 attempts
- **graph:** 3 attempts
- **vector:** 3 attempts

### Performance by Question Category

- **api_contract:** 3/3 successful (100%)
- **code_logic:** 3/3 successful (100%)
- **code_navigation:** 4/4 successful (100%)
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

|1|Where is the PythonAstGraphBuilder class...|code_navigation|graph|graph|success|0.85|121ms|1|
|2|Find the __init__ method of Neo4jGraphRe...|code_navigation|hybrid|hybrid|success|0.75|115ms|5|
|3|Show me the ingest_github function.|code_navigation|hybrid|hybrid|success|0.64|98ms|5|
|4|Where does Planner.plan() retrieve strat...|code_navigation|hybrid|hybrid|success|0.82|48ms|5|
|5|What does the /ingest/github endpoint ac...|api_contract|hybrid|hybrid|success|0.64|66ms|5|
|6|What fields are in QueryRequest schema?|api_contract|hybrid|hybrid|success|0.59|87ms|5|
|7|What are the possible outcomes from the ...|api_contract|hybrid|hybrid|success|0.65|76ms|5|
|8|How does the intent classifier decide wh...|code_logic|hybrid|hybrid|success|0.84|53ms|5|
|9|Explain the escalation logic in the plan...|code_logic|hybrid|hybrid|success|0.64|48ms|5|
|10|What does the policy evaluator check bef...|code_logic|hybrid|hybrid|success|0.73|45ms|5|
|11|What packages does the embedding service...|dependencies|graph|none|no_evidence|—|43ms|0|
|12|Which modules depend on the graph_store?|dependencies|graph|vector|success|0.58|38ms|5|
|13|What environment variables control CEKP ...|configuration|hybrid|hybrid|success|0.62|49ms|5|
|14|What is the default confidence threshold...|configuration|hybrid|hybrid|success|0.78|47ms|5|
|15|What happens when GitHub API rate limit ...|error_handling|hybrid|hybrid|success|0.64|40ms|5|
|16|How does the audit logging handle failur...|error_handling|hybrid|hybrid|success|0.73|52ms|5|
|17|Is the Planner instantiated per-request ...|performance|hybrid|hybrid|success|0.86|65ms|5|
|18|How many strategies can escalate before ...|performance|hybrid|hybrid|success|0.64|42ms|5|
|19|How is Neo4j connected from the API cont...|integration|hybrid|hybrid|success|0.79|36ms|5|
|20|What happens when a repository is re-ing...|integration|hybrid|hybrid|success|0.64|104ms|5|
|21|What tests exist for the graph builder?|testing|hybrid|hybrid|success|0.71|67ms|5|
|22|How are GitHub connector tests structure...|testing|hybrid|hybrid|success|0.66|66ms|5|
|23|Tell me about machine learning.|out_of_scope|hybrid|hybrid|success|0.58|65ms|3|
|24|What is the weather?|out_of_scope|hybrid|none|no_evidence|—|78ms|0|

## Analysis & Recommendations

### ✅ Strong Performance

The query system demonstrates robust performance with high success rates and
 consistent latencies. The planner is effectively routing queries to appropriate strategies.


### Latency Profile

✅ Excellent latency (65ms avg) - suitable for interactive use


### Strategy Diversity

✅ Multiple strategies are being exercised, indicating healthy escalation logic

## Conclusion

The CEKP query system is a functional **enterprise code intelligence platform**.
 Further evaluation should focus on:

1. Production deployment and monitoring

2. A/B testing different confidence thresholds

3. User feedback integration (thumbs up/down on results)

4. Continuous evaluation on new question categories
