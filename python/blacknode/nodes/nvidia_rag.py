"""NVIDIA-accelerated building blocks for inspectable RAG workflows."""
from __future__ import annotations

import json
import math
import re
import time
from typing import Any

from blacknode.node import Any as AnyPort
from blacknode.node import Dict, Embedding, Enum, Float, Int, List, Model, Text, node
from blacknode.providers.openai_provider import OpenAIProvider

from .nvidia import (
    HOSTED_NIM_BASE_URL,
    _clean_model,
    _nim_api_key,
    _post_json,
)

DEFAULT_RAG_CHAT_MODEL = "nim:nvidia/nemotron-mini-4b-instruct"
DEFAULT_EMBED_MODEL = "nvidia/llama-nemotron-embed-1b-v2"
DEFAULT_RERANK_MODEL = "nvidia/llama-nemotron-rerank-1b-v2"
DEFAULT_RERANK_URL = (
    "https://ai.api.nvidia.com/v1/retrieval/"
    "nvidia/llama-nemotron-rerank-1b-v2/reranking"
)


def _endpoint(value: Any, suffix: str, default: str) -> str:
    raw = str(value or default).strip().rstrip("/")
    if raw.endswith(suffix):
        return raw
    return raw + suffix


def _ranking_endpoint(value: Any) -> str:
    raw = str(value or DEFAULT_RERANK_URL).strip().rstrip("/")
    if raw.endswith(("/ranking", "/reranking")):
        return raw
    return raw + "/ranking"


def _documents(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str):
        raw_items: list[Any] = [value]
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []

    documents = []
    for index, item in enumerate(raw_items):
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("content") or "")
            doc_id = item.get("id", index)
            metadata = dict(item.get("metadata")) if isinstance(item.get("metadata"), dict) else {}
            metadata.update({
                key: val
                for key, val in item.items()
                if key not in {"id", "text", "content", "embedding", "metadata", "score", "rank"}
            })
        else:
            text = str(item)
            doc_id = index
            metadata = {}
        if text.strip():
            documents.append({"id": doc_id, "text": text, "metadata": metadata})
    return documents


def _json_object(text: str) -> dict[str, Any]:
    candidates = [text]
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.I | re.S)
    if fenced:
        candidates.insert(0, fenced.group(1))
    braced = re.search(r"\{.*\}", text, re.S)
    if braced:
        candidates.append(braced.group(0))
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def _model_call(ctx: dict, model: str) -> None:
    run_logger = ctx.get("__run_logger__")
    if run_logger:
        run_logger.model_call(
            node_id=ctx.get("__node_id__"),
            model=model,
            provider="NVIDIA NIM",
            tool_count=0,
        )


@node(
    inputs={
        "query": Text,
        "strategy": Enum(["Q2E", "extract"], default="Q2E"),
        "model": Model(default=DEFAULT_RAG_CHAT_MODEL),
        "endpoint_url": Text(default=HOSTED_NIM_BASE_URL),
        "api_key": Text,
        "max_tokens": Int(default=512),
    },
    outputs={
        "core_query": Text,
        "rewritten_query": Text,
        "terms": List,
        "analysis": Dict,
        "latency_ms": Float,
    },
    name="NIMQueryRewrite",
    category="NVIDIA",
    description="Extract and expand a search query with a Nemotron reasoning model.",
)
def nim_query_rewrite(ctx: dict) -> dict:
    query = str(ctx.get("query") or "").strip()
    if not query:
        return {
            "core_query": "",
            "rewritten_query": "",
            "terms": [],
            "analysis": {},
            "latency_ms": 0.0,
        }

    strategy = str(ctx.get("strategy") or "Q2E").strip().upper()
    model = _clean_model(ctx.get("model") or DEFAULT_RAG_CHAT_MODEL)
    max_tokens = max(64, min(int(ctx.get("max_tokens") or 512), 2048))
    if strategy == "EXTRACT":
        instruction = (
            "Extract the user's core search request. Remove conversational filler, "
            "but preserve every explicit constraint."
        )
    else:
        instruction = (
            "Extract the user's core search request, then apply Query-to-Expansion "
            "(Q2E): add concise synonyms, alternate terminology, named concepts, "
            "and closely related search phrases. Do not invent facts."
        )
    system = (
        "You prepare queries for enterprise retrieval. "
        f"{instruction} Return only JSON with keys core_query, rewritten_query, "
        "and terms, where terms is an array of short strings."
    )

    client = OpenAIProvider(
        api_key=_nim_api_key(ctx.get("api_key")),
        base_url=str(ctx.get("endpoint_url") or HOSTED_NIM_BASE_URL).rstrip("/"),
    )
    _model_call(ctx, model)
    started = time.perf_counter()
    response = client.complete(
        [{"role": "user", "content": query}],
        model=model,
        system=system,
        max_tokens=max_tokens,
        temperature=0.1,
    )
    latency_ms = (time.perf_counter() - started) * 1000
    parsed = _json_object(response.text)
    core_query = str(parsed.get("core_query") or query).strip()
    rewritten = str(parsed.get("rewritten_query") or core_query).strip()
    raw_terms = parsed.get("terms")
    terms = [str(item).strip() for item in raw_terms if str(item).strip()] if isinstance(raw_terms, list) else []
    return {
        "core_query": core_query,
        "rewritten_query": rewritten,
        "terms": terms,
        "analysis": {
            "strategy": strategy,
            "model": model,
            "original_query": query,
            "raw_response": response.text,
        },
        "latency_ms": round(latency_ms, 3),
    }


