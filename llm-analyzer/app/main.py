import logging

import httpx
from fastapi import FastAPI, HTTPException

from .diagnostics import PROMPT_VERSION, build_mock_diagnostics
from .models import TableAnalysisFacts, TableWarningAnalysisRequest, TableWarningDiagnostics
from .rag import RagSearchService, build_default_rag_service
from .rag_models import RagSearchRequest, RagSearchResponse


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


@app.post("/rag/search", response_model=RagSearchResponse)
def rag_search(request: RagSearchRequest) -> RagSearchResponse:
    service = _rag_service()
    try:
        response = service.search(request)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="rag store unavailable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info(
        "rag_search_request recovered_chunk_ids=%s",
        ",".join(response.chunk_ids),
    )
    return response


def _normalize_request(
    request: TableWarningAnalysisRequest | TableAnalysisFacts,
) -> TableWarningAnalysisRequest:
    if isinstance(request, TableWarningAnalysisRequest):
        return request
    return TableWarningAnalysisRequest(facts=request)


def _rag_service() -> RagSearchService:
    service = getattr(app.state, "rag_search_service", None)
    if service is None:
        service = build_default_rag_service()
        app.state.rag_search_service = service
    return service
