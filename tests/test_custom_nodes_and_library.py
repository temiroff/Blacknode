from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from blacknode.discovery import load_node_file
from blacknode.node import Int, Text, _NODE_REGISTRY, node


class NodeDecoratorTests(unittest.TestCase):
    def test_rich_decorator_supports_direct_function_signature(self):
        @node(
            name="TestDirectRepeatNode",
            category="Tests",
            inputs={"text": Text, "times": Int(default=2)},
            outputs={"result": Text},
        )
        def repeat(text: str, times: int = 2) -> str:
            return str(text) * int(times)

        fn = _NODE_REGISTRY["TestDirectRepeatNode"]

        self.assertEqual(fn({"text": "ha"})["result"], "haha")
        self.assertEqual(fn._bn_category, "Tests")
        self.assertEqual(fn._bn_input_defaults["times"], 2)

    def test_file_discovery_registers_node_and_source_path(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "my_nodes.py"
            path.write_text(
                "from blacknode.node import Text, node\n\n"
                "@node(name='DiscoveredEcho', category='Tests', inputs={'text': Text}, outputs={'result': Text})\n"
                "def discovered_echo(text: str) -> str:\n"
                "    return text\n",
                encoding="utf-8",
            )

            result = load_node_file(path)

            self.assertTrue(result["ok"])
            self.assertIn("DiscoveredEcho", result["new_types"])
            self.assertEqual(_NODE_REGISTRY["DiscoveredEcho"]({"text": "ok"})["result"], "ok")
            self.assertEqual(_NODE_REGISTRY["DiscoveredEcho"]._bn_source_path, str(path.resolve()))


class RichNodeLibraryTests(unittest.TestCase):
    def test_keyword_rag_nodes_rank_and_build_context(self):
        chunks = _NODE_REGISTRY["TextChunker"]({
            "text": "NVIDIA NIM serves models. Blacknode builds visual workflows.",
            "chunk_size": 32,
            "overlap": 0,
        })["chunks"]
        index = _NODE_REGISTRY["KeywordIndex"]({"documents": chunks})["index"]
        results = _NODE_REGISTRY["KeywordSearch"]({"index": index, "query": "visual workflows", "top_k": 1})["results"]
        context = _NODE_REGISTRY["RAGContext"]({"results": results})["context"]

        self.assertEqual(len(results), 1)
        self.assertIn("workflows", context)

    def test_sqlite_nodes_execute_and_query(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "test.db")
            _NODE_REGISTRY["SQLiteExec"]({
                "path": db_path,
                "sql": "create table items (name text)",
                "params": [],
            })
            _NODE_REGISTRY["SQLiteExec"]({
                "path": db_path,
                "sql": "insert into items values (?)",
                "params": ["blacknode"],
            })

            result = _NODE_REGISTRY["SQLiteQuery"]({
                "path": db_path,
                "sql": "select name from items",
                "params": [],
            })

            self.assertEqual(result["rows"], [{"name": "blacknode"}])
            self.assertEqual(result["columns"], ["name"])

    def test_search_and_api_helper_nodes_are_deterministic(self):
        url = _NODE_REGISTRY["WebSearchURL"]({"query": "blacknode nvidia", "engine": "duckduckgo"})["url"]
        built = _NODE_REGISTRY["APIRequestBuilder"]({
            "base_url": "https://api.example.com",
            "path": "v1/search",
            "query": {"q": "blacknode"},
            "headers": {"Authorization": "Bearer x"},
        })
        html = '<a href="/l/?uddg=https%3A%2F%2Fexample.com">Example Result</a>'
        results = _NODE_REGISTRY["SearchResultExtractor"]({"html": html, "base_url": "https://duckduckgo.com", "limit": 1})["results"]

        self.assertIn("duckduckgo.com/html/", url)
        self.assertEqual(built["url"], "https://api.example.com/v1/search?q=blacknode")
        self.assertEqual(results, [{"title": "Example Result", "url": "https://example.com"}])

    def test_community_node_loaded_on_startup(self):
        self.assertIn("RegexExtract", _NODE_REGISTRY)
        result = _NODE_REGISTRY["RegexExtract"]({"text": "a@b.com c@d.com", "pattern": r"\S+@\S+", "limit": 1})
        self.assertEqual(result["matches"], ["a@b.com"])
