# NVIDIA Visual RAG Comparator

Blacknode can compose NVIDIA's modular retrieval components as a visible,
typed workflow. The included comparator runs the same semantic retrieval path
twice: once with the user's original question and once after Nemotron applies
Query-to-Expansion (Q2E).

```text
                         original query -> query embedding -> vector search
documents -> chunking -> passage embeddings
                         Q2E query      -> query embedding -> vector search
                                                               |
                                                               v
                                                        NVIDIA reranking
                                                               |
                                                               v
                                                      cited NIM answer
```

The graph exposes the rewritten query, retrieval orders, reranked passages,
citations, model calls, and node timings. This makes it possible to inspect
whether query rewriting improved retrieval instead of treating RAG as one
opaque call.

## Included Nodes

| Node | Purpose |
|---|---|
| `NIMQueryRewrite` | Uses a Nemotron chat NIM to extract a core query and optionally apply Q2E. |
| `NVIDIAEmbedding` | Calls a hosted or local NVIDIA Embedding NIM in `query` or `passage` mode. |
| `NVIDIAVectorSearch` | Runs deterministic cosine similarity over returned embeddings. |
| `NVIDIARerank` | Sends retrieved candidates to a hosted or local NVIDIA Reranking NIM. |
| `NIMCitationAnswer` | Generates an evidence-constrained answer with numbered citations. |
| `RetrievalCompare` | Reports changes between original, rewritten, and reranked result orders. |

The default retrieval models are:

- `nvidia/llama-nemotron-embed-1b-v2`
- `nvidia/llama-nemotron-rerank-1b-v2`

Query rewriting and cited generation default to
`nvidia/nemotron-mini-4b-instruct` for responsive interactive demos. The model
field remains configurable for larger hosted or local Nemotron models.

## Run The Template

You can set a hosted NVIDIA API key through the environment:

```powershell
$env:NVIDIA_API_KEY="nvapi-..."
```

Open the editor:

```powershell
.\start.bat
```

Alternatively, select any NVIDIA node and enter the key once in the
**Shared Credential · NVIDIA NIM** card. Blacknode saves it in the editor key
store and automatically reuses it for every NVIDIA service node. The canvas
shows **NIM key shared** when the key is available and **NIM key missing** when
it still needs to be configured. The `api_key` input port remains available
for workflows that need an explicit per-node override.

Load **NVIDIA Visual RAG Comparator** from Templates and cook:

1. **Q2E Rewritten Query**
2. **Retrieval Comparison**
3. **Cited Answer**
4. **Citations**

The default corpus is intentionally small. Replace the `corpus` Text node with
a file, database, or extraction workflow for a real use case.

## Manual Credential Check

1. Open **NVIDIA Visual RAG Comparator** and select an NVIDIA node.
2. Confirm that its inspector says **Key found** and the canvas badge says
   **NIM key shared**.
3. If the key is missing, enter it once in the shared credential card.
4. Select another NVIDIA node. It should immediately show the same shared-key
   status without asking for another key.
5. Cook **Retrieval Comparison** or **Cited Answer** to verify the shared
   credential works in a live NVIDIA request.

## Hosted And Local Endpoints

Hosted defaults:

```text
Embedding: https://integrate.api.nvidia.com/v1/embeddings
Reranking: https://ai.api.nvidia.com/v1/retrieval/nvidia/llama-nemotron-rerank-1b-v2/reranking
Chat NIM:  https://integrate.api.nvidia.com/v1
```

For local NIM containers:

- Set `NVIDIAEmbedding.endpoint_url` to a service base such as
  `http://127.0.0.1:8000/v1`; Blacknode appends `/embeddings`.
- Set `NVIDIARerank.endpoint_url` to a service base such as
  `http://127.0.0.1:8001/v1`; Blacknode appends `/ranking`.
- Point `NIMQueryRewrite` and `NIMCitationAnswer` at the OpenAI-compatible chat
  NIM base URL.

Embedding and reranking commonly run as separate NIM services, so they can use
different ports or hosts.

## Current Boundary

This first implementation keeps document embeddings in workflow values and
performs cosine search in the Blacknode process. That makes the comparison
portable and inspectable, but it is not a production vector database.

For a larger deployment, keep the same rewrite, rerank, citation, and comparison
nodes while replacing `NVIDIAVectorSearch` with Milvus, LanceDB, or another
vector store backed by the full NeMo Retriever ingestion pipeline.

The current template does not include Q2D, chain-of-thought rewrite comparison,
automatic groundedness scoring, persistent indexes, or benchmark datasets.

## NVIDIA References

- [NeMo Retriever overview](https://docs.nvidia.com/nemo/retriever/latest/)
- [Embedding NIM API](https://docs.nvidia.com/nim/nemo-retriever/text-embedding/latest/)
- [Reranking NIM API](https://docs.nvidia.com/nim/nemo-retriever/text-reranking/latest/)
- [Reasoning query rewriting with Nemotron](https://developer.nvidia.com/blog/how-to-enhance-rag-pipelines-with-reasoning-using-nvidia-llama-nemotron-models/)
