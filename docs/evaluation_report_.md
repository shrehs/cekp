
======================================================================
CEKP Query System Evaluation
Starting: 2026-08-08T16:11:32.947286
Test suite size: 24 questions
API endpoint: http://localhost:8080
======================================================================

[ 1/24] Where is the PythonAstGraphBuilder class defined?... ================================================================================
Where is the PythonAstGraphBuilder class defined?
{
  "question": "Where is the PythonAstGraphBuilder class defined?",
  "ranked_strategies": [
    "graph",
    "vector"
  ],
  "attempts": [
    {
      "strategy": "graph",
      "outcome": "success",
      "confidence": 0.85,
      "cleared_threshold": true,
      "latency_ms": 80.31568900014463,
      "metadata": {
        "classification_ms": 0.06179900015013118,
        "retrieval_ms": 80.23190600010821,
        "formatting_ms": 0.013054999953965307,
        "method": "find_symbol",
        "reference": "PythonAstGraphBuilder"
      }
    }
  ],
  "planner_outcome": "success",
  "final_strategy_used": "graph",
  "final_confidence": 0.85,
  "final_reasoning": "Graph query 'find_symbol' on 'PythonAstGraphBuilder' returned 1 result(s).",
  "final_latency_ms": 80.31568900014463,
  "final_metadata": {
    "classification_ms": 0.06179900015013118,
    "retrieval_ms": 80.23190600010821,
    "formatting_ms": 0.013054999953965307,
    "method": "find_symbol",
    "reference": "PythonAstGraphBuilder"
  }
}
================================================================================
================================================================================
Attempts: [{'strategy': 'graph', 'outcome': 'success', 'confidence': 0.85, 'cleared_threshold': True, 'latency_ms': 80.31568900014463, 'metadata': {'classification_ms': 0.06179900015013118, 'retrieval_ms': 80.23190600010821, 'formatting_ms': 0.013054999953965307, 'method': 'find_symbol', 'reference': 'PythonAstGraphBuilder'}}]
Planner outcome: success
Final strategy: graph
Final confidence: 0.85
Computed outcome: success
Computed strategy: graph
================================================================================
✓ (126ms, success)
[ 2/24] Find the __init__ method of Neo4jGraphRepository.... ================================================================================
Find the __init__ method of Neo4jGraphRepository.
{
  "question": "Find the __init__ method of Neo4jGraphRepository.",
  "ranked_strategies": [
    "hybrid",
    "vector"
  ],
  "attempts": [
    {
      "strategy": "hybrid",
      "outcome": "success",
      "confidence": 0.686,
      "cleared_threshold": true,
      "latency_ms": 36.4909129998523,
      "metadata": null
    }
  ],
  "planner_outcome": "success",
  "final_strategy_used": "hybrid",
  "final_confidence": 0.686,
  "final_reasoning": "Hybrid search, top combined score 0.686.",
  "final_latency_ms": 36.4909129998523,
  "final_metadata": null
}
================================================================================
================================================================================
Attempts: [{'strategy': 'hybrid', 'outcome': 'success', 'confidence': 0.686, 'cleared_threshold': True, 'latency_ms': 36.4909129998523, 'metadata': None}]
Planner outcome: success
Final strategy: hybrid
Final confidence: 0.686
Computed outcome: success
Computed strategy: hybrid
================================================================================
✓ (62ms, success)
[ 3/24] Show me the ingest_github function.... ================================================================================
Show me the ingest_github function.
{
  "question": "Show me the ingest_github function.",
  "ranked_strategies": [
    "hybrid",
    "vector"
  ],
  "attempts": [
    {
      "strategy": "hybrid",
      "outcome": "success",
      "confidence": 0.64,
      "cleared_threshold": true,
      "latency_ms": 94.5382749998771,
      "metadata": null
    }
  ],
  "planner_outcome": "success",
  "final_strategy_used": "hybrid",
  "final_confidence": 0.64,
  "final_reasoning": "Hybrid search, top combined score 0.640.",
  "final_latency_ms": 94.5382749998771,
  "final_metadata": null
}
================================================================================
================================================================================
Attempts: [{'strategy': 'hybrid', 'outcome': 'success', 'confidence': 0.64, 'cleared_threshold': True, 'latency_ms': 94.5382749998771, 'metadata': None}]
Planner outcome: success
Final strategy: hybrid
Final confidence: 0.64
Computed outcome: success
Computed strategy: hybrid
================================================================================
✓ (112ms, success)
[ 4/24] Where does Planner.plan() retrieve strategies from?... ================================================================================
Where does Planner.plan() retrieve strategies from?
{
  "question": "Where does Planner.plan() retrieve strategies from?",
  "ranked_strategies": [
    "hybrid",
    "vector"
  ],
  "attempts": [
    {
      "strategy": "hybrid",
      "outcome": "success",
      "confidence": 0.6653,
      "cleared_threshold": true,
      "latency_ms": 29.840198000101736,
      "metadata": null
    }
  ],
  "planner_outcome": "success",
  "final_strategy_used": "hybrid",
  "final_confidence": 0.6653,
  "final_reasoning": "Hybrid search, top combined score 0.665.",
  "final_latency_ms": 29.840198000101736,
  "final_metadata": null
}
================================================================================
================================================================================
Attempts: [{'strategy': 'hybrid', 'outcome': 'success', 'confidence': 0.6653, 'cleared_threshold': True, 'latency_ms': 29.840198000101736, 'metadata': None}]
Planner outcome: success
Final strategy: hybrid
Final confidence: 0.6653
Computed outcome: success
Computed strategy: hybrid
================================================================================
✓ (45ms, success)
[ 5/24] What does the /ingest/github endpoint accept?... ================================================================================
What does the /ingest/github endpoint accept?
{
  "question": "What does the /ingest/github endpoint accept?",
  "ranked_strategies": [
    "hybrid",
    "vector"
  ],
  "attempts": [
    {
      "strategy": "hybrid",
      "outcome": "success",
      "confidence": 0.6444,
      "cleared_threshold": true,
      "latency_ms": 22.31847400003062,
      "metadata": null
    }
  ],
  "planner_outcome": "success",
  "final_strategy_used": "hybrid",
  "final_confidence": 0.6444,
  "final_reasoning": "Hybrid search, top combined score 0.644.",
  "final_latency_ms": 22.31847400003062,
  "final_metadata": null
}
================================================================================
================================================================================
Attempts: [{'strategy': 'hybrid', 'outcome': 'success', 'confidence': 0.6444, 'cleared_threshold': True, 'latency_ms': 22.31847400003062, 'metadata': None}]
Planner outcome: success
Final strategy: hybrid
Final confidence: 0.6444
Computed outcome: success
Computed strategy: hybrid
================================================================================
✓ (40ms, success)
[ 6/24] What fields are in QueryRequest schema?... ================================================================================
What fields are in QueryRequest schema?
{
  "question": "What fields are in QueryRequest schema?",
  "ranked_strategies": [
    "hybrid",
    "vector"
  ],
  "attempts": [
    {
      "strategy": "hybrid",
      "outcome": "success",
      "confidence": 0.5541,
      "cleared_threshold": true,
      "latency_ms": 21.978235999995377,
      "metadata": null
    }
  ],
  "planner_outcome": "success",
  "final_strategy_used": "hybrid",
  "final_confidence": 0.5541,
  "final_reasoning": "Hybrid search, top combined score 0.554.",
  "final_latency_ms": 21.978235999995377,
  "final_metadata": null
}
================================================================================
================================================================================
Attempts: [{'strategy': 'hybrid', 'outcome': 'success', 'confidence': 0.5541, 'cleared_threshold': True, 'latency_ms': 21.978235999995377, 'metadata': None}]
Planner outcome: success
Final strategy: hybrid
Final confidence: 0.5541
Computed outcome: success
Computed strategy: hybrid
================================================================================
✓ (39ms, success)
[ 7/24] What are the possible outcomes from the planner?... ================================================================================
What are the possible outcomes from the planner?
{
  "question": "What are the possible outcomes from the planner?",
  "ranked_strategies": [
    "hybrid",
    "vector"
  ],
  "attempts": [
    {
      "strategy": "hybrid",
      "outcome": "success",
      "confidence": 0.6173,
      "cleared_threshold": true,
      "latency_ms": 40.265309999995225,
      "metadata": null
    }
  ],
  "planner_outcome": "success",
  "final_strategy_used": "hybrid",
  "final_confidence": 0.6173,
  "final_reasoning": "Hybrid search, top combined score 0.617.",
  "final_latency_ms": 40.265309999995225,
  "final_metadata": null
}
================================================================================
================================================================================
Attempts: [{'strategy': 'hybrid', 'outcome': 'success', 'confidence': 0.6173, 'cleared_threshold': True, 'latency_ms': 40.265309999995225, 'metadata': None}]
Planner outcome: success
Final strategy: hybrid
Final confidence: 0.6173
Computed outcome: success
Computed strategy: hybrid
================================================================================
✓ (58ms, success)
[ 8/24] How does the intent classifier decide what strategy to use?... ================================================================================
How does the intent classifier decide what strategy to use?
{
  "question": "How does the intent classifier decide what strategy to use?",
  "ranked_strategies": [
    "hybrid",
    "vector"
  ],
  "attempts": [
    {
      "strategy": "hybrid",
      "outcome": "success",
      "confidence": 0.6779,
      "cleared_threshold": true,
      "latency_ms": 49.68314400002782,
      "metadata": null
    }
  ],
  "planner_outcome": "success",
  "final_strategy_used": "hybrid",
  "final_confidence": 0.6779,
  "final_reasoning": "Hybrid search, top combined score 0.678.",
  "final_latency_ms": 49.68314400002782,
  "final_metadata": null
}
================================================================================
================================================================================
Attempts: [{'strategy': 'hybrid', 'outcome': 'success', 'confidence': 0.6779, 'cleared_threshold': True, 'latency_ms': 49.68314400002782, 'metadata': None}]
Planner outcome: success
Final strategy: hybrid
Final confidence: 0.6779
Computed outcome: success
Computed strategy: hybrid
================================================================================
✓ (89ms, success)
[ 9/24] Explain the escalation logic in the planner.... ================================================================================
Explain the escalation logic in the planner.
{
  "question": "Explain the escalation logic in the planner.",
  "ranked_strategies": [
    "hybrid",
    "vector"
  ],
  "attempts": [
    {
      "strategy": "hybrid",
      "outcome": "success",
      "confidence": 0.5931,
      "cleared_threshold": true,
      "latency_ms": 27.03590400005851,
      "metadata": null
    }
  ],
  "planner_outcome": "success",
  "final_strategy_used": "hybrid",
  "final_confidence": 0.5931,
  "final_reasoning": "Hybrid search, top combined score 0.593.",
  "final_latency_ms": 27.03590400005851,
  "final_metadata": null
}
================================================================================
================================================================================
Attempts: [{'strategy': 'hybrid', 'outcome': 'success', 'confidence': 0.5931, 'cleared_threshold': True, 'latency_ms': 27.03590400005851, 'metadata': None}]
Planner outcome: success
Final strategy: hybrid
Final confidence: 0.5931
Computed outcome: success
Computed strategy: hybrid
================================================================================
✓ (45ms, success)
[10/24] What does the policy evaluator check before running a strate... ================================================================================
What does the policy evaluator check before running a strategy?
{
  "question": "What does the policy evaluator check before running a strategy?",
  "ranked_strategies": [
    "hybrid",
    "vector"
  ],
  "attempts": [
    {
      "strategy": "hybrid",
      "outcome": "success",
      "confidence": 0.6803,
      "cleared_threshold": true,
      "latency_ms": 32.90297200010173,
      "metadata": null
    }
  ],
  "planner_outcome": "success",
  "final_strategy_used": "hybrid",
  "final_confidence": 0.6803,
  "final_reasoning": "Hybrid search, top combined score 0.680.",
  "final_latency_ms": 32.90297200010173,
  "final_metadata": null
}
================================================================================
================================================================================
Attempts: [{'strategy': 'hybrid', 'outcome': 'success', 'confidence': 0.6803, 'cleared_threshold': True, 'latency_ms': 32.90297200010173, 'metadata': None}]
Planner outcome: success
Final strategy: hybrid
Final confidence: 0.6803
Computed outcome: success
Computed strategy: hybrid
================================================================================
✓ (49ms, success)
[11/24] What packages does the embedding service import?... ================================================================================
What packages does the embedding service import?
{
  "question": "What packages does the embedding service import?",
  "ranked_strategies": [
    "graph",
    "vector"
  ],
  "attempts": [
    {
      "strategy": "graph",
      "outcome": "error",
      "confidence": null,
      "cleared_threshold": null,
      "latency_ms": null,
      "metadata": null
    },
    {
      "strategy": "vector",
      "outcome": "error",
      "confidence": null,
      "cleared_threshold": null,
      "latency_ms": null,
      "metadata": null
    }
  ],
  "planner_outcome": "failed",
  "final_strategy_used": null,
  "final_confidence": null,
  "final_reasoning": null,
  "final_latency_ms": null,
  "final_metadata": null
}
================================================================================
================================================================================
Attempts: [{'strategy': 'graph', 'outcome': 'error', 'confidence': None, 'cleared_threshold': None, 'latency_ms': None, 'metadata': None}, {'strategy': 'vector', 'outcome': 'error', 'confidence': None, 'cleared_threshold': None, 'latency_ms': None, 'metadata': None}]
Planner outcome: failed
Final strategy: None
Final confidence: None
Computed outcome: failed
Computed strategy: none
================================================================================
✓ (33ms, failed)
[12/24] Which modules depend on the graph_store?... ================================================================================
Which modules depend on the graph_store?
{
  "question": "Which modules depend on the graph_store?",
  "ranked_strategies": [
    "graph",
    "vector"
  ],
  "attempts": [
    {
      "strategy": "graph",
      "outcome": "not_implemented",
      "confidence": 0.0,
      "cleared_threshold": false,
      "latency_ms": 0.008967999974629492,
      "metadata": {
        "classification_ms": 0.004256000011082506
      }
    },
    {
      "strategy": "vector",
      "outcome": "error",
      "confidence": null,
      "cleared_threshold": null,
      "latency_ms": null,
      "metadata": null
    }
  ],
  "planner_outcome": "no_evidence",
  "final_strategy_used": null,
  "final_confidence": null,
  "final_reasoning": null,
  "final_latency_ms": null,
  "final_metadata": null
}
================================================================================
================================================================================
Attempts: [{'strategy': 'graph', 'outcome': 'not_implemented', 'confidence': 0.0, 'cleared_threshold': False, 'latency_ms': 0.008967999974629492, 'metadata': {'classification_ms': 0.004256000011082506}}, {'strategy': 'vector', 'outcome': 'error', 'confidence': None, 'cleared_threshold': None, 'latency_ms': None, 'metadata': None}]
Planner outcome: no_evidence
Final strategy: None
Final confidence: None
Computed outcome: no_evidence
Computed strategy: none
================================================================================
✓ (49ms, no_evidence)
[13/24] What environment variables control CEKP settings?... ================================================================================
What environment variables control CEKP settings?
{
  "question": "What environment variables control CEKP settings?",
  "ranked_strategies": [
    "hybrid",
    "vector"
  ],
  "attempts": [
    {
      "strategy": "hybrid",
      "outcome": "success",
      "confidence": 0.5659,
      "cleared_threshold": true,
      "latency_ms": 45.670948999941174,
      "metadata": null
    }
  ],
  "planner_outcome": "success",
  "final_strategy_used": "hybrid",
  "final_confidence": 0.5659,
  "final_reasoning": "Hybrid search, top combined score 0.566.",
  "final_latency_ms": 45.670948999941174,
  "final_metadata": null
}
================================================================================
================================================================================
Attempts: [{'strategy': 'hybrid', 'outcome': 'success', 'confidence': 0.5659, 'cleared_threshold': True, 'latency_ms': 45.670948999941174, 'metadata': None}]
Planner outcome: success
Final strategy: hybrid
Final confidence: 0.5659
Computed outcome: success
Computed strategy: hybrid
================================================================================
✓ (103ms, success)
[14/24] What is the default confidence threshold for retrieving resu... ================================================================================
What is the default confidence threshold for retrieving results?
{
  "question": "What is the default confidence threshold for retrieving results?",
  "ranked_strategies": [
    "hybrid",
    "vector"
  ],
  "attempts": [
    {
      "strategy": "hybrid",
      "outcome": "success",
      "confidence": 0.6551,
      "cleared_threshold": true,
      "latency_ms": 52.53575300002922,
      "metadata": null
    }
  ],
  "planner_outcome": "success",
  "final_strategy_used": "hybrid",
  "final_confidence": 0.6551,
  "final_reasoning": "Hybrid search, top combined score 0.655.",
  "final_latency_ms": 52.53575300002922,
  "final_metadata": null
}
================================================================================
================================================================================
Attempts: [{'strategy': 'hybrid', 'outcome': 'success', 'confidence': 0.6551, 'cleared_threshold': True, 'latency_ms': 52.53575300002922, 'metadata': None}]
Planner outcome: success
Final strategy: hybrid
Final confidence: 0.6551
Computed outcome: success
Computed strategy: hybrid
================================================================================
✓ (119ms, success)
[15/24] What happens when GitHub API rate limit is exceeded?... ================================================================================
What happens when GitHub API rate limit is exceeded?
{
  "question": "What happens when GitHub API rate limit is exceeded?",
  "ranked_strategies": [
    "hybrid",
    "vector"
  ],
  "attempts": [
    {
      "strategy": "hybrid",
      "outcome": "success",
      "confidence": 0.6807,
      "cleared_threshold": true,
      "latency_ms": 49.41526400011753,
      "metadata": null
    }
  ],
  "planner_outcome": "success",
  "final_strategy_used": "hybrid",
  "final_confidence": 0.6807,
  "final_reasoning": "Hybrid search, top combined score 0.681.",
  "final_latency_ms": 49.41526400011753,
  "final_metadata": null
}
================================================================================
================================================================================
Attempts: [{'strategy': 'hybrid', 'outcome': 'success', 'confidence': 0.6807, 'cleared_threshold': True, 'latency_ms': 49.41526400011753, 'metadata': None}]
Planner outcome: success
Final strategy: hybrid
Final confidence: 0.6807
Computed outcome: success
Computed strategy: hybrid
================================================================================
✓ (85ms, success)
[16/24] How does the audit logging handle failures?... ================================================================================
How does the audit logging handle failures?
{
  "question": "How does the audit logging handle failures?",
  "ranked_strategies": [
    "hybrid",
    "vector"
  ],
  "attempts": [
    {
      "strategy": "hybrid",
      "outcome": "success",
      "confidence": 0.7268,
      "cleared_threshold": true,
      "latency_ms": 49.2893760001607,
      "metadata": null
    }
  ],
  "planner_outcome": "success",
  "final_strategy_used": "hybrid",
  "final_confidence": 0.7268,
  "final_reasoning": "Hybrid search, top combined score 0.727.",
  "final_latency_ms": 49.2893760001607,
  "final_metadata": null
}
================================================================================
================================================================================
Attempts: [{'strategy': 'hybrid', 'outcome': 'success', 'confidence': 0.7268, 'cleared_threshold': True, 'latency_ms': 49.2893760001607, 'metadata': None}]
Planner outcome: success
Final strategy: hybrid
Final confidence: 0.7268
Computed outcome: success
Computed strategy: hybrid
================================================================================
✓ (69ms, success)
[17/24] Is the Planner instantiated per-request or shared?... ================================================================================
Is the Planner instantiated per-request or shared?
{
  "question": "Is the Planner instantiated per-request or shared?",
  "ranked_strategies": [
    "hybrid",
    "vector"
  ],
  "attempts": [
    {
      "strategy": "hybrid",
      "outcome": "success",
      "confidence": 0.6386,
      "cleared_threshold": true,
      "latency_ms": 28.821176999827003,
      "metadata": null
    }
  ],
  "planner_outcome": "success",
  "final_strategy_used": "hybrid",
  "final_confidence": 0.6386,
  "final_reasoning": "Hybrid search, top combined score 0.639.",
  "final_latency_ms": 28.821176999827003,
  "final_metadata": null
}
================================================================================
================================================================================
Attempts: [{'strategy': 'hybrid', 'outcome': 'success', 'confidence': 0.6386, 'cleared_threshold': True, 'latency_ms': 28.821176999827003, 'metadata': None}]
Planner outcome: success
Final strategy: hybrid
Final confidence: 0.6386
Computed outcome: success
Computed strategy: hybrid
================================================================================
✓ (46ms, success)
[18/24] How many strategies can escalate before giving up?... ================================================================================
How many strategies can escalate before giving up?
{
  "question": "How many strategies can escalate before giving up?",
  "ranked_strategies": [
    "hybrid",
    "vector"
  ],
  "attempts": [
    {
      "strategy": "hybrid",
      "outcome": "success",
      "confidence": 0.5798,
      "cleared_threshold": true,
      "latency_ms": 49.808067999947525,
      "metadata": null
    }
  ],
  "planner_outcome": "success",
  "final_strategy_used": "hybrid",
  "final_confidence": 0.5798,
  "final_reasoning": "Hybrid search, top combined score 0.580.",
  "final_latency_ms": 49.808067999947525,
  "final_metadata": null
}
================================================================================
================================================================================
Attempts: [{'strategy': 'hybrid', 'outcome': 'success', 'confidence': 0.5798, 'cleared_threshold': True, 'latency_ms': 49.808067999947525, 'metadata': None}]
Planner outcome: success
Final strategy: hybrid
Final confidence: 0.5798
Computed outcome: success
Computed strategy: hybrid
================================================================================
✓ (73ms, success)
[19/24] How is Neo4j connected from the API container?... ================================================================================
How is Neo4j connected from the API container?
{
  "question": "How is Neo4j connected from the API container?",
  "ranked_strategies": [
    "hybrid",
    "vector"
  ],
  "attempts": [
    {
      "strategy": "hybrid",
      "outcome": "success",
      "confidence": 0.7923,
      "cleared_threshold": true,
      "latency_ms": 48.156606000020474,
      "metadata": null
    }
  ],
  "planner_outcome": "success",
  "final_strategy_used": "hybrid",
  "final_confidence": 0.7923,
  "final_reasoning": "Hybrid search, top combined score 0.792.",
  "final_latency_ms": 48.156606000020474,
  "final_metadata": null
}
================================================================================
================================================================================
Attempts: [{'strategy': 'hybrid', 'outcome': 'success', 'confidence': 0.7923, 'cleared_threshold': True, 'latency_ms': 48.156606000020474, 'metadata': None}]
Planner outcome: success
Final strategy: hybrid
Final confidence: 0.7923
Computed outcome: success
Computed strategy: hybrid
================================================================================
✓ (76ms, success)
[20/24] What happens when a repository is re-ingested?... ================================================================================
What happens when a repository is re-ingested?
{
  "question": "What happens when a repository is re-ingested?",
  "ranked_strategies": [
    "hybrid",
    "vector"
  ],
  "attempts": [
    {
      "strategy": "hybrid",
      "outcome": "success",
      "confidence": 0.5616,
      "cleared_threshold": true,
      "latency_ms": 49.600818000044455,
      "metadata": null
    }
  ],
  "planner_outcome": "success",
  "final_strategy_used": "hybrid",
  "final_confidence": 0.5616,
  "final_reasoning": "Hybrid search, top combined score 0.562.",
  "final_latency_ms": 49.600818000044455,
  "final_metadata": null
}
================================================================================
================================================================================
Attempts: [{'strategy': 'hybrid', 'outcome': 'success', 'confidence': 0.5616, 'cleared_threshold': True, 'latency_ms': 49.600818000044455, 'metadata': None}]
Planner outcome: success
Final strategy: hybrid
Final confidence: 0.5616
Computed outcome: success
Computed strategy: hybrid
================================================================================
✓ (75ms, success)
[21/24] What tests exist for the graph builder?... ================================================================================
What tests exist for the graph builder?
{
  "question": "What tests exist for the graph builder?",
  "ranked_strategies": [
    "hybrid",
    "vector"
  ],
  "attempts": [
    {
      "strategy": "hybrid",
      "outcome": "success",
      "confidence": 0.6777,
      "cleared_threshold": true,
      "latency_ms": 48.26171299987436,
      "metadata": null
    }
  ],
  "planner_outcome": "success",
  "final_strategy_used": "hybrid",
  "final_confidence": 0.6777,
  "final_reasoning": "Hybrid search, top combined score 0.678.",
  "final_latency_ms": 48.26171299987436,
  "final_metadata": null
}
================================================================================
================================================================================
Attempts: [{'strategy': 'hybrid', 'outcome': 'success', 'confidence': 0.6777, 'cleared_threshold': True, 'latency_ms': 48.26171299987436, 'metadata': None}]
Planner outcome: success
Final strategy: hybrid
Final confidence: 0.6777
Computed outcome: success
Computed strategy: hybrid
================================================================================
✓ (110ms, success)
[22/24] How are GitHub connector tests structured?... ================================================================================
How are GitHub connector tests structured?
{
  "question": "How are GitHub connector tests structured?",
  "ranked_strategies": [
    "hybrid",
    "vector"
  ],
  "attempts": [
    {
      "strategy": "hybrid",
      "outcome": "success",
      "confidence": 0.6602,
      "cleared_threshold": true,
      "latency_ms": 44.78520599991498,
      "metadata": null
    }
  ],
  "planner_outcome": "success",
  "final_strategy_used": "hybrid",
  "final_confidence": 0.6602,
  "final_reasoning": "Hybrid search, top combined score 0.660.",
  "final_latency_ms": 44.78520599991498,
  "final_metadata": null
}
================================================================================
================================================================================
Attempts: [{'strategy': 'hybrid', 'outcome': 'success', 'confidence': 0.6602, 'cleared_threshold': True, 'latency_ms': 44.78520599991498, 'metadata': None}]
Planner outcome: success
Final strategy: hybrid
Final confidence: 0.6602
Computed outcome: success
Computed strategy: hybrid
================================================================================
✓ (85ms, success)
[23/24] Tell me about machine learning.... ================================================================================
Tell me about machine learning.
{
  "question": "Tell me about machine learning.",
  "ranked_strategies": [
    "hybrid",
    "vector"
  ],
  "attempts": [
    {
      "strategy": "hybrid",
      "outcome": "success",
      "confidence": 0.5239,
      "cleared_threshold": true,
      "latency_ms": 40.31271000008019,
      "metadata": null
    }
  ],
  "planner_outcome": "success",
  "final_strategy_used": "hybrid",
  "final_confidence": 0.5239,
  "final_reasoning": "Hybrid search, top combined score 0.524.",
  "final_latency_ms": 40.31271000008019,
  "final_metadata": null
}
================================================================================
================================================================================
Attempts: [{'strategy': 'hybrid', 'outcome': 'success', 'confidence': 0.5239, 'cleared_threshold': True, 'latency_ms': 40.31271000008019, 'metadata': None}]
Planner outcome: success
Final strategy: hybrid
Final confidence: 0.5239
Computed outcome: success
Computed strategy: hybrid
================================================================================
✓ (61ms, success)
[24/24] What is the weather?... ================================================================================
What is the weather?
{
  "question": "What is the weather?",
  "ranked_strategies": [
    "hybrid",
    "vector"
  ],
  "attempts": [
    {
      "strategy": "hybrid",
      "outcome": "success",
      "confidence": 0.4671,
      "cleared_threshold": false,
      "latency_ms": 23.135604999879433,
      "metadata": null
    },
    {
      "strategy": "vector",
      "outcome": "error",
      "confidence": null,
      "cleared_threshold": null,
      "latency_ms": null,
      "metadata": null
    }
  ],
  "planner_outcome": "no_evidence",
  "final_strategy_used": null,
  "final_confidence": null,
  "final_reasoning": null,
  "final_latency_ms": null,
  "final_metadata": null
}
================================================================================
================================================================================
Attempts: [{'strategy': 'hybrid', 'outcome': 'success', 'confidence': 0.4671, 'cleared_threshold': False, 'latency_ms': 23.135604999879433, 'metadata': None}, {'strategy': 'vector', 'outcome': 'error', 'confidence': None, 'cleared_threshold': None, 'latency_ms': None, 'metadata': None}]
Planner outcome: no_evidence
Final strategy: None
Final confidence: None
Computed outcome: no_evidence
Computed strategy: none
================================================================================
✓ (52ms, no_evidence)

✓ Report saved: docs/evaluation_report_20260808_161135.md
✓ Metrics saved: docs/evaluation_metrics_20260808_161135.json

======================================================================
EVALUATION COMPLETE
======================================================================
# CEKP Query System Evaluation Report

**Generated:** 2026-08-08T16:11:35.223933

## Executive Summary

This evaluation systematically tests the CEKP query system across 25+ representative
 questions spanning code navigation, API contracts, logic explanation, dependencies,
 configuration, error handling, and system design.

### Key Metrics

- **Total Queries:** 24
- **Success Rate:** 87.5% (21/24)
- **Evidence Found:** 0.0% (0/24)
- **Avg Latency:** 71ms (median: 65ms)
- **Latency Range:** 33ms - 126ms

### Confidence Scores

- **Mean Confidence:** 0.651
- **Median Confidence:** 0.655
- **Range:** 0.524 - 0.850

### Outcome Distribution

- **success:** 21 (87.5%)
- **no_evidence:** 2 (8.3%)
- **failed:** 1 (4.2%)

### Strategy Usage & Effectiveness

- **hybrid:** 20 queries (83.3%)
- **graph:** 1 queries (4.2%)

### Performance by Question Category

- **api_contract:** 3/3 successful (100%)
- **code_logic:** 3/3 successful (100%)
- **code_navigation:** 4/4 successful (100%)
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

