from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from pydantic import Field

from .models import StrictBaseModel, TableAnalysisFacts


PROMPT_VERSION = "table-warning-json-v1"
MAX_CHUNK_TEXT_CHARS = 1200
MAX_P4_SOURCE_CHARS = 2400
MAX_LOG_EXCERPT_CHARS = 800


class RagChunk(StrictBaseModel):
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    citation: str = Field(min_length=1)
    version: str = Field(min_length=1)
    text: str = Field(min_length=1)
    score: float | None = Field(default=None, ge=0)


@dataclass(frozen=True)
class PromptBundle:
    messages: list[dict[str, str]]
    prompt_version: str
    rag_context_ids: list[str]


def build_table_warning_prompt(
    facts: TableAnalysisFacts,
    rag_chunks: Sequence[RagChunk | Mapping[str, Any]] | None = None,
) -> PromptBundle:
    chunks = [_coerce_chunk(chunk) for chunk in (rag_chunks or [])]
    rag_context_ids = [chunk.source_id for chunk in chunks]

    prompt_payload = {
        "prompt_version": PROMPT_VERSION,
        "task": "Analyze one P4 table execution and return evidence-based diagnostics.",
        "facts": _facts_summary(facts),
        "rag_context": [_chunk_summary(chunk) for chunk in chunks],
        "output_contract": _output_contract(),
    }

    return PromptBundle(
        messages=[
            {"role": "system", "content": _system_message()},
            {
                "role": "user",
                "content": json.dumps(prompt_payload, ensure_ascii=True, indent=2, sort_keys=True),
            },
        ],
        prompt_version=PROMPT_VERSION,
        rag_context_ids=rag_context_ids,
    )


def build_table_warning_messages(
    facts: TableAnalysisFacts,
    rag_chunks: Sequence[RagChunk | Mapping[str, Any]] | None = None,
) -> list[dict[str, str]]:
    return build_table_warning_prompt(facts, rag_chunks).messages


def _system_message() -> str:
    return (
        "You assist P4SymTest by interpreting deterministic symbolic-execution facts. "
        "You are not a verifier and must not invent unsupported behavior. "
        "Use only the supplied facts, summaries, P4 slices, runtime/topology summaries, logs, "
        "and RAG chunks. If evidence is insufficient, mark the diagnostic inconclusive. "
        "Return exactly one JSON object and no markdown, comments, prose, or code fences."
    )


def _facts_summary(facts: TableAnalysisFacts) -> dict[str, Any]:
    return {
        "facts_version": facts.facts_version,
        "analysis_id": facts.analysis_id,
        "pipeline": facts.pipeline,
        "table_name": facts.table_name,
        "switch_id": facts.switch_id,
        "snapshots": {
            "input": {
                "filename": facts.input_snapshot.filename,
                "state_count": facts.input_snapshot.state_count,
            },
            "output": {
                "filename": facts.output_snapshot.filename,
                "state_count": facts.output_snapshot.state_count,
            },
        },
        "state_summary": facts.state_summary.model_dump(mode="json"),
        "runtime_entries": [
            entry.model_dump(mode="json") for entry in facts.runtime_entries
        ],
        "topology_slice": facts.topology_slice,
        "p4_slice": {
            "table_source": _truncate(facts.p4_slice.table_source, MAX_P4_SOURCE_CHARS),
            "action_sources": [
                _truncate(source, MAX_P4_SOURCE_CHARS)
                for source in facts.p4_slice.action_sources
            ],
        },
        "symbolic_facts": [
            fact.model_dump(mode="json") for fact in facts.symbolic_facts
        ],
        "log_summary": {
            "stdout_excerpt": _truncate(
                facts.log_summary.stdout_excerpt,
                MAX_LOG_EXCERPT_CHARS,
            ),
            "stderr_excerpt": _truncate(
                facts.log_summary.stderr_excerpt,
                MAX_LOG_EXCERPT_CHARS,
            ),
        },
        "available_evidence": _available_evidence(facts),
    }


