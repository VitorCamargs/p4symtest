# Prompt and local model protocol

## Scope

The `llm-analyzer` calls a local OpenAI-compatible `/v1/chat/completions`
endpoint. OpenAI-compatible means protocol compatibility only; the intended
runtime is interchangeable and may be `llama-server`, vLLM, Ollama, or another
local open-source model server that implements the same request shape.

## Runtime configuration

The analyzer reads these variables:

- `LLAMA_BASE_URL` or `LLAMA_SERVER_URL`: model server base URL.
- `LLAMA_MODEL`: model identifier sent in the chat completion request.
- `LLM_TEMPERATURE`: default low temperature for reproducible diagnostics.
- `LLM_TIMEOUT_SECONDS` or `LLM_REQUEST_TIMEOUT_SECONDS`: request timeout.
- `LLM_MAX_OUTPUT_TOKENS`: maximum JSON response size.

Only configuration changes between runtime profiles. The prompt builder,
validator, and HTTP client code path stays the same.

## Diagnostics modes

`/analyze/table-warning` supports these execution modes:

- `mock`: deterministic mock diagnostics for development and UI integration.
- `mock_inconclusive`: deterministic abstention path for UI/error handling.
- `llm`: baseline real-model path with no RAG context.
- `rag_llm`: real-model path with retrieved context from Qdrant.

The current runtime focus is `llm`. `rag_llm` stays in the contract so Qdrant
can be enabled later without changing backend/frontend payloads.

## Prompt contract

Prompt version: `table-warning-json-v1`.

The prompt has two messages:

- System message: defines the model as an assistive interpreter of P4SymTest
  facts, not a verifier.
- User message: JSON payload containing compact deterministic facts, optional
  RAG chunks, available evidence summaries, and the required output contract.

The prompt intentionally excludes raw giant snapshots. It includes only snapshot
filenames, state counts, state summaries, field update summaries, P4 slices,
runtime entries, topology slices, log excerpts, symbolic facts, and RAG chunk
text.

## Output contract

The model must return exactly one JSON object matching
`TableWarningDiagnostics`. Every warning must cite evidence by `evidence_ids`,
and every cited ID must exist in the returned `evidence` array.

The analyzer owns these response fields and sets them after parsing:

- `model_info.provider`
- `model_info.model`
- `model_info.prompt_version`
- `rag_context_ids`

## Fallback policy

The validator returns an inconclusive diagnostic instead of surfacing unsafe
model output when:

- the request times out;
- the model server request fails;
- the model returns invalid JSON;
- the JSON fails the diagnostics schema;
- the response has no evidence;
- a warning cites missing evidence;
- an inconclusive response still contains warnings;
- the response table name does not match the analyzed facts.

Fallback diagnostics preserve deterministic state-count evidence and include no
warnings.