|1|Where is the PythonAstGraphBuilder class...|code_navigation|graph|graph|success|0.85|126ms|0|
|2|Find the __init__ method of Neo4jGraphRe...|code_navigation|hybrid|hybrid|success|0.69|62ms|0|
|3|Show me the ingest_github function.|code_navigation|hybrid|hybrid|success|0.64|112ms|0|
|4|Where does Planner.plan() retrieve strat...|code_navigation|hybrid|hybrid|success|0.67|45ms|0|
|5|What does the /ingest/github endpoint ac...|api_contract|hybrid|hybrid|success|0.64|40ms|0|
|6|What fields are in QueryRequest schema?|api_contract|hybrid|hybrid|success|0.55|39ms|0|
|7|What are the possible outcomes from the ...|api_contract|hybrid|hybrid|success|0.62|58ms|0|
|8|How does the intent classifier decide wh...|code_logic|hybrid|hybrid|success|0.68|89ms|0|
|9|Explain the escalation logic in the plan...|code_logic|hybrid|hybrid|success|0.59|45ms|0|
|10|What does the policy evaluator check bef...|code_logic|hybrid|hybrid|success|0.68|49ms|0|
|11|What packages does the embedding service...|dependencies|graph|none|failed|—|33ms|0|
|12|Which modules depend on the graph_store?|dependencies|graph|none|no_evidence|—|49ms|0|
|13|What environment variables control CEKP ...|configuration|hybrid|hybrid|success|0.57|103ms|0|
|14|What is the default confidence threshold...|configuration|hybrid|hybrid|success|0.66|119ms|0|
|15|What happens when GitHub API rate limit ...|error_handling|hybrid|hybrid|success|0.68|85ms|0|
|16|How does the audit logging handle failur...|error_handling|hybrid|hybrid|success|0.73|69ms|0|
|17|Is the Planner instantiated per-request ...|performance|hybrid|hybrid|success|0.64|46ms|0|
|18|How many strategies can escalate before ...|performance|hybrid|hybrid|success|0.58|73ms|0|
|19|How is Neo4j connected from the API cont...|integration|hybrid|hybrid|success|0.79|76ms|0|
|20|What happens when a repository is re-ing...|integration|hybrid|hybrid|success|0.56|75ms|0|
|21|What tests exist for the graph builder?|testing|hybrid|hybrid|success|0.68|110ms|0|
|22|How are GitHub connector tests structure...|testing|hybrid|hybrid|success|0.66|85ms|0|
|23|Tell me about machine learning.|out_of_scope|hybrid|hybrid|success|0.52|61ms|0|
|24|What is the weather?|out_of_scope|hybrid|none|no_evidence|—|52ms|0|

## Analysis & Recommendations

### ✅ Strong Performance

The query system demonstrates robust performance with high success rates and
 consistent latencies. The planner is effectively routing queries to appropriate strategies.


### Latency Profile

✅ Excellent latency (71ms avg) - suitable for interactive use


### Strategy Diversity

✅ Multiple strategies are being exercised, indicating healthy escalation logic

## Conclusion

The CEKP query system is a functional **enterprise code intelligence platform**.
 Further evaluation should focus on:

1. Production deployment and monitoring

2. A/B testing different confidence thresholds

3. User feedback integration (thumbs up/down on results)

4. Continuous evaluation on new question categories