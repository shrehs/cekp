import pytest

from app.planner.strategies import GraphStrategy


@pytest.mark.parametrize(
    "query,expected",
    [
        ("Which modules import app.core.config?", ("get_importers_of", "app.core.config")),
        ("What does app.core.config import?", ("get_module_imports", "app.core.config")),
        ("Which functions call embed_query?", ("get_callers_of", "embed_query")),
        ("Who calls embed_query?", ("get_callers_of", "embed_query")),

        ("Where is the PythonAstGraphBuilder class defined?",
         ("find_symbol", "PythonAstGraphBuilder")),

        ("Where is PythonAstGraphBuilder defined?",
         ("find_symbol", "PythonAstGraphBuilder")),

        ("Where is the PythonAstGraphBuilder defined?",
         ("find_symbol", "PythonAstGraphBuilder")),

        ("Find the PythonAstGraphBuilder class",
         ("find_symbol", "PythonAstGraphBuilder")),

        ("Show me the PythonAstGraphBuilder class",
         ("find_symbol", "PythonAstGraphBuilder")),

        ("Show me the ingest_github function.",
         ("find_symbol", "ingest_github")),

        ("Find the __init__ method of Neo4jGraphRepository.",
         ("find_method_of_class", "__init__:Neo4jGraphRepository")),

        ("What functions are defined in planner.py?",
         ("get_functions_defined_in", "planner.py")),

        ("List classes in planner.py",
         ("get_classes_defined_in", "planner.py")),

        ("Which classes are defined in planner.py",
         ("get_classes_defined_in", "planner.py")),
    ],
)
def test_classify(query, expected):
    assert GraphStrategy._classify(query) == expected


@pytest.mark.parametrize(
    "query",
    [
        "",
        "Hello",
        "How is the weather?",
        "What is machine learning?",
        "What is a class in object-oriented programming?",
        "Find me a good restaurant",
        "Where is my keyboard?",
    ],
)
def test_classify_returns_none_for_unknown_queries(query):
    assert GraphStrategy._classify(query) == (None, None)