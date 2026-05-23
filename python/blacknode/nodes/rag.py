from __future__ import annotations

import math
import re
from collections import Counter

from blacknode.node import node


@node(
    inputs=["text:Text", "chunk_size:Int=900", "overlap:Int=120"],
    outputs=["chunks:List", "count:Int"],
    name="TextChunker",
)
def text_chunker(ctx: dict) -> dict:
    text = str(ctx.get("text") or "")
    chunk_size = max(1, int(ctx.get("chunk_size", 900)))
    overlap = max(0, int(ctx.get("overlap", 120)))
    step = max(1, chunk_size - overlap)
    chunks = [
        {"id": index, "text": text[start:start + chunk_size]}
        for index, start in enumerate(range(0, len(text), step), start=1)
        if text[start:start + chunk_size].strip()
    ]
    return {"chunks": chunks, "count": len(chunks)}


@node(inputs=["documents:List"], outputs=["index:Dict", "count:Int"], name="KeywordIndex")
def keyword_index(ctx: dict) -> dict:
    documents = ctx.get("documents") if isinstance(ctx.get("documents"), list) else []
    indexed = []
    doc_freq: Counter[str] = Counter()
    for index, document in enumerate(documents):
        if isinstance(document, dict):
            text = str(document.get("text") or document.get("content") or "")
            doc_id = document.get("id", index)
            metadata = {k: v for k, v in document.items() if k not in {"text", "content"}}
        else:
            text = str(document)
            doc_id = index
            metadata = {}
        terms = _terms(text)
        counts = Counter(terms)
        doc_freq.update(set(terms))
        indexed.append({"id": doc_id, "text": text, "terms": dict(counts), "metadata": metadata})
    return {"index": {"documents": indexed, "doc_freq": dict(doc_freq), "count": len(indexed)}, "count": len(indexed)}


@node(inputs=["index:Dict", "query:Text", "top_k:Int=5"], outputs=["results:List"], name="KeywordSearch")
def keyword_search(ctx: dict) -> dict:
    index = ctx.get("index") if isinstance(ctx.get("index"), dict) else {}
    documents = index.get("documents") if isinstance(index.get("documents"), list) else []
    doc_freq = index.get("doc_freq") if isinstance(index.get("doc_freq"), dict) else {}
    query_terms = Counter(_terms(str(ctx.get("query") or "")))
    total_docs = max(1, int(index.get("count") or len(documents) or 1))
    scored = []
    for document in documents:
        term_counts = document.get("terms") if isinstance(document, dict) else {}
        if not isinstance(term_counts, dict):
            continue
        score = 0.0
        for term, query_count in query_terms.items():
            freq = float(term_counts.get(term, 0))
            if freq <= 0:
                continue
            idf = math.log((total_docs + 1) / (float(doc_freq.get(term, 0)) + 1)) + 1
            score += query_count * freq * idf
        if score > 0:
            scored.append({
                "id": document.get("id"),
                "score": round(score, 6),
                "text": document.get("text", ""),
                "metadata": document.get("metadata", {}),
            })
    scored.sort(key=lambda item: item["score"], reverse=True)
    return {"results": scored[:max(1, int(ctx.get("top_k", 5)))]}


@node(inputs=["results:List", "separator:Text=\n\n"], outputs=["context:Text"], name="RAGContext")
def rag_context(ctx: dict) -> dict:
    results = ctx.get("results") if isinstance(ctx.get("results"), list) else []
    separator = str(ctx.get("separator") or "\n\n")
    texts = []
    for item in results:
        if isinstance(item, dict):
            texts.append(str(item.get("text") or ""))
        else:
            texts.append(str(item))
    return {"context": separator.join(text for text in texts if text)}


def _terms(text: str) -> list[str]:
    return [term.lower() for term in re.findall(r"[A-Za-z0-9_]+", text) if len(term) > 1]
