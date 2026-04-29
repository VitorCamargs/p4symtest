from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.models import TableWarningDiagnostics


client = TestClient(app)


def valid_payload() -> dict:
    return {
        "request_id": "req-001",
        "diagnostics_mode": "mock",
        "metadata": {},
        "facts": {
            "facts_version": "onda0.facts.v1",
            "analysis_id": "analysis-001",
            "pipeline": "ingress",
            "table_name": "MyIngress.ipv4_lpm",
            "switch_id": "s1",
            "input_snapshot": {
                "filename": "input.json",
                "state_count": 2,
            },
            "output_snapshot": {
                "filename": "output.json",
                "state_count": 2,
            },
            "state_summary": {
                "input_states": 2,
                "output_states": 2,
                "drop_states": 2,
                "field_updates": [
                    {
                        "field": "standard_metadata.egress_spec",
                        "summary": "All explored states were assigned the drop port.",
                    }
                ],
            },
            "runtime_entries": [
                {
                    "match": {"hdr.ipv4.dstAddr": "10.0.1.1/32"},
                    "action": "ipv4_forward",
                    "action_params": {"port": 1},
                }
            ],
            "topology_slice": {
                "switch": "s1",
                "ports": {"1": "h1", "2": "h2"},
            },
            "p4_slice": {
                "table_source": "table ipv4_lpm { actions = { ipv4_forward; drop; } }",
                "action_sources": [
                    "action ipv4_forward(bit<9> port) { standard_metadata.egress_spec = port; }",
                    "action drop() { mark_to_drop(standard_metadata); }",
                ],
            },
            "symbolic_facts": [
                {
                    "id": "drop-001",
                    "kind": "drop",
                    "summary": "All output states are marked as dropped.",
                }
            ],
            "log_summary": {
                "stdout_excerpt": "Applied table MyIngress.ipv4_lpm.",
                "stderr_excerpt": "",
            },
        },
    }


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_valid_request_returns_mock_diagnostics() -> None:
    response = client.post("/analyze/table-warning", json=valid_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["diagnostics_version"] == "onda0.mock.v1"
    assert body["table_name"] == "MyIngress.ipv4_lpm"
    assert body["inconclusive"] is False
    assert body["warnings"][0]["type"] == "unexpected_drop"
    assert body["model_info"]["provider"] == "mock"
    assert body["model_info"]["prompt_version"] == "mock-table-warning-v1"


def test_direct_facts_payload_returns_mock_diagnostics() -> None:
    response = client.post("/analyze/table-warning", json=valid_payload()["facts"])

    assert response.status_code == 200
    body = response.json()
    assert body["table_name"] == "MyIngress.ipv4_lpm"
    assert body["warnings"][0]["type"] == "unexpected_drop"


def test_invalid_request_fails_validation() -> None:
    payload = valid_payload()
    del payload["facts"]["table_name"]

    response = client.post("/analyze/table-warning", json=payload)

    assert response.status_code == 422


def test_response_follows_schema_intent() -> None:
    response = client.post("/analyze/table-warning", json=valid_payload())
    body = response.json()

    diagnostics = TableWarningDiagnostics.model_validate(body)
    assert set(diagnostics.model_dump().keys()) == {
        "diagnostics_version",
        "table_name",
        "expected_behavior",
        "observed_behavior",
        "warnings",
        "inconclusive",
        "evidence",
        "model_info",
        "rag_context_ids",
    }
    assert diagnostics.rag_context_ids == []
    assert diagnostics.model_info.model == "deterministic-table-warning"
    assert diagnostics.evidence


def test_inconclusive_mode_returns_inconclusive_true() -> None:
    payload = valid_payload()
    payload["diagnostics_mode"] = "mock_inconclusive"

    response = client.post("/analyze/table-warning", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["inconclusive"] is True
    assert body["warnings"] == []


def test_inconclusive_can_be_triggered_by_metadata() -> None:
    payload = valid_payload()
    payload["metadata"] = {"force_inconclusive": True}

    response = client.post("/analyze/table-warning", json=payload)

    assert response.status_code == 200
    assert response.json()["inconclusive"] is True


def test_every_warning_includes_existing_evidence() -> None:
    response = client.post("/analyze/table-warning", json=valid_payload())
    diagnostics = TableWarningDiagnostics.model_validate(response.json())
    evidence_ids = {item.id for item in diagnostics.evidence}

    assert diagnostics.warnings
    for warning in diagnostics.warnings:
        assert warning.evidence_ids
        assert set(warning.evidence_ids).issubset(evidence_ids)


def test_response_model_rejects_warning_without_evidence() -> None:
    body = client.post("/analyze/table-warning", json=valid_payload()).json()
    body["warnings"][0]["evidence_ids"] = []

    try:
        TableWarningDiagnostics.model_validate(body)
    except ValidationError:
        return

    raise AssertionError("warning without evidence should not validate")
