from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


Pipeline = Literal["ingress", "egress"]
SymbolicFactKind = Literal[
    "reachability",
    "drop",
    "field_update",
    "parser_constraint",
    "runtime_match",
    "topology",
]
WarningType = Literal[
    "unreachable_table",
    "unexpected_drop",
    "rule_shadowing",
    "missing_runtime_entry",
    "unexpected_field_update",
    "no_effect_action",
    "parser_table_mismatch",
    "deparser_invalid_header",
    "egress_spec_conflict",
]
Severity = Literal["info", "low", "medium", "high"]
WarningSource = Literal["deterministic", "llm_hypothesis"]
EvidenceSource = Literal[
    "symbolic_fact",
    "p4_slice",
    "runtime",
    "topology",
    "snapshot_summary",
    "log_summary",
    "rag_chunk",
]
DiagnosticsMode = Literal["mock", "mock_inconclusive", "llm", "rag_llm"]


class SnapshotSummary(StrictBaseModel):
    filename: str = Field(min_length=1)
    state_count: float = Field(ge=0)


class FieldUpdateSummary(StrictBaseModel):
    field: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class StateSummary(StrictBaseModel):
    input_states: float = Field(ge=0)
    output_states: float = Field(ge=0)
    drop_states: float = Field(ge=0)
    field_updates: list[FieldUpdateSummary]


class RuntimeEntry(StrictBaseModel):
    match: dict[str, Any]
    action: str = Field(min_length=1)
    action_params: dict[str, Any]


class P4Slice(StrictBaseModel):
    table_source: str
    action_sources: list[str]


class SymbolicFact(StrictBaseModel):
    id: str = Field(min_length=1)
    kind: SymbolicFactKind
    summary: str = Field(min_length=1)


class LogSummary(StrictBaseModel):
    stdout_excerpt: str
    stderr_excerpt: str


class TableAnalysisFacts(StrictBaseModel):
    facts_version: str = Field(min_length=1)
    analysis_id: str = Field(min_length=1)
    pipeline: Pipeline
    table_name: str = Field(min_length=1)
    switch_id: str = Field(min_length=1)
    input_snapshot: SnapshotSummary
    output_snapshot: SnapshotSummary
    state_summary: StateSummary
    runtime_entries: list[RuntimeEntry]
    topology_slice: dict[str, Any]
    p4_slice: P4Slice
    symbolic_facts: list[SymbolicFact]
    log_summary: LogSummary


class TableWarningAnalysisRequest(StrictBaseModel):
    facts: TableAnalysisFacts
    request_id: str | None = None
    diagnostics_mode: DiagnosticsMode = "mock"
    metadata: dict[str, Any] = Field(default_factory=dict)


class WarningDiagnostic(StrictBaseModel):
    type: WarningType
    severity: Severity
    confidence: float = Field(ge=0, le=1)
    source: WarningSource
    evidence_ids: list[str] = Field(min_length=1)
    explanation: str = Field(min_length=1)
    suggested_action: str = Field(min_length=1)


class EvidenceItem(StrictBaseModel):
    id: str = Field(min_length=1)
    source: EvidenceSource
    summary: str = Field(min_length=1)
    location: str | None = None


class ModelInfo(StrictBaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)


class TableWarningDiagnostics(StrictBaseModel):
    diagnostics_version: str = Field(min_length=1)
    table_name: str = Field(min_length=1)
    expected_behavior: str = Field(min_length=1)
    observed_behavior: str = Field(min_length=1)
    warnings: list[WarningDiagnostic]
    inconclusive: bool
    evidence: list[EvidenceItem]
    model_info: ModelInfo
    rag_context_ids: list[str]
