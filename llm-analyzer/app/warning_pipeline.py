from __future__ import annotations

import logging

from .llm_client import LlamaServerClient, LlamaServerConfig, analyze_table_warning_with_llm
from .models import TableAnalysisFacts, TableWarningDiagnostics
from .prompt_builder import PROMPT_VERSION
from .rag import RagSearchService
from .rag_models import RagSearchRequest


logger = logging.getLogger("llm_analyzer.warning_pipeline")


def analyze_table_warning_with_rag(
    facts: TableAnalysisFacts,
    *,
    rag_service: RagSearchService,
    llm_client: LlamaServerClient | None = None,
    llm_config: LlamaServerConfig | None = None,
    query_vector: list[float] | None = None,
    rag_limit: int = 5,
) -> TableWarningDiagnostics:
    rag_response = rag_service.search(
        RagSearchRequest(
            query=build_table_warning_rag_query(facts),
            limit=rag_limit,
            query_vector=query_vector,
        )
    )
    diagnostics = analyze_table_warning_with_llm(
        facts,
        rag_chunks=[chunk.model_dump(exclude_none=True) for chunk in rag_response.chunks],
        client=llm_client,
        config=llm_config,
    )
    diagnostics = diagnostics.model_copy(update={"rag_context_ids": rag_response.chunk_ids})
    logger.info(
        "warning_pipeline_context prompt_version=%s model=%s chunk_ids=%s",
        PROMPT_VERSION,
        diagnostics.model_info.model,
        ",".join(rag_response.chunk_ids),
    )
    return diagnostics


def build_table_warning_rag_query(facts: TableAnalysisFacts) -> str:
    symbolic_summaries = " ".join(fact.summary for fact in facts.symbolic_facts)
    field_updates = " ".join(
        f"{update.field} {update.summary}"
        for update in facts.state_summary.field_updates
    )
    table_source = " ".join(facts.p4_slice.table_source.split())[:500]
    return " ".join(
        part
        for part in [
            facts.pipeline,
            facts.table_name,
            f"drops {facts.state_summary.drop_states}",
            symbolic_summaries,
            field_updates,
            table_source,
        ]
        if part
    )
