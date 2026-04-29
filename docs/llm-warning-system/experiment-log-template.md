# Experiment log template

Use this template for every warning-system experiment.

## Run metadata

- Run id:
- Date:
- Commit SHA:
- Operator:
- Hardware profile: `cpu-local` | `mac-m4` | `local-gpu` | `vps-light`
- Host description:
- Docker Compose profile:
- P4 program:
- Scenario / bug id:

## Model metadata

- Model family:
- Model file:
- Quantization:
- Runtime: `llama.cpp` | `ollama` | `vllm` | other
- Context length:
- Max output tokens:
- Temperature:
- Threads:
- GPU layers:

## RAG metadata

- Qdrant collection:
- Knowledge base version:
- Manifest checksum:
- Embedding model:
- Number of retrieved chunks:
- Retrieved chunk ids:

## P4SymTest metadata

- Component executed: parser | ingress table | egress table | deparser
- Table name:
- Switch id:
- Input snapshot:
- Output snapshot:
- Runtime config:
- Topology:

## Expected bug / behavior

- Ground truth:
- Expected warning type:
- Expected evidence:

## Observed diagnostics

- Inconclusive:
- Warning count:
- Warning types:
- Evidence ids:
- Confidence values:
- Suggested action:

## Outcome

- True positive:
- False positive:
- False negative:
- Notes:

## Performance

- Backend analysis time:
- LLM analyzer time:
- RAG retrieval time:
- Model generation time:
- Total user-visible time:
- Memory notes:
- GPU/CPU notes:

