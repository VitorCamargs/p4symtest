from __future__ import annotations

from typing import Any

from .models import (
    EvidenceItem,
    ModelInfo,
    TableAnalysisFacts,
    TableWarningAnalysisRequest,
    TableWarningDiagnostics,
    WarningDiagnostic,
)


DIAGNOSTICS_VERSION = "onda0.mock.v1"
PROMPT_VERSION = "mock-table-warning-v1"
MOCK_PROVIDER = "mock"
MOCK_MODEL = "deterministic-table-warning"


def build_mock_diagnostics(request: TableWarningAnalysisRequest) -> TableWarningDiagnostics:
    facts = request.facts
    evidence = _build_evidence(facts)
    evidence_by_id = {item.id: item for item in evidence}
    inconclusive = _is_inconclusive_request(request)

    if inconclusive:
        warnings: list[WarningDiagnostic] = []
        expected_behavior = (
            f"Mock analysis could not establish a supported expected behavior for "
            f"{facts.pipeline} table {facts.table_name}."
        )
        observed_behavior = (
            "The request explicitly asked the mock service to abstain, so the "
            "diagnostic is marked inconclusive."
        )
    else:
        warnings = _build_warnings(facts, evidence_by_id)
        expected_behavior = _expected_behavior(facts)
        observed_behavior = _observed_behavior(facts)

    return TableWarningDiagnostics(
        diagnostics_version=DIAGNOSTICS_VERSION,
        table_name=facts.table_name,
        expected_behavior=expected_behavior,
        observed_behavior=observed_behavior,
        warnings=warnings,
        inconclusive=inconclusive,
        evidence=evidence,
        model_info=ModelInfo(
            provider=MOCK_PROVIDER,
            model=MOCK_MODEL,
            prompt_version=PROMPT_VERSION,
        ),
        rag_context_ids=[],
    )


def _is_inconclusive_request(request: TableWarningAnalysisRequest) -> bool:
    if request.diagnostics_mode == "mock_inconclusive":
        return True

    metadata = request.metadata
    if metadata.get("force_inconclusive") is True:
        return True

    for fact in request.facts.symbolic_facts:
        if "mock_inconclusive" in fact.summary.lower():
            return True

    return False


def _build_evidence(facts: TableAnalysisFacts) -> list[EvidenceItem]:
    evidence: list[EvidenceItem] = [
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
        EvidenceItem(
            id="state.summary",
            source="snapshot_summary",
            summary=(
                f"State summary: {_fmt_count(facts.state_summary.input_states)} input, "
                f"{_fmt_count(facts.state_summary.output_states)} output, "
                f"{_fmt_count(facts.state_summary.drop_states)} drop states."
            ),
        ),
        EvidenceItem(
            id="p4.table",
            source="p4_slice",
            summary=_compact_text(facts.p4_slice.table_source) or "P4 table slice provided.",
        ),
        EvidenceItem(
            id="runtime.entries",
            source="runtime",
            summary=f"{len(facts.runtime_entries)} runtime entries supplied for the table.",
        ),
        EvidenceItem(
            id="topology.slice",
            source="topology",
            summary=_summarize_mapping(facts.topology_slice, "Topology slice supplied."),
        ),
        EvidenceItem(
            id="log.summary",
            source="log_summary",
            summary=_summarize_logs(facts.log_summary.stdout_excerpt, facts.log_summary.stderr_excerpt),
        ),
    ]

    for update in facts.state_summary.field_updates:
        evidence.append(
            EvidenceItem(
                id=f"field_update.{_safe_id(update.field)}",
                source="snapshot_summary",
                summary=f"{update.field}: {update.summary}",
            )
        )

    for symbolic_fact in facts.symbolic_facts:
        evidence.append(
            EvidenceItem(
                id=f"symbolic.{symbolic_fact.id}",
                source="symbolic_fact",
                summary=f"{symbolic_fact.kind}: {symbolic_fact.summary}",
            )
        )

    return evidence


