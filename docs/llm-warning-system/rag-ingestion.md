# RAG ingestion

The `llm-analyzer` RAG layer uses Qdrant as a vector store, but embeddings are
prepared offline. The analyzer does not download models, train embeddings, or
depend on host-specific hardware for ingestion.

## Manifest format

An ingestion manifest is a JSON file with one collection target and a list of
pre-embedded chunks:

```json
{
  "manifest_version": "rag-manifest.v1",
  "manifest_id": "p4symtest-domain-notes",
  "collection": "p4symtest-warnings",
  "vector_size": 384,
  "distance": "Cosine",
  "chunks": [
    {
      "chunk_key": "v1model-egress-spec-drop",
      "source_id": "v1model-egress-spec",
      "title": "v1model egress_spec and drop behavior",
      "source_type": "v1model",
      "citation": "P4 v1model reference, standard_metadata.egress_spec",
      "version": "2026-04-onda0",
      "text": "Short cited passage or local project note text.",
      "embedding": [0.1, 0.2, 0.3],
      "metadata": {
        "tags": ["egress_spec", "drop"]
      }
    }
  ]
}
```

Each chunk payload exposed by `/rag/search` is aligned with
`schemas/rag_chunk.schema.json`: `source_id`, `title`, `source_type`,
`citation`, `version`, `text`, and optional `score`.

Stable Qdrant point IDs are generated from manifest/source metadata:
`manifest_id`, `manifest_version`, `source_id`, `version`, `chunk_key` or
manifest index, `title`, and `citation`. Re-ingesting the same manifest upserts
the same IDs.

## Container-first ingestion

Run ingestion from the analyzer container so the same dependency set is used in
development and CI:

```bash
docker compose --profile cpu-local run --rm --no-deps llm-analyzer \
  python scripts/rag_ingest.py \
  --manifest tests/fixtures/rag/sample_manifest.json \
  --qdrant-url http://qdrant:6333 \
  --collection p4symtest-warnings
```

The script validates vector sizes, creates the collection if needed, and upserts
all points. The output is a reproducible manifest summary containing the stable
chunk IDs.

## Search contract

`POST /rag/search` accepts:

```json
{
  "query": "egress_spec drop behavior",
  "limit": 5,
  "query_vector": [0.1, 0.2, 0.3],
  "filters": {
    "source_types": ["v1model"],
    "source_ids": [],
    "versions": []
  }
}
```

For production retrieval, `query_vector` should be produced by the same offline
embedding pipeline used for the manifest. If it is omitted, the analyzer uses a
small deterministic hashing vectorizer as a development and test fallback. This
fallback is reproducible and hardware-agnostic, but it is not a semantic
embedding model.

The response returns chunks and the recovered stable point IDs:

```json
{
  "chunks": [
    {
      "source_id": "v1model-egress-spec",
      "title": "v1model egress_spec and drop behavior",
      "source_type": "v1model",
      "citation": "P4 v1model reference, standard_metadata.egress_spec",
      "version": "2026-04-onda0",
      "text": "Short cited passage or local project note text.",
      "score": 0.91
    }
  ],
  "chunk_ids": ["stable-qdrant-point-id"]
}
```

Empty or whitespace-only queries return an empty result. Qdrant availability
errors are reported as `503` by the endpoint so callers can treat diagnostics as
optional and preserve symbolic verification results.
