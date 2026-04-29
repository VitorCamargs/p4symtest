import json
import logging
from pathlib import Path

import httpx

from app.llm_client import LlamaServerClient, LlamaServerConfig
from app.rag import HashingTextEmbedder, RagSearchService
from app.rag_client import InMemoryRagStore
from app.rag_ingestion import ingest_manifest, load_rag_manifest
from app.warning_pipeline import (
    analyze_table_warning_with_rag,
    build_table_warning_rag_query,
)
from test_prompt_builder import sample_facts


FIXTURE = Path(__file__).parent / "fixtures" / "rag" / "sample_manifest.json"


def test_rag_prompt_llm_mock_pipeline_returns_context_ids(caplog) -> None:
    facts = sample_facts()
    service, chunk_ids = _rag_service_with_fixture()

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        user_payload = json.loads(body["messages"][1]["content"])
        assert user_payload["prompt_version"] == "table-warning-json-v1"
        assert user_payload["rag_context"][0]["source_id"] == "v1model-egress-spec"
        assert "mark_to_drop" in user_payload["rag_context"][0]["text"]
        return _completion_response(_valid_model_payload(facts.table_name))

    caplog.set_level(logging.INFO, logger="llm_analyzer.warning_pipeline")
    diagnostics = analyze_table_warning_with_rag(
        facts,
        rag_service=service,
        llm_client=_mock_client(handler),
        query_vector=[1.0, 0.0, 0.0, 0.0],
        rag_limit=1,
    )

    assert diagnostics.inconclusive is False
    assert diagnostics.warnings[0].type == "unexpected_drop"
    assert diagnostics.model_info.provider == "llama-server"
    assert diagnostics.model_info.prompt_version == "table-warning-json-v1"
    assert diagnostics.rag_context_ids == [chunk_ids[0]]
    assert "warning_pipeline_context" in caplog.text
    assert chunk_ids[0] in caplog.text
    assert "qwen-pipeline-test" in caplog.text


def test_rag_prompt_llm_timeout_returns_inconclusive_with_context_ids() -> None:
    facts = sample_facts()
    service, chunk_ids = _rag_service_with_fixture()

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    diagnostics = analyze_table_warning_with_rag(
        facts,
        rag_service=service,
        llm_client=_mock_client(handler),
        query_vector=[1.0, 0.0, 0.0, 0.0],
        rag_limit=1,
    )

    assert diagnostics.inconclusive is True
    assert diagnostics.warnings == []
    assert diagnostics.rag_context_ids == [chunk_ids[0]]
    assert diagnostics.observed_behavior == "llama-server request timed out."


def test_pipeline_builds_query_from_table_facts() -> None:
    query = build_table_warning_rag_query(sample_facts())

    assert "ingress" in query
    assert "MyIngress.ipv4_lpm" in query
    assert "drops 3" in query
    assert "standard_metadata.egress_spec" in query


def _rag_service_with_fixture() -> tuple[RagSearchService, list[str]]:
    manifest = load_rag_manifest(FIXTURE)
    store = InMemoryRagStore()
    ingestion = ingest_manifest(manifest, store)
    return (
        RagSearchService(
            store=store,
            collection="rag-test",
            embedder=HashingTextEmbedder(vector_size=4),
        ),
        ingestion.chunk_ids,
    )


def _mock_client(handler) -> LlamaServerClient:
    return LlamaServerClient(
        config=LlamaServerConfig(
            base_url="http://llama-server-test:8080",
            model="qwen-pipeline-test",
            temperature=0.1,
            timeout_seconds=3,
            max_output_tokens=256,
        ),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _completion_response(payload: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "qwen-pipeline-test",
            "choices": [{"message": {"content": json.dumps(payload)}}],
        },
    )


def _valid_model_payload(table_name: str) -> dict:
    return {
        "diagnostics_version": "llm.table-warning.v1",
        "table_name": table_name,
        "expected_behavior": "The table appears intended to forward IPv4 traffic.",
        "observed_behavior": "All analyzed states were dropped.",
        "warnings": [
            {
                "type": "unexpected_drop",
                "severity": "high",
                "confidence": 0.82,
                "source": "llm_hypothesis",
                "evidence_ids": ["state.summary"],
                "explanation": "The state summary reports only dropped output states.",
                "suggested_action": "Inspect runtime entries and egress_spec assignments.",
            }
        ],
        "inconclusive": False,
        "evidence": [
            {
                "id": "state.summary",
                "source": "snapshot_summary",
                "summary": "Three input states produced three dropped output states.",
            }
        ],
    }
