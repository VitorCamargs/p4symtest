import logging

from fastapi import FastAPI

from .diagnostics import PROMPT_VERSION, build_mock_diagnostics
from .models import TableAnalysisFacts, TableWarningAnalysisRequest, TableWarningDiagnostics


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("llm_analyzer")

app = FastAPI(
    title="P4SymTest LLM Analyzer Mock",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/analyze/table-warning",
    response_model=TableWarningDiagnostics,
    response_model_exclude_none=True,
)
def analyze_table_warning(
    request: TableWarningAnalysisRequest | TableAnalysisFacts,
) -> TableWarningDiagnostics:
    request = _normalize_request(request)
    request_id = request.request_id or request.facts.analysis_id
    logger.info(
        "table_warning_request request_id=%s prompt_version=%s diagnostics_mode=%s",
        request_id,
        PROMPT_VERSION,
        request.diagnostics_mode,
    )
    return build_mock_diagnostics(request)


def _normalize_request(
    request: TableWarningAnalysisRequest | TableAnalysisFacts,
) -> TableWarningAnalysisRequest:
    if isinstance(request, TableWarningAnalysisRequest):
        return request
    return TableWarningAnalysisRequest(facts=request)
