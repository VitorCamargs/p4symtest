from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import ValidationError

from .models import (
    EvidenceItem,
    ModelInfo,
    TableAnalysisFacts,
    TableWarningDiagnostics,
)
from .prompt_builder import PROMPT_VERSION


FALLBACK_DIAGNOSTICS_VERSION = "llm.fallback.v1"
LLM_DIAGNOSTICS_VERSION = "llm.table-warning.v1"


def parse_table_warning_diagnostics(
    content: str,
    facts: TableAnalysisFacts,
    *,
    provider: str,
    model: str,
    prompt_version: str = PROMPT_VERSION,
    rag_context_ids: Iterable[str] | None = None,
) -> TableWarningDiagnostics:
    context_ids = list(rag_context_ids or [])

    try:
        payload = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return build_inconclusive_fallback(
            facts,
            reason="Model response was not valid JSON.",
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            rag_context_ids=context_ids,
        )

    if not isinstance(payload, Mapping):
        return build_inconclusive_fallback(
            facts,
            reason="Model response JSON was not an object.",
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            rag_context_ids=context_ids,
        )

    return validate_table_warning_diagnostics(
        payload,
        facts,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        rag_context_ids=context_ids,
    )


def validate_table_warning_diagnostics(
    payload: Mapping[str, Any],
    facts: TableAnalysisFacts,
    *,
    provider: str,
    model: str,
    prompt_version: str = PROMPT_VERSION,
    rag_context_ids: Iterable[str] | None = None,
) -> TableWarningDiagnostics:
    context_ids = list(rag_context_ids or [])
    normalized_payload = dict(payload)
    normalized_payload["model_info"] = {
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
    }
    normalized_payload["rag_context_ids"] = context_ids

    try:
        diagnostics = TableWarningDiagnostics.model_validate(normalized_payload)
    except ValidationError as exc:
        return build_inconclusive_fallback(
            facts,
            reason=f"Model response failed diagnostics schema validation: {exc.errors()[0]['type']}.",
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            rag_context_ids=context_ids,
        )

    if diagnostics.table_name != facts.table_name:
        return build_inconclusive_fallback(
            facts,
            reason="Model response table_name did not match the analyzed facts.",
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            rag_context_ids=context_ids,
        )

    if diagnostics.inconclusive and diagnostics.warnings:
        return build_inconclusive_fallback(
            facts,
            reason="Model response was inconclusive but still returned warnings.",
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            rag_context_ids=context_ids,
        )

    if not diagnostics.evidence:
        return build_inconclusive_fallback(
            facts,
            reason="Model response did not include supporting evidence.",
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            rag_context_ids=context_ids,
        )

    evidence_ids = {item.id for item in diagnostics.evidence}
    for warning in diagnostics.warnings:
        missing_ids = [item_id for item_id in warning.evidence_ids if item_id not in evidence_ids]
        if missing_ids:
            return build_inconclusive_fallback(
                facts,
                reason="Model warning referenced evidence that was not present in the response.",
                provider=provider,
                model=model,
                prompt_version=prompt_version,
                rag_context_ids=context_ids,
            )

    return diagnostics


def build_inconclusive_fallback(
    facts: TableAnalysisFacts,
    *,
    reason: str,
    provider: str,
    model: str,
    prompt_version: str = PROMPT_VERSION,
    rag_context_ids: Iterable[str] | None = None,
) -> TableWarningDiagnostics:
    return TableWarningDiagnostics(
        diagnostics_version=FALLBACK_DIAGNOSTICS_VERSION,
        table_name=facts.table_name,
        expected_behavior=(
            f"No supported LLM expected-behavior interpretation is available for "
            f"{facts.pipeline} table {facts.table_name}."
        ),
        observed_behavior=reason,
        warnings=[],
        inconclusive=True,
        evidence=_fallback_evidence(facts),
        model_info=ModelInfo(
            provider=provider,
            model=model,
            prompt_version=prompt_version,
        ),
        rag_context_ids=list(rag_context_ids or []),
    )


def _fallback_evidence(facts: TableAnalysisFacts) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            id="state.summary",
            source="snapshot_summary",
            summary=(
                f"Fallback used deterministic state counts only: "
                f"{_fmt_count(facts.state_summary.input_states)} input, "
                f"{_fmt_count(facts.state_summary.output_states)} output, "
                f"{_fmt_count(facts.state_summary.drop_states)} drop states."
            ),
        ),
        EvidenceItem(
            id="snapshot.input",
            source="snapshot_summary",
            summary=(
                f"Input snapshot {facts.input_snapshot.filename} contains "
                f"{_fmt_count(facts.input_snapshot.state_count)} states."
            ),
            location=facts.input_snapshot.filename,
        ),
        EvidenceItem(
            id="snapshot.output",
            source="snapshot_summary",
            summary=(
                f"Output snapshot {facts.output_snapshot.filename} contains "
                f"{_fmt_count(facts.output_snapshot.state_count)} states."
            ),
            location=facts.output_snapshot.filename,
        ),
    ]


def _fmt_count(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return str(value)