@node(
    inputs={
        "content": AnyPort,
        "input_type": Enum(["passage", "query"], default="passage"),
        "model": Text(default=DEFAULT_EMBED_MODEL),
        "endpoint_url": Text(default=HOSTED_NIM_BASE_URL),
        "api_key": Text,
        "dimensions": Int(default=0),
        "timeout": Float(default=30.0),
    },
    outputs={
        "embedding": Embedding,
        "embeddings": List,
        "items": List,
        "metrics": Dict,
    },
    name="NVIDIAEmbedding",
    category="NVIDIA",
    description="Create query or passage embeddings with a hosted or local NVIDIA Embedding NIM.",
)
def nvidia_embedding(ctx: dict) -> dict:
    documents = _documents(ctx.get("content"))
    if not documents:
        return {"embedding": [], "embeddings": [], "items": [], "metrics": {"count": 0}}

    model = str(ctx.get("model") or DEFAULT_EMBED_MODEL).strip()
    input_type = str(ctx.get("input_type") or "passage").strip().lower()
    if input_type not in {"query", "passage"}:
        input_type = "passage"
    body: dict[str, Any] = {
        "input": [item["text"] for item in documents],
        "model": model,
        "input_type": input_type,
        "modality": "text",
        "encoding_format": "float",
        "truncate": "END",
    }
    dimensions = int(ctx.get("dimensions") or 0)
    if dimensions > 0:
        body["dimensions"] = dimensions

    url = _endpoint(ctx.get("endpoint_url"), "/embeddings", HOSTED_NIM_BASE_URL)
    started = time.perf_counter()
    ok, status, response = _post_json(
        url,
        _nim_api_key(ctx.get("api_key")),
        body,
        max(1.0, float(ctx.get("timeout") or 30.0)),
    )
    latency_ms = (time.perf_counter() - started) * 1000
    if not ok:
        raise RuntimeError(f"NVIDIA embedding request failed ({status}): {response}")

    rows = response.get("data") if isinstance(response.get("data"), list) else []
    ordered = sorted(
        (row for row in rows if isinstance(row, dict)),
        key=lambda row: int(row.get("index", 0)),
    )
    embeddings = [
        [float(value) for value in row.get("embedding", [])]
        for row in ordered
        if isinstance(row.get("embedding"), list)
    ]
    if len(embeddings) != len(documents):
        raise RuntimeError(
            f"NVIDIA embedding response returned {len(embeddings)} vectors "
            f"for {len(documents)} inputs."
        )
    usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
    return {
        "embedding": embeddings[0] if embeddings else [],
        "embeddings": embeddings,
        "items": documents,
        "metrics": {
            "provider": "NVIDIA NeMo Retriever",
            "model": model,
            "input_type": input_type,
            "count": len(embeddings),
            "dimensions": len(embeddings[0]) if embeddings else 0,
            "latency_ms": round(latency_ms, 3),
            "usage": usage,
        },
    }


