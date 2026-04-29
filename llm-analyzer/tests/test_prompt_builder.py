from app.models import TableAnalysisFacts
from app.prompt_builder import RagChunk, build_table_warning_prompt


RAW_SNAPSHOT_SENTINEL = "RAW_SNAPSHOT_SHOULD_NOT_APPEAR_IN_PROMPT"


def sample_facts() -> TableAnalysisFacts:
    return TableAnalysisFacts.model_validate(
        {
            "facts_version": "onda0.facts.v1",
            "analysis_id": "analysis-llm-001",
            "pipeline": "ingress",
            "table_name": "MyIngress.ipv4_lpm",
            "switch_id": "s1",
            "input_snapshot": {
                "filename": "input.json",
                "state_count": 3,
            },
            "output_snapshot": {
                "filename": "output.json",
                "state_count": 3,
            },
            "state_summary": {
                "input_states": 3,
                "output_states": 3,
                "drop_states": 3,
                "field_updates": [
                    {
                        "field": "standard_metadata.egress_spec",
                        "summary": "All states were assigned the drop port.",
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
                "table_source": "table ipv4_lpm { key = { hdr.ipv4.dstAddr: lpm; } }",
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
        }
    )


def test_prompt_contains_facts_and_chunks() -> None:
    facts = sample_facts()
    chunk = RagChunk(
        source_id="p4-spec-table-001",
        title="P4 table application",
        source_type="p4_spec",
        citation="P4-16 spec section 12",
        version="1.2.4",
        text="A table applies one selected action based on its key and entries.",
        score=0.91,
    )

    prompt = build_table_warning_prompt(facts, [chunk])
    prompt_text = "\n".join(message["content"] for message in prompt.messages)

    assert prompt.prompt_version == "table-warning-json-v1"
    assert prompt.rag_context_ids == ["p4-spec-table-001"]
    assert "MyIngress.ipv4_lpm" in prompt_text
    assert "All output states are marked as dropped." in prompt_text
    assert "A table applies one selected action" in prompt_text
    assert "Return exactly one JSON object" in prompt_text


def test_prompt_excludes_large_raw_snapshot_fields() -> None:
    facts = sample_facts()
    object.__setattr__(facts, "raw_snapshot_payload", RAW_SNAPSHOT_SENTINEL)

    prompt = build_table_warning_prompt(facts)
    prompt_text = "\n".join(message["content"] for message in prompt.messages)

    assert "input.json" in prompt_text
    assert "output.json" in prompt_text
    assert RAW_SNAPSHOT_SENTINEL not in prompt_text
    assert "raw_snapshot_payload" not in prompt_text
