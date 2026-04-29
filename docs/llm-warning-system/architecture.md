# LLM warning system architecture

## Purpose

This document defines the initial architecture for table-level diagnostics in P4SymTest. The feature extends P4 verification with evidence-based explanations and warnings, while preserving the existing symbolic execution engine as the source of truth.

The core thesis is: **P4SymTest computes symbolic facts; the LLM interprets curated evidence.** The LLM is not an autonomous agent and does not replace SMT/Z3.

## System boundary

The warning system is composed of five logical containers:

- `frontend`: renders table diagnostics, evidence, confidence, severity, and inconclusive states.
- `backend`: executes parser/table/deparser analysis, extracts deterministic facts, and calls `llm-analyzer`.
- `llm-analyzer`: validates facts, retrieves RAG context, builds prompts, calls the local model server, and validates JSON diagnostics.
- `llama-server`: serves an open-source local model through an OpenAI-compatible chat completions API.
- `qdrant`: stores pre-processed RAG chunks and metadata.

P4SymTest remains the orchestrator. The model receives closed diagnostic tasks and returns structured JSON.

## Hardware-agnostic profiles

The implementation must be container-first and hardware-agnostic. The code path must be the same across profiles; only environment variables, model files, context length, threads, and GPU flags can change.

Planned profiles:

- `cpu-local`: first integration target, no GPU required.
- `mac-m4`: CPU-only container profile for Mac M4 development.
- `local-gpu`: i7 14th gen + GTX 3060 8 GB, intended for local model benchmarking.
- `vps-light`: 2 vCPU + 8 GB RAM demo profile with smaller GGUF model and simple P4 programs.

## Data flow

1. User executes a table in the frontend.
2. Backend runs the existing symbolic analysis and writes output snapshots.
3. Backend extracts `TableAnalysisFacts`.
4. Backend calls `llm-analyzer` with facts.
5. `llm-analyzer` retrieves relevant `RagChunk` items from Qdrant.
6. `llm-analyzer` builds a compact prompt from facts and chunks.
7. `llm-analyzer` calls `llama-server`.
8. `llm-analyzer` validates the JSON response as `TableWarningDiagnostics`.
9. Backend returns diagnostics as an optional field in the table response.
10. Frontend renders diagnostics without blocking the normal verification result.

## Evidence policy

Warnings must cite evidence. Evidence can come from:

- deterministic facts extracted from symbolic execution;
- P4 source slices;
- runtime entries;
- topology slices;
- snapshot summaries;
- RAG chunks with source metadata.

If evidence is insufficient, diagnostics must be marked inconclusive.

## Failure policy

LLM/RAG failure must never break symbolic verification. Backend responses should preserve the original output and include a diagnostics-unavailable state when needed.

Failure examples:

- `llm-analyzer` timeout;
- invalid model JSON;
- empty RAG result;
- Qdrant unavailable;
- local model unavailable.

## Public contract summary

Backend table endpoints keep their current behavior and add an optional `diagnostics` field:

- `POST /api/analyze/table`
- `POST /api/analyze/egress_table`

Internal analyzer endpoints:

- `GET /health`
- `POST /rag/search`
- `POST /analyze/table-warning`

The model server is accessed through a local OpenAI-compatible protocol:

- `POST /v1/chat/completions`

OpenAI-compatible means protocol compatibility only. The intended models are open-source local models.

