import json
from pathlib import Path

from backend.table_diagnostics.extractor import (
    build_table_analysis_facts,
    count_drop_states,
    extract_field_updates,
    extract_p4_slice,
    extract_runtime_entries,
    extract_topology_slice,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def build_facts(pipeline="ingress"):
    runtime_config = load_fixture("runtime_config.json")
    topology = load_fixture("topology.json")
    fsm_data = load_fixture("fsm.json")
    if pipeline == "ingress":
        return build_table_analysis_facts(
            pipeline="ingress",
            table_name="MyIngress.ipv4_lpm",
            switch_id="s1",
            input_snapshot_filename="ingress_input.json",
            output_snapshot_filename="ingress_output.json",
            input_states=load_fixture("ingress_input.json"),
            output_states=load_fixture("ingress_output.json"),
            runtime_config=runtime_config,
            topology=topology,
            fsm_data=fsm_data,
            p4_source_paths=[FIXTURES / "program.p4"],
            stdout="",
            stderr="",
        )
    return build_table_analysis_facts(
        pipeline="egress",
        table_name="MyEgress.egress_port_smac",
        switch_id="s1",
        input_snapshot_filename="egress_input.json",
        output_snapshot_filename="egress_output.json",
        input_states=load_fixture("egress_input.json"),
        output_states=load_fixture("egress_output.json"),
        runtime_config=runtime_config,
        topology=topology,
        fsm_data=fsm_data,
        p4_source_paths=[FIXTURES / "program.p4"],
        stdout="",
        stderr="",
    )


def test_extractor_builds_ingress_facts_from_fixture():
    facts = build_facts("ingress")

    assert facts["pipeline"] == "ingress"
    assert facts["table_name"] == "MyIngress.ipv4_lpm"
    assert facts["input_snapshot"]["state_count"] == 2
    assert facts["output_snapshot"]["state_count"] == 2
    assert facts["runtime_entries"][0]["action"] == "MyIngress.ipv4_forward"
    assert "table ipv4_lpm" in facts["p4_slice"]["table_source"]
    assert any("ipv4_forward" in source for source in facts["p4_slice"]["action_sources"])


def test_extractor_builds_egress_facts_from_fixture():
    facts = build_facts("egress")

    assert facts["pipeline"] == "egress"
    assert facts["table_name"] == "MyEgress.egress_port_smac"
    assert facts["runtime_entries"][0]["action"] == "MyEgress.rewrite_src_mac"
    assert any(
        update["field"] == "ethernet.srcAddr"
        for update in facts["state_summary"]["field_updates"]
    )
    assert "table egress_port_smac" in facts["p4_slice"]["table_source"]


def test_drop_detection_uses_exact_egress_spec_and_log_heuristic():
    output_states = [
        {
            "field_updates": {
                "standard_metadata.egress_spec": "#b111111111"
            }
        }
    ]
    assert count_drop_states(output_states) == 1

    stdout = "  -> AVISO: Todos os pacotes deste estado sao descartados."
    assert count_drop_states([], stdout=stdout) == 1


def test_field_delta_reports_changed_output_updates():
    input_states = [
        {
            "field_updates": {
                "ethernet.dstAddr": "#x01"
            }
        }
    ]
    output_states = [
        {
            "field_updates": {
                "ethernet.dstAddr": "#x02",
                "standard_metadata.egress_spec": "#b000000001"
            }
        }
    ]

    updates = extract_field_updates(input_states, output_states)
    fields = {update["field"]: update["summary"] for update in updates}

    assert "ethernet.dstAddr" in fields
    assert "standard_metadata.egress_spec" in fields
    assert "1 output state" in fields["ethernet.dstAddr"]


def test_runtime_filtering_uses_switch_and_table():
    runtime_config = load_fixture("runtime_config.json")

    entries = extract_runtime_entries(runtime_config, "s1", "MyIngress.ipv4_lpm")

    assert len(entries) == 1
    assert entries[0]["action"] == "MyIngress.ipv4_forward"
    assert entries[0]["action_params"]["port"] == "1"


def test_topology_slice_keeps_switch_ports_hosts_and_links():
    topology = load_fixture("topology.json")
    runtime_entries = extract_runtime_entries(
        load_fixture("runtime_config.json"), "s1", "MyIngress.ipv4_lpm"
    )

    topology_slice = extract_topology_slice(topology, "s1", runtime_entries)

    assert topology_slice["switch"] == "s1"
    assert topology_slice["ports"] == {"s1-eth1": 1, "s1-eth2": 2}
    assert topology_slice["referenced_ports"] == ["1"]
    assert "h1" in topology_slice["connected_hosts"]
    assert topology_slice["links"] == [{"from": "s1-eth2", "to": "s2-eth1"}]


def test_topology_slice_uses_egress_port_match_when_available():
    topology = load_fixture("topology.json")
    runtime_entries = extract_runtime_entries(
        load_fixture("runtime_config.json"), "s1", "MyEgress.egress_port_smac"
    )

    topology_slice = extract_topology_slice(topology, "s1", runtime_entries)

    assert topology_slice["referenced_ports"] == ["1"]


def test_p4_slice_falls_back_to_safe_empty_values():
    p4_slice = extract_p4_slice({}, "ingress", "Missing.table", [])

    assert p4_slice == {"table_source": "", "action_sources": []}
