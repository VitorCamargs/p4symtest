import json

import httpx

from app.llm_client import (
    LlamaServerClient,
    LlamaServerConfig,
    analyze_table_warning_with_llm,
)
from app.prompt_builder import RagChunk
from test_prompt_builder import sample_facts


def test_config_reads_env_aliases() -> None:
    config = LlamaServerConfig.from_env(
        {
            "LLAMA_SERVER_URL": "http://llama-server-test:8080",
            "LLAMA_MODEL": "qwen2.5-coder-test",
            "LLM_TEMPERATURE": "0.05",
            "LLM_REQUEST_TIMEOUT_SECONDS": "12",
            "LLM_MAX_OUTPUT_TOKENS": "256",
            "LLM_JSON_RESPONSE_FORMAT": "false",
            "LLM_REPAIR_ATTEMPTS": "2",
        }
    )

    assert config.base_url == "http://llama-server-test:8080"
    assert config.chat_completions_url == "http://llama-server-test:8080/v1/chat/completions"
    assert config.model == "qwen2.5-coder-test"
    assert config.temperature == 0.05
    assert config.timeout_seconds == 12
    assert config.max_output_tokens == 256
    assert config.json_response_format is False
    assert config.repair_attempts == 2


def test_config_prefers_base_url_and_timeout_aliases() -> None:
    config = LlamaServerConfig.from_env(
        {
            "LLAMA_BASE_URL": "http://preferred:9090",
            "LLAMA_SERVER_URL": "http://fallback:8080",
            "LLM_TIMEOUT_SECONDS": "7",
            "LLM_REQUEST_TIMEOUT_SECONDS": "12",
        }
    )

    assert config.base_url == "http://preferred:9090"
    assert config.timeout_seconds == 7


def test_mock_llm_returns_valid_json() -> None:
    facts = sample_facts()
    chunk = RagChunk(
        source_id="routing-doc-001",
        title="Routing lookup",
        source_type="routing",
        citation="routing-note",
        version="1",
        text="IPv4 forwarding usually selects an egress port for reachable destinations.",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert body["model"] == "qwen-test"
        assert body["temperature"] == 0.2
        assert body["max_tokens"] == 128
        assert body["response_format"] == {"type": "json_object"}
        assert body["messages"][0]["role"] == "system"

        return httpx.Response(
            200,
            json={
                "model": "qwen-test",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(_valid_model_payload(facts.table_name))
                        }
                    }
                ],
            },
        )

    client = _mock_client(handler)

    diagnostics = analyze_table_warning_with_llm(
        facts,
        rag_chunks=[chunk],
        client=client,
    )

    assert diagnostics.inconclusive is False
    assert diagnostics.warnings[0].type == "unexpected_drop"
    assert diagnostics.model_info.provider == "llama-server"
    assert diagnostics.model_info.model == "qwen-test"
    assert diagnostics.model_info.prompt_version == "table-warning-json-v2"
    assert diagnostics.rag_context_ids == ["routing-doc-001"]


def test_fenced_json_is_parsed_without_repair() -> None:
    facts = sample_facts()
    calls = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append("initial")
        return httpx.Response(
            200,
            json={
                "model": "qwen-test",
                "choices": [
                    {
                        "message": {
                            "content": "```json\n"
                            + json.dumps(_valid_model_payload(facts.table_name))
                            + "\n```"
                        }
                    }
                ],
            },
        )

    diagnostics = analyze_table_warning_with_llm(facts, client=_mock_client(handler))

    assert calls == ["initial"]
    assert diagnostics.inconclusive is False
    assert diagnostics.warnings[0].type == "unexpected_drop"


def test_mock_llm_returns_invalid_json() -> None:
    facts = sample_facts()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "qwen-test",
                "choices": [{"message": {"content": "not json"}}],
            },
        )

    diagnostics = analyze_table_warning_with_llm(facts, client=_mock_client(handler))

    assert diagnostics.inconclusive is True
    assert diagnostics.warnings == []
    assert diagnostics.diagnostics_version == "llm.fallback.v1"
    assert "valid JSON" in diagnostics.observed_behavior


def test_invalid_first_response_is_repaired() -> None:
    facts = sample_facts()
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body["messages"][0]["content"])
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={
                    "model": "qwen-test",
                    "choices": [{"message": {"content": "not json"}}],
                },
            )
        assert "repair" in body["messages"][0]["content"].lower()
        return _completion_response(_valid_model_payload(facts.table_name))

    diagnostics = analyze_table_warning_with_llm(facts, client=_mock_client(handler))

    assert len(calls) == 2
    assert diagnostics.inconclusive is False
    assert diagnostics.warnings[0].type == "unexpected_drop"


def test_mock_llm_times_out() -> None:
    facts = sample_facts()

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("request timed out")

    diagnostics = analyze_table_warning_with_llm(facts, client=_mock_client(handler))

    assert diagnostics.inconclusive is True
    assert diagnostics.warnings == []
    assert diagnostics.diagnostics_version == "llm.fallback.v1"
    assert diagnostics.observed_behavior == "llama-server request timed out."


def test_response_without_evidence_becomes_inconclusive() -> None:
    facts = sample_facts()

    def handler(_request: httpx.Request) -> httpx.Response:
        payload = _valid_model_payload(facts.table_name)
        payload["warnings"] = []
        payload["evidence"] = []
        payload["inconclusive"] = False
        return _completion_response(payload)

    diagnostics = analyze_table_warning_with_llm(facts, client=_mock_client(handler))

    assert diagnostics.inconclusive is True
    assert diagnostics.warnings == []
    assert "supporting evidence" in diagnostics.observed_behavior


def test_warning_without_existing_evidence_becomes_inconclusive() -> None:
    facts = sample_facts()

    def handler(_request: httpx.Request) -> httpx.Response:
        payload = _valid_model_payload(facts.table_name)
        payload["warnings"][0]["evidence_ids"] = ["missing.evidence"]
        return _completion_response(payload)

    diagnostics = analyze_table_warning_with_llm(facts, client=_mock_client(handler))

    assert diagnostics.inconclusive is True
    assert diagnostics.warnings == []
    assert "evidence that was not present" in diagnostics.observed_behavior


def _mock_client(handler) -> LlamaServerClient:
    config = LlamaServerConfig(
        base_url="http://llama-server-test:8080",
        model="qwen-test",
        temperature=0.2,
        timeout_seconds=3,
        max_output_tokens=128,
    )
    return LlamaServerClient(
        config=config,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _completion_response(payload: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "qwen-test",
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