def _cosine(left: list[Any], right: list[Any]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(float(a) * float(b) for a, b in zip(left, right))
    left_norm = math.sqrt(sum(float(value) ** 2 for value in left))
    right_norm = math.sqrt(sum(float(value) ** 2 for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


@node(
    inputs={
        "documents": List,
        "embeddings": List,
        "query_embedding": Embedding,
        "top_k": Int(default=10),
    },
    outputs={"results": List, "metrics": Dict},
    name="NVIDIAVectorSearch",
    category="NVIDIA",
    description="Run deterministic cosine search over NVIDIA document embeddings.",
)
def nvidia_vector_search(ctx: dict) -> dict:
    documents = _documents(ctx.get("documents"))
    embeddings = ctx.get("embeddings") if isinstance(ctx.get("embeddings"), list) else []
    query_embedding = ctx.get("query_embedding") if isinstance(ctx.get("query_embedding"), list) else []
    top_k = max(1, int(ctx.get("top_k") or 10))
    if len(documents) != len(embeddings):
        raise ValueError(
            f"Vector search received {len(documents)} documents and "
            f"{len(embeddings)} embeddings."
        )

    scored = []
    for document, embedding in zip(documents, embeddings):
        vector = embedding if isinstance(embedding, list) else []
        scored.append({
            **document,
            "score": round(_cosine(query_embedding, vector), 6),
        })
    scored.sort(key=lambda item: item["score"], reverse=True)
    results = [
        {**item, "rank": rank}
        for rank, item in enumerate(scored[:top_k], start=1)
    ]
    return {
        "results": results,
        "metrics": {
            "searched": len(documents),
            "returned": len(results),
            "top_score": results[0]["score"] if results else 0.0,
        },
    }


@node(
    inputs={
        "query": Text,
        "results": List,
        "model": Text(default=DEFAULT_RERANK_MODEL),
        "endpoint_url": Text(default=DEFAULT_RERANK_URL),
        "api_key": Text,
        "top_k": Int(default=5),
        "timeout": Float(default=30.0),
    },
    outputs={"results": List, "metrics": Dict},
    name="NVIDIARerank",
    category="NVIDIA",
    description="Rerank retrieved passages with a hosted or local NVIDIA Reranking NIM.",
)
def nvidia_rerank(ctx: dict) -> dict:
    query = str(ctx.get("query") or "").strip()
    candidates = _documents(ctx.get("results"))
    if not query or not candidates:
        return {"results": [], "metrics": {"count": 0}}

    source_results = [item for item in ctx.get("results", []) if isinstance(item, dict)]
    model = str(ctx.get("model") or DEFAULT_RERANK_MODEL).strip()
    url = _ranking_endpoint(ctx.get("endpoint_url"))
    body = {
        "model": model,
        "query": {"text": query},
        "passages": [{"text": item["text"]} for item in candidates],
        "truncate": "END",
    }
    started = time.perf_counter()
    ok, status, response = _post_json(
        url,
        _nim_api_key(ctx.get("api_key")),
        body,
        max(1.0, float(ctx.get("timeout") or 30.0)),
    )
    latency_ms = (time.perf_counter() - started) * 1000
    if not ok:
        raise RuntimeError(f"NVIDIA reranking request failed ({status}): {response}")

    rankings = response.get("rankings") if isinstance(response.get("rankings"), list) else []
    top_k = max(1, int(ctx.get("top_k") or 5))
    reranked = []
    for rank, row in enumerate(rankings[:top_k], start=1):
        if not isinstance(row, dict):
            continue
        index = int(row.get("index", -1))
        if not 0 <= index < len(candidates):
            continue
        original = source_results[index] if index < len(source_results) else candidates[index]
        reranked.append({
            **original,
            "rank": rank,
            "retrieval_score": original.get("score", 0.0),
            "rerank_score": round(float(row.get("logit", 0.0)), 6),
        })
    usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
    return {
        "results": reranked,
        "metrics": {
            "provider": "NVIDIA NeMo Retriever",
            "model": model,
            "candidates": len(candidates),
            "returned": len(reranked),
            "latency_ms": round(latency_ms, 3),
            "usage": usage,
        },
    }


def _source_label(item: dict[str, Any], index: int) -> str:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    return str(
        metadata.get("title")
        or metadata.get("source")
        or metadata.get("url")
        or item.get("id")
        or f"Source {index}"
    )


@node(
    inputs={
        "query": Text,
        "results": List,
        "model": Model(default=DEFAULT_RAG_CHAT_MODEL),
        "endpoint_url": Text(default=HOSTED_NIM_BASE_URL),
        "api_key": Text,
        "max_tokens": Int(default=384),
    },
    outputs={"answer": Text, "citations": List, "context": Text, "metrics": Dict},
    name="NIMCitationAnswer",
    category="NVIDIA",
    description="Generate a grounded NIM answer with numbered citations to retrieved passages.",
)
def nim_citation_answer(ctx: dict) -> dict:
    query = str(ctx.get("query") or "").strip()
    results = [item for item in ctx.get("results", []) if isinstance(item, dict)]
    if not query or not results:
        return {
            "answer": "No retrieved evidence was available to answer the question.",
            "citations": [],
            "context": "",
            "metrics": {"sources": 0},
        }

    citations = []
    context_parts = []
    for index, item in enumerate(results, start=1):
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        citation = {
            "index": index,
            "id": item.get("id"),
            "label": _source_label(item, index),
            "url": str(metadata.get("url") or ""),
            "text": str(item.get("text") or ""),
        }
        citations.append(citation)
        context_parts.append(f"[{index}] {citation['label']}\n{citation['text']}")
    context = "\n\n".join(context_parts)
    model = _clean_model(ctx.get("model") or DEFAULT_RAG_CHAT_MODEL)
    client = OpenAIProvider(
        api_key=_nim_api_key(ctx.get("api_key")),
        base_url=str(ctx.get("endpoint_url") or HOSTED_NIM_BASE_URL).rstrip("/"),
    )
    _model_call(ctx, model)
    started = time.perf_counter()
    response = client.complete(
        [{
            "role": "user",
            "content": f"Question:\n{query}\n\nRetrieved evidence:\n{context}",
        }],
        model=model,
        system=(
            "Answer only from the retrieved evidence in at most 120 words. "
            "Use a short paragraph or no more than three bullets. Cite every "
            "factual sentence with bracketed source numbers such as [1]. Do not "
            "add examples, explanations, or recommendations that are not "
            "explicitly supported by the evidence. Use only evidence directly "
            "relevant to the question; do not summarize every source. If the "
            "evidence is insufficient, say so explicitly. Do not invent sources."
        ),
        max_tokens=max(64, min(int(ctx.get("max_tokens") or 384), 4096)),
        temperature=0.1,
    )
    latency_ms = (time.perf_counter() - started) * 1000
    answer = response.text.strip()
    referenced = {int(value) for value in re.findall(r"\[(\d+)\]", answer)}
    citation_fallback = not referenced
    if citation_fallback:
        referenced = {item["index"] for item in citations}
        answer = f"{answer}\n\nSources: " + ", ".join(f"[{index}]" for index in sorted(referenced))
    used = [item for item in citations if item["index"] in referenced] or citations
    return {
        "answer": answer,
        "citations": used,
        "context": context,
        "metrics": {
            "model": model,
            "sources": len(citations),
            "cited_sources": len(used),
            "citation_fallback": citation_fallback,
            "latency_ms": round(latency_ms, 3),
        },
    }


def _result_ids(results: Any) -> list[str]:
    if not isinstance(results, list):
        return []
    return [
        str(item.get("id"))
        for item in results
        if isinstance(item, dict) and item.get("id") is not None
    ]


@node(
    inputs={
        "original_results": List,
        "rewritten_results": List,
        "reranked_results": List,
    },
    outputs={"comparison": Dict, "report": Text},
    name="RetrievalCompare",
    category="NVIDIA",
    description="Compare original-query, rewritten-query, and reranked retrieval results.",
)
def retrieval_compare(ctx: dict) -> dict:
    original_ids = _result_ids(ctx.get("original_results"))
    rewritten_ids = _result_ids(ctx.get("rewritten_results"))
    reranked_ids = _result_ids(ctx.get("reranked_results"))
    original_set = set(original_ids)
    rewritten_set = set(rewritten_ids)
    overlap = [doc_id for doc_id in rewritten_ids if doc_id in original_set]
    added = [doc_id for doc_id in rewritten_ids if doc_id not in original_set]
    dropped = [doc_id for doc_id in original_ids if doc_id not in rewritten_set]
    comparison = {
        "original_order": original_ids,
        "rewritten_order": rewritten_ids,
        "reranked_order": reranked_ids,
        "overlap_count": len(overlap),
        "added_by_rewrite": added,
        "dropped_by_rewrite": dropped,
        "top_result_changed": bool(original_ids and rewritten_ids and original_ids[0] != rewritten_ids[0]),
        "top_result_after_rerank": reranked_ids[0] if reranked_ids else None,
    }
    report = (
        "Retrieval comparison\n"
        f"- Original top results: {', '.join(original_ids) or '(none)'}\n"
        f"- Q2E top results: {', '.join(rewritten_ids) or '(none)'}\n"
        f"- Reranked results: {', '.join(reranked_ids) or '(none)'}\n"
        f"- Added by Q2E: {', '.join(added) or '(none)'}\n"
        f"- Dropped by Q2E: {', '.join(dropped) or '(none)'}"
    )
    return {"comparison": comparison, "report": report}
