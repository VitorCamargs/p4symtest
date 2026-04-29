# Integration smoke tests

This document records the first sequential integrations for the table-warning
pipeline. These checks keep P4SymTest as the orchestrator and exercise the LLM
layer only as an optional diagnostics interpreter.

## Backend to analyzer mock

The backend smoke script builds `TableAnalysisFacts` from backend fixtures and
sends them to a real `llm-analyzer` mock service over HTTP.

Run the analyzer mock in a container. `--use-aliases` makes the one-off
container reachable as `llm-analyzer` on the compose network:

```bash
docker compose --profile cpu-local run --rm --no-deps --use-aliases llm-analyzer
```

In another shell, run the backend smoke script inside the backend container:

```bash
docker compose run --rm --no-deps \
  -e P4SYMTEST_TABLE_DIAGNOSTICS_ENABLED=1 \
  -e P4SYMTEST_LLM_ANALYZER_URL=http://llm-analyzer:8000 \
  backend python3 tests/integration_warning_analyzer_smoke.py
```

Expected output is a JSON object with `status=ok`, `provider=mock`, a table
name, a warning count, and an evidence count.

Diagnostics remain optional: if this endpoint is unavailable, the backend must
keep returning the symbolic verification result with an inconclusive diagnostics
fallback when diagnostics are enabled, or no diagnostics field when diagnostics
are disabled.
