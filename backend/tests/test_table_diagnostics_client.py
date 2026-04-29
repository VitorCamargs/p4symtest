import json

from backend.table_diagnostics.analyzer_client import (
    request_table_diagnostics,
    table_diagnostics_enabled,
)


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.body


def minimal_facts():
    return {
        "table_name": "MyIngress.ipv4_lpm",
        "facts_version": "2026-04-llm-warning-v1",
    }


def enabled_env():
    return {
        "P4SYMTEST_TABLE_DIAGNOSTICS_ENABLED": "1",
        "P4SYMTEST_LLM_ANALYZER_URL": "http://llm-analyzer:8080",
        "P4SYMTEST_LLM_ANALYZER_TIMEOUT_SECONDS": "0.1",
    }


def test_analyzer_timeout_returns_diagnostics_unavailable_without_base_output_loss():
    base_output = {"output_states": [{"description": "base symbolic state"}]}

    def timeout_urlopen(request, timeout):
        raise TimeoutError("simulated timeout")

    diagnostics = request_table_diagnostics(
        minimal_facts(), env=enabled_env(), urlopen=timeout_urlopen
    )
    base_output["diagnostics"] = diagnostics

    assert base_output["output_states"] == [{"description": "base symbolic state"}]
    assert diagnostics["inconclusive"] is True
    assert diagnostics["model_info"]["model"] == "diagnostics_unavailable"
    assert "diagnostics_unavailable: timeout" in diagnostics["observed_behavior"]


def test_diagnostics_request_is_disabled_without_env_opt_in():
    assert table_diagnostics_enabled({}) is False
    assert request_table_diagnostics(minimal_facts(), env={}, urlopen=None) is None


def test_analyzer_error_returns_diagnostics_unavailable():
    def error_urlopen(request, timeout):
        raise OSError("connection refused")

    diagnostics = request_table_diagnostics(
        minimal_facts(), env=enabled_env(), urlopen=error_urlopen
    )

    assert diagnostics["inconclusive"] is True
    assert "diagnostics_unavailable: request_error" in diagnostics["observed_behavior"]


def test_analyzer_invalid_json_returns_diagnostics_unavailable():
    def invalid_json_urlopen(request, timeout):
        return FakeResponse(b"not-json")

    diagnostics = request_table_diagnostics(
        minimal_facts(), env=enabled_env(), urlopen=invalid_json_urlopen
    )

    assert diagnostics["inconclusive"] is True
    assert "diagnostics_unavailable: invalid_json" in diagnostics["observed_behavior"]


def test_analyzer_valid_payload_is_returned():
    payload = {
        "diagnostics_version": "2026-04-llm-warning-v1",
        "table_name": "MyIngress.ipv4_lpm",
        "expected_behavior": "expected",
        "observed_behavior": "observed",
        "warnings": [],
        "inconclusive": False,
        "evidence": [],
        "model_info": {
            "provider": "mock",
            "model": "mock",
            "prompt_version": "table-warning-v1",
        },
        "rag_context_ids": [],
    }

    def ok_urlopen(request, timeout):
        return FakeResponse(json.dumps(payload).encode("utf-8"))

    diagnostics = request_table_diagnostics(
        minimal_facts(), env=enabled_env(), urlopen=ok_urlopen
    )

    assert diagnostics == payload
