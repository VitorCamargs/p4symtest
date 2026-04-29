import logging

import httpx
from fastapi import FastAPI, HTTPException

from .diagnostics import PROMPT_VERSION as MOCK_PROMPT_VERSION, build_mock_diagnostics
from .llm_client import LlamaServerConfig, analyze_table_warning_with_llm
from .models import TableAnalysisFacts, TableWarningAnalysisRequest, TableWarningDiagnostics
from .prompt_builder import PROMPT_VERSION as LLM_PROMPT_VERSION
from .rag import RagSearchService, build_default_rag_service
from .rag_models import RagSearchRequest, RagSearchResponse
from .response_validator import build_inconclusive_fallback
from .warning_pipeline import analyze_table_warning_with_rag


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("llm_analyzer")

app = FastAPI(
    title="P4SymTest LLM Analyzer",
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
        "table_warning_request request_id=%s mock_prompt_version=%s diagnostics_mode=%s",
        request_id,
        MOCK_PROMPT_VERSION,
        request.diagnostics_mode,
    )
    if request.diagnostics_mode in {"mock", "mock_inconclusive"}:
        return build_mock_diagnostics(request)
    return _run_model_diagnostics(request)


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


def _run_model_diagnostics(request: TableWarningAnalysisRequest) -> TableWarningDiagnostics:
    facts = request.facts
    config = LlamaServerConfig.from_env()
    try:
        if request.diagnostics_mode == "llm":
            return analyze_table_warning_with_llm(facts, config=config)
        if request.diagnostics_mode == "rag_llm":
            return analyze_table_warning_with_rag(
                facts,
                rag_service=_rag_service(),
                llm_config=config,
            )
    except Exception as exc:
        logger.exception(
            "table_warning_model_pipeline_failed diagnostics_mode=%s table=%s",
            request.diagnostics_mode,
            facts.table_name,
        )
        return build_inconclusive_fallback(
            facts,
            reason=f"{request.diagnostics_mode} diagnostics failed: {type(exc).__name__}.",
            provider="llm-analyzer",
            model=config.model,
            prompt_version=LLM_PROMPT_VERSION,
        )

    raise HTTPException(status_code=400, detail="unsupported diagnostics_mode")


def _rag_service() -> RagSearchService:
    service = getattr(app.state, "rag_search_service", None)
    if service is None:
        service = build_default_rag_service()
        app.state.rag_search_service = service
    return service
