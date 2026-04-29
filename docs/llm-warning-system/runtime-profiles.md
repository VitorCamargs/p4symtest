# LLM/RAG runtime profiles

This document describes the container-first runtime profiles for the table-level
warning system. The profiles change only Docker runtime settings, environment
variables, model files, and resource assumptions. They must not require backend,
frontend, analyzer, or RAG application-code changes.

## Internal service contract

The application talks to stable Docker network names:

- Backend to analyzer: `LLM_ANALYZER_URL=http://llm-analyzer:8000`
- Analyzer to Qdrant: `QDRANT_URL=http://qdrant:6333`
- Analyzer to model server: `LLAMA_SERVER_URL=http://llama-server:8080`

Profile-specific services publish the same network aliases. For example,
`llm-analyzer-mac-m4` is still reachable as `llm-analyzer`, and
`llama-server-mac-m4` is still reachable as `llama-server`.

Use one LLM profile at a time:

```bash
docker compose --profile cpu-local up
docker compose --profile mac-m4 up
docker compose --profile local-gpu up
docker compose --profile vps-light up
```

## Profiles

| Profile | Purpose | Model server | Default model size | GPU |
| --- | --- | --- | --- | --- |
| `cpu-local` | First integration target and default development path | `llama-server` | 3B Q4 GGUF | none |
| `mac-m4` | Mac M4 development through CPU-only containers | `llama-server-mac-m4` | 3B Q4 GGUF | none |
| `local-gpu` | Local CUDA workstation benchmarking | `llama-server-local-gpu` | 7B Q4 GGUF | NVIDIA |
| `vps-light` | Small VPS demo path | `llama-server-vps-light` | 1.5B Q4 GGUF | none |

The `mac-m4` profile intentionally stays CPU-only inside Docker. It avoids a
runtime dependency on host Metal acceleration and keeps the container contract
portable.

## Model files

Model files are mounted read-only from `LLM_MODELS_PATH`, defaulting to
`/tmp/p4symtest-models`. Keep model files outside the repository so large GGUF
artifacts do not enter Git history.

Expected default filenames:

| Profile | Variable | Default file |
| --- | --- | --- |
| `cpu-local` | `CPU_LOCAL_LLAMA_MODEL_FILE` | `qwen2.5-coder-3b-instruct-q4_k_m.gguf` |
| `mac-m4` | `MAC_M4_LLAMA_MODEL_FILE` | `qwen2.5-coder-3b-instruct-q4_k_m.gguf` |
| `local-gpu` | `LOCAL_GPU_LLAMA_MODEL_FILE` | `qwen2.5-coder-7b-instruct-q4_k_m.gguf` |
| `vps-light` | `VPS_LIGHT_LLAMA_MODEL_FILE` | `qwen2.5-coder-1.5b-instruct-q4_k_m.gguf` |

The model name sent by the analyzer is configured separately from the mounted
file path so future runtimes can keep OpenAI-compatible model IDs independent
from local filenames.

## Environment variables

Common variables:

| Variable | Default | Used by |
| --- | --- | --- |
| `LLM_ANALYZER_URL` | `http://llm-analyzer:8000` | backend |
| `QDRANT_URL` | `http://qdrant:6333` | analyzer |
| `LLAMA_SERVER_URL` | `http://llama-server:8080` | analyzer |
| `LLM_MODELS_PATH` | `/tmp/p4symtest-models` | llama-server containers |
| `LLAMA_SERVER_IMAGE` | `ghcr.io/ggml-org/llama.cpp:server` | CPU model servers |
| `LLAMA_SERVER_CUDA_IMAGE` | `ghcr.io/ggml-org/llama.cpp:server-cuda` | GPU model server |
| `QDRANT_IMAGE` | `qdrant/qdrant:latest` | qdrant |
| `RAG_COLLECTION` | `p4symtest-warnings` | analyzer |
| `LLM_TEMPERATURE` | `0.1` | analyzer |

Each profile exposes the same container env names:

- `LLM_RUNTIME_PROFILE`
- `LLAMA_MODEL`
- `LLAMA_CONTEXT_SIZE`
- `LLAMA_THREADS`
- `LLAMA_GPU_LAYERS`
- `LLM_REQUEST_TIMEOUT_SECONDS`
- `LLM_MAX_OUTPUT_TOKENS`

Override them from the host with profile-prefixed variables:

| Profile | Prefix |
| --- | --- |
| `cpu-local` | `CPU_LOCAL_` |
| `mac-m4` | `MAC_M4_` |
| `local-gpu` | `LOCAL_GPU_` |
| `vps-light` | `VPS_LIGHT_` |

Examples:

```bash
CPU_LOCAL_LLAMA_THREADS=6 docker compose --profile cpu-local up
MAC_M4_LLAMA_CONTEXT_SIZE=4096 docker compose --profile mac-m4 up
LOCAL_GPU_LLAMA_GPU_LAYERS=28 docker compose --profile local-gpu up
VPS_LIGHT_LLM_MAX_OUTPUT_TOKENS=256 docker compose --profile vps-light up
```

## Healthchecks

Compose expresses healthchecks for:

- `llm-analyzer`: `GET /health`
- `llama-server*`: `GET /health`
- `qdrant`: `GET /healthz`

The backend does not depend on `llm-analyzer` at startup. Diagnostics are
optional, and LLM/RAG failure must not block symbolic verification.

## Container-first tests

Run `llm-analyzer` tests inside the service container, not on the host Python:

```bash
docker compose --profile cpu-local build llm-analyzer
docker compose --profile cpu-local run --rm --no-deps llm-analyzer python -m pytest tests -q
```

The compose service mounts `./llm-analyzer` into `/srv/llm-analyzer`, so tests,
source code, and the runtime working directory use the same container path.

## Current integration note

`docker-compose.yml` references the expected `./llm-analyzer/Dockerfile` build
context. If that service has not been added yet, `docker compose config` still
validates the profile wiring, but `docker compose up` for an LLM profile will
not build the analyzer until the `llm-analyzer` implementation exists.

## Validation

Run these checks after changing runtime profiles:

```bash
docker compose --profile cpu-local config
docker compose --profile mac-m4 config
docker compose --profile local-gpu config
docker compose --profile vps-light config
```
