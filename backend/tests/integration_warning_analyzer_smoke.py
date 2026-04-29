import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
for candidate in (REPO_ROOT, BACKEND_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

try:
    from backend.table_diagnostics import (
        build_table_analysis_facts,
        request_table_diagnostics,
    )
except ModuleNotFoundError:
    from table_diagnostics import (
        build_table_analysis_facts,
        request_table_diagnostics,
    )


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def build_smoke_facts():
    return build_table_analysis_facts(
        pipeline="ingress",
        table_name="MyIngress.ipv4_lpm",
        switch_id="s1",
        input_snapshot_filename="ingress_input.json",
        output_snapshot_filename="ingress_output.json",
        input_states=load_fixture("ingress_input.json"),
        output_states=load_fixture("ingress_output.json"),
        runtime_config=load_fixture("runtime_config.json"),
        topology=load_fixture("topology.json"),
        fsm_data=load_fixture("fsm.json"),
        p4_source_paths=[FIXTURES / "program.p4"],
        stdout="Applied table MyIngress.ipv4_lpm.",
        stderr="",
    )


def main():
    env = dict(os.environ)
    env["P4SYMTEST_TABLE_DIAGNOSTICS_ENABLED"] = "1"
    env.setdefault("P4SYMTEST_LLM_ANALYZER_URL", "http://localhost:8000")
    env.setdefault("P4SYMTEST_LLM_ANALYZER_TIMEOUT_SECONDS", "5")

    diagnostics = request_table_diagnostics(build_smoke_facts(), env=env)
    if diagnostics is None:
        raise AssertionError("diagnostics must be returned when analyzer is enabled")

    assert diagnostics["diagnostics_version"] == "onda0.mock.v1"
    assert diagnostics["table_name"] == "MyIngress.ipv4_lpm"
    assert diagnostics["model_info"]["provider"] == "mock"
    assert diagnostics["model_info"]["model"] == "deterministic-table-warning"
    assert isinstance(diagnostics["warnings"], list)
    assert diagnostics["evidence"]
    assert diagnostics["rag_context_ids"] == []

    print(
        json.dumps(
            {
                "status": "ok",
                "table_name": diagnostics["table_name"],
                "provider": diagnostics["model_info"]["provider"],
                "warning_count": len(diagnostics["warnings"]),
                "evidence_count": len(diagnostics["evidence"]),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"integration_warning_analyzer_smoke failed: {exc}", file=sys.stderr)
        raise
