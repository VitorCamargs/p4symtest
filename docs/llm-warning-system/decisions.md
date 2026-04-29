# LLM warning system decisions

## Decision 001: P4SymTest remains the orchestrator

P4SymTest executes the P4 analysis, extracts facts, and asks the model closed questions. The LLM does not decide which tools to run and does not mutate verification state.

Rationale: verification workflows need reproducibility and auditability. Autonomous agent behavior would add nondeterminism and make evaluation harder.

## Decision 002: Facts before language

The backend must extract deterministic facts before calling the LLM.

Rationale: the model should interpret evidence, not infer from raw logs alone. This supports lower hallucination risk and clearer article claims.

## Decision 003: Diagnostics are optional

Table responses add an optional `diagnostics` field. Existing flows must keep working when diagnostics are absent.

Rationale: LLM/RAG availability must not affect symbolic verification.

## Decision 004: Container-first development

All services must be designed for container execution. Local host-specific setup should be limited to model files, Docker runtime, and environment variables.

Rationale: the system must run across CPU-only, Mac M4, local GPU, and VPS profiles without code changes.

## Decision 005: Hardware-agnostic code

Hardware differences are expressed through profiles and environment variables, not branches in application logic.

Rationale: the architecture must be portable and easier to reproduce for paper experiments.

## Decision 006: Qdrant as vector store

Qdrant is the target vector store, deployed as a separate container.

Rationale: this matches the intended architecture and keeps RAG storage independent from the analyzer service.

## Decision 007: Offline embedding preprocessing

RAG documents should be embedded offline and ingested into Qdrant through a reproducible manifest.

Rationale: this keeps the runtime profile light and makes the knowledge base auditable.

## Decision 008: OpenAI-compatible local model API

The `llm-analyzer` talks to `llama-server` through an OpenAI-compatible `/v1/chat/completions` endpoint.

Rationale: the protocol is widely supported by local runtimes such as llama.cpp, Ollama, and vLLM. This does not imply use of OpenAI models.

## Decision 009: CPU-only first

The first real runtime target is CPU-only. GPU comes later.

Rationale: CPU-only removes CUDA/driver failures from the first integration and also prepares the Mac M4 and VPS paths.

## Decision 010: One commit per delivery

Each delivery must have unique tests and a single reviewable commit.

Rationale: this keeps review, rollback, and article traceability clean.

