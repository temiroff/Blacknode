from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from blacknode.node import _NODE_REGISTRY


class NvidiaRagNodeTests(unittest.TestCase):
    def test_embedding_builds_current_nvidia_payload(self):
        captured = {}

        def fake_post(url, api_key, body, timeout):
            captured.update(url=url, api_key=api_key, body=body, timeout=timeout)
            return True, 200, {
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ],
                "usage": {"total_tokens": 8},
            }

        with patch("blacknode.nodes.nvidia_rag._post_json", side_effect=fake_post):
            result = _NODE_REGISTRY["NVIDIAEmbedding"]({
                "content": [
                    {"id": "a", "text": "alpha", "title": "Alpha"},
                    {"id": "b", "text": "beta", "title": "Beta"},
                ],
                "input_type": "passage",
                "model": "nvidia/llama-nemotron-embed-1b-v2",
                "endpoint_url": "http://localhost:8000/v1",
                "api_key": "secret",
                "dimensions": 384,
                "timeout": 5,
            })

        self.assertEqual(captured["url"], "http://localhost:8000/v1/embeddings")
        self.assertEqual(captured["body"]["input_type"], "passage")
        self.assertEqual(captured["body"]["dimensions"], 384)
        self.assertEqual(result["embeddings"], [[1.0, 0.0], [0.0, 1.0]])
        self.assertEqual(result["items"][0]["metadata"]["title"], "Alpha")
        self.assertEqual(result["metrics"]["dimensions"], 2)

    def test_vector_search_orders_by_cosine_similarity(self):
        result = _NODE_REGISTRY["NVIDIAVectorSearch"]({
            "documents": [
                {"id": "a", "text": "alpha"},
                {"id": "b", "text": "beta"},
                {"id": "c", "text": "gamma"},
            ],
            "embeddings": [[1.0, 0.0], [0.8, 0.2], [0.0, 1.0]],
            "query_embedding": [1.0, 0.0],
            "top_k": 2,
        })

        self.assertEqual([item["id"] for item in result["results"]], ["a", "b"])
        self.assertEqual(result["results"][0]["rank"], 1)
        self.assertEqual(result["metrics"]["returned"], 2)

    def test_rerank_supports_hosted_endpoint_and_preserves_sources(self):
        captured = {}

        def fake_post(url, api_key, body, timeout):
            captured.update(url=url, body=body)
            return True, 200, {
                "rankings": [
                    {"index": 1, "logit": 3.5},
                    {"index": 0, "logit": 1.25},
                ],
                "usage": {"total_tokens": 20},
            }

        hosted = (
            "https://ai.api.nvidia.com/v1/retrieval/"
            "nvidia/llama-nemotron-rerank-1b-v2/reranking"
        )
        with patch("blacknode.nodes.nvidia_rag._post_json", side_effect=fake_post):
            result = _NODE_REGISTRY["NVIDIARerank"]({
                "query": "query expansion",
                "results": [
                    {
                        "id": "a",
                        "text": "first",
                        "score": 0.8,
                        "metadata": {"url": "https://example.com/a"},
                    },
                    {
                        "id": "b",
                        "text": "second",
                        "score": 0.7,
                        "metadata": {"url": "https://example.com/b"},
                    },
                ],
                "endpoint_url": hosted,
                "model": "nvidia/llama-nemotron-rerank-1b-v2",
                "top_k": 2,
            })

        self.assertEqual(captured["url"], hosted)
        self.assertEqual(captured["body"]["query"], {"text": "query expansion"})
        self.assertEqual([item["id"] for item in result["results"]], ["b", "a"])
        self.assertEqual(result["results"][0]["metadata"]["url"], "https://example.com/b")
        self.assertEqual(result["results"][0]["retrieval_score"], 0.7)
        self.assertEqual(result["results"][0]["rerank_score"], 3.5)

    def test_rerank_appends_local_ranking_path(self):
        captured = {}

        def fake_post(url, api_key, body, timeout):
            captured["url"] = url
            return True, 200, {"rankings": [{"index": 0, "logit": 1.0}]}

        with patch("blacknode.nodes.nvidia_rag._post_json", side_effect=fake_post):
            _NODE_REGISTRY["NVIDIARerank"]({
                "query": "test",
                "results": [{"id": "a", "text": "passage"}],
                "endpoint_url": "http://localhost:8000/v1",
            })

        self.assertEqual(captured["url"], "http://localhost:8000/v1/ranking")

    def test_query_rewrite_parses_json_response(self):
        class FakeProvider:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def complete(self, *args, **kwargs):
                return SimpleNamespace(text=(
                    '{"core_query":"limited language data",'
                    '"rewritten_query":"low-resource languages multilingual LLM training",'
                    '"terms":["low-resource languages","multilingual LLMs"]}'
                ))

        with patch("blacknode.nodes.nvidia_rag.OpenAIProvider", FakeProvider):
            result = _NODE_REGISTRY["NIMQueryRewrite"]({
                "query": "How do I train AI when a language has little data?",
                "strategy": "Q2E",
            })

        self.assertEqual(result["core_query"], "limited language data")
        self.assertIn("multilingual LLM", result["rewritten_query"])
        self.assertEqual(result["terms"][0], "low-resource languages")

    def test_citation_answer_returns_only_referenced_sources(self):
        class FakeProvider:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def complete(self, *args, **kwargs):
                return SimpleNamespace(text="Q2E adds related terminology before retrieval [2].")

        with patch("blacknode.nodes.nvidia_rag.OpenAIProvider", FakeProvider):
            result = _NODE_REGISTRY["NIMCitationAnswer"]({
                "query": "What does Q2E do?",
                "results": [
                    {"id": "a", "text": "Unrelated.", "metadata": {"title": "A"}},
                    {
                        "id": "b",
                        "text": "Q2E adds related terms.",
                        "metadata": {"title": "NVIDIA RAG", "url": "https://example.com/rag"},
                    },
                ],
            })

        self.assertEqual(len(result["citations"]), 1)
        self.assertEqual(result["citations"][0]["index"], 2)
        self.assertEqual(result["citations"][0]["label"], "NVIDIA RAG")
        self.assertIn("[2]", result["answer"])
        self.assertFalse(result["metrics"]["citation_fallback"])

    def test_citation_answer_adds_source_footer_when_model_omits_citations(self):
        class FakeProvider:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def complete(self, *args, **kwargs):
                return SimpleNamespace(text="Q2E expands the query before retrieval.")

        with patch("blacknode.nodes.nvidia_rag.OpenAIProvider", FakeProvider):
            result = _NODE_REGISTRY["NIMCitationAnswer"]({
                "query": "What does Q2E do?",
                "results": [{"id": "a", "text": "Q2E expands queries."}],
            })

        self.assertIn("Sources: [1]", result["answer"])
        self.assertTrue(result["metrics"]["citation_fallback"])

    def test_retrieval_compare_reports_rewrite_changes(self):
        result = _NODE_REGISTRY["RetrievalCompare"]({
            "original_results": [{"id": "a"}, {"id": "b"}],
            "rewritten_results": [{"id": "b"}, {"id": "c"}],
            "reranked_results": [{"id": "c"}, {"id": "b"}],
        })

        self.assertEqual(result["comparison"]["added_by_rewrite"], ["c"])
        self.assertEqual(result["comparison"]["dropped_by_rewrite"], ["a"])
        self.assertTrue(result["comparison"]["top_result_changed"])
        self.assertEqual(result["comparison"]["top_result_after_rerank"], "c")


if __name__ == "__main__":
    unittest.main()