def _available_evidence(facts: TableAnalysisFacts) -> list[dict[str, str]]:
    evidence = [
        {
            "id": "snapshot.input",
            "source": "snapshot_summary",
            "summary": (
                f"Input snapshot {facts.input_snapshot.filename} has "
                f"{_fmt_count(facts.input_snapshot.state_count)} states."
            ),
        },
        {
            "id": "snapshot.output",
            "source": "snapshot_summary",
            "summary": (
                f"Output snapshot {facts.output_snapshot.filename} has "
                f"{_fmt_count(facts.output_snapshot.state_count)} states."
            ),
        },
        {
            "id": "state.summary",
            "source": "snapshot_summary",
            "summary": (
                f"{_fmt_count(facts.state_summary.input_states)} input states, "
                f"{_fmt_count(facts.state_summary.output_states)} output states, "
                f"{_fmt_count(facts.state_summary.drop_states)} drop states."
            ),
        },
        {
            "id": "p4.table",
            "source": "p4_slice",
            "summary": _truncate(" ".join(facts.p4_slice.table_source.split()), 360),
        },
        {
            "id": "runtime.entries",
            "source": "runtime",
            "summary": f"{len(facts.runtime_entries)} runtime entries supplied.",
        },
        {
            "id": "topology.slice",
            "source": "topology",
            "summary": _topology_summary(facts.topology_slice),
        },
        {
            "id": "log.summary",
            "source": "log_summary",
            "summary": _log_summary(
                facts.log_summary.stdout_excerpt,
                facts.log_summary.stderr_excerpt,
            ),
        },
    ]

    for update in facts.state_summary.field_updates:
        evidence.append(
            {
                "id": f"field_update.{_safe_id(update.field)}",
                "source": "snapshot_summary",
                "summary": f"{update.field}: {update.summary}",
            }
        )

    for symbolic_fact in facts.symbolic_facts:
        evidence.append(
            {
                "id": f"symbolic.{symbolic_fact.id}",
                "source": "symbolic_fact",
                "summary": f"{symbolic_fact.kind}: {symbolic_fact.summary}",
            }
        )

    return evidence


def _chunk_summary(chunk: RagChunk) -> dict[str, Any]:
    return {
        "source_id": chunk.source_id,
        "title": chunk.title,
        "source_type": chunk.source_type,
        "citation": chunk.citation,
        "version": chunk.version,
        "score": chunk.score,
        "text": _truncate(chunk.text, MAX_CHUNK_TEXT_CHARS),
    }


def _output_contract() -> dict[str, Any]:
    return {
        "json_only": True,
        "schema_name": "TableWarningDiagnostics",
        "required_top_level_fields": [
            "diagnostics_version",
            "table_name",
            "expected_behavior",
            "observed_behavior",
            "warnings",
            "inconclusive",
            "evidence",
            "model_info",
            "rag_context_ids",
        ],
        "warning_types": [
            "unreachable_table",
            "unexpected_drop",
            "rule_shadowing",
            "missing_runtime_entry",
            "unexpected_field_update",
            "no_effect_action",
            "parser_table_mismatch",
            "deparser_invalid_header",
            "egress_spec_conflict",
        ],
        "severity_values": ["info", "low", "medium", "high"],
        "evidence_sources": [
            "symbolic_fact",
            "p4_slice",
            "runtime",
            "topology",
            "snapshot_summary",
            "log_summary",
            "rag_chunk",
        ],
        "rules": [
            "Every warning must include one or more evidence_ids.",
            "Every warning evidence_id must refer to an item in evidence.",
            "Use only evidence supported by the supplied facts or RAG chunks.",
            "If no warning is supported, return warnings as an empty array.",
            "If evidence is insufficient, set inconclusive to true and warnings to an empty array.",
            "Do not include raw snapshots, packet dumps, or unprovided source text.",
        ],
    }


def _coerce_chunk(chunk: RagChunk | Mapping[str, Any]) -> RagChunk:
    if isinstance(chunk, RagChunk):
        return chunk
    return RagChunk.model_validate(chunk)


def _truncate(value: str, limit: int) -> str:
    normalized = value.strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _topology_summary(value: dict[str, Any]) -> str:
    if not value:
        return "Topology slice is empty."
    keys = ", ".join(sorted(str(key) for key in value.keys())[:8])
    suffix = "" if len(value) <= 8 else ", ..."
    return f"Topology keys: {keys}{suffix}."


def _log_summary(stdout_excerpt: str, stderr_excerpt: str) -> str:
    if stderr_excerpt.strip():
        return f"stderr: {_truncate(stderr_excerpt, 360)}"
    if stdout_excerpt.strip():
        return f"stdout: {_truncate(stdout_excerpt, 360)}"
    return "No stdout or stderr excerpt supplied."


def _fmt_count(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return str(value)


def _safe_id(value: str) -> str:
    cleaned = "".join(char if char.isalnum() else "." for char in value.strip().lower())
    cleaned = ".".join(part for part in cleaned.split(".") if part)
    return cleaned or "unknown"