def _build_warnings(
    facts: TableAnalysisFacts,
    evidence_by_id: dict[str, EvidenceItem],
) -> list[WarningDiagnostic]:
    if facts.output_snapshot.state_count == 0:
        return [
            WarningDiagnostic(
                type="unreachable_table",
                severity="medium",
                confidence=0.72,
                source="deterministic",
                evidence_ids=_existing_ids(evidence_by_id, ["snapshot.input", "snapshot.output", "state.summary"]),
                explanation=(
                    "The mock analyzer observed no output states for this table execution, "
                    "which is consistent with an unreachable table or an unsatisfied path condition."
                ),
                suggested_action=(
                    "Check parser and pipeline reachability constraints before investigating runtime entries."
                ),
            )
        ]

    if facts.state_summary.drop_states > 0:
        return [
            WarningDiagnostic(
                type="unexpected_drop",
                severity="high",
                confidence=0.78,
                source="llm_hypothesis",
                evidence_ids=_existing_ids(
                    evidence_by_id,
                    ["state.summary", "snapshot.output", "p4.table", "runtime.entries", "topology.slice"],
                ),
                explanation=(
                    "The table produced dropped states in a context that contains table source, "
                    "runtime, and topology evidence. The mock warning treats this as suspicious "
                    "forwarding behavior rather than proof of a bug."
                ),
                suggested_action=(
                    "Inspect the table match keys, default action, and egress_spec assignments for the dropped states."
                ),
            )
        ]

    if not facts.runtime_entries:
        return [
            WarningDiagnostic(
                type="missing_runtime_entry",
                severity="medium",
                confidence=0.68,
                source="deterministic",
                evidence_ids=_existing_ids(evidence_by_id, ["runtime.entries", "p4.table", "state.summary"]),
                explanation=(
                    "No runtime entries were supplied for a table execution that still reached output states."
                ),
                suggested_action="Verify whether this table requires runtime entries for the analyzed switch.",
            )
        ]

    if not facts.state_summary.field_updates:
        return [
            WarningDiagnostic(
                type="no_effect_action",
                severity="low",
                confidence=0.56,
                source="llm_hypothesis",
                evidence_ids=_existing_ids(evidence_by_id, ["state.summary", "p4.table"]),
                explanation=(
                    "No field updates were reported by the deterministic facts for this table execution."
                ),
                suggested_action="Confirm that the selected action is expected to leave observable state unchanged.",
            )
        ]

    return []


def _expected_behavior(facts: TableAnalysisFacts) -> str:
    return (
        f"The {facts.pipeline} table {facts.table_name} is expected to apply its P4 table "
        "logic to the provided symbolic input states using the supplied runtime and topology context."
    )


def _observed_behavior(facts: TableAnalysisFacts) -> str:
    return (
        f"The mock analyzer observed {_fmt_count(facts.state_summary.input_states)} input states, "
        f"{_fmt_count(facts.state_summary.output_states)} output states, and "
        f"{_fmt_count(facts.state_summary.drop_states)} drop states."
    )


def _existing_ids(evidence_by_id: dict[str, EvidenceItem], preferred_ids: list[str]) -> list[str]:
    ids = [evidence_id for evidence_id in preferred_ids if evidence_id in evidence_by_id]
    if ids:
        return ids
    return [next(iter(evidence_by_id))]


def _fmt_count(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return str(value)


def _safe_id(value: str) -> str:
    cleaned = "".join(char if char.isalnum() else "." for char in value.strip().lower())
    cleaned = ".".join(part for part in cleaned.split(".") if part)
    return cleaned or "unknown"


def _compact_text(value: str, limit: int = 180) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _summarize_mapping(value: dict[str, Any], fallback: str) -> str:
    if not value:
        return "Topology slice is empty."
    keys = ", ".join(sorted(str(key) for key in value.keys())[:6])
    suffix = "" if len(value) <= 6 else ", ..."
    return f"{fallback} Keys: {keys}{suffix}."


def _summarize_logs(stdout_excerpt: str, stderr_excerpt: str) -> str:
    if stderr_excerpt.strip():
        return f"stderr: {_compact_text(stderr_excerpt)}"
    if stdout_excerpt.strip():
        return f"stdout: {_compact_text(stdout_excerpt)}"
    return "No stdout or stderr excerpt supplied."

