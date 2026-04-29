import hashlib
import json
import re
from pathlib import Path

FACTS_VERSION = "2026-04-llm-warning-v1"
DROP_PORT_VALUE = 511
DROP_PORT_BINARY = "#b111111111"
MAX_EXCERPT_CHARS = 1200
MAX_SUMMARY_VALUE_CHARS = 180


def build_table_analysis_facts(
    *,
    pipeline,
    table_name,
    switch_id,
    input_snapshot_filename,
    output_snapshot_filename,
    input_states,
    output_states,
    runtime_config=None,
    topology=None,
    fsm_data=None,
    p4_source_paths=None,
    stdout="",
    stderr="",
):
    input_states = input_states if isinstance(input_states, list) else []
    output_states = output_states if isinstance(output_states, list) else []
    runtime_config = runtime_config if isinstance(runtime_config, dict) else {}
    topology = topology if isinstance(topology, dict) else {}
    fsm_data = fsm_data if isinstance(fsm_data, dict) else {}

    runtime_entries = extract_runtime_entries(runtime_config, switch_id, table_name)
    topology_slice = extract_topology_slice(topology, switch_id, runtime_entries)
    p4_slice = extract_p4_slice(fsm_data, pipeline, table_name, p4_source_paths)
    field_updates = extract_field_updates(input_states, output_states)
    drop_states = count_drop_states(output_states, stdout=stdout)

    facts = {
        "facts_version": FACTS_VERSION,
        "analysis_id": _analysis_id(
            pipeline,
            switch_id,
            table_name,
            input_snapshot_filename,
            output_snapshot_filename,
        ),
        "pipeline": pipeline,
        "table_name": table_name,
        "switch_id": str(switch_id),
        "input_snapshot": {
            "filename": str(input_snapshot_filename),
            "state_count": len(input_states),
        },
        "output_snapshot": {
            "filename": str(output_snapshot_filename),
            "state_count": len(output_states),
        },
        "state_summary": {
            "input_states": len(input_states),
            "output_states": len(output_states),
            "drop_states": drop_states,
            "field_updates": field_updates,
        },
        "runtime_entries": runtime_entries,
        "topology_slice": topology_slice,
        "p4_slice": p4_slice,
        "symbolic_facts": build_symbolic_facts(
            input_count=len(input_states),
            output_count=len(output_states),
            drop_states=drop_states,
            field_updates=field_updates,
            runtime_entries=runtime_entries,
            topology_slice=topology_slice,
        ),
        "log_summary": {
            "stdout_excerpt": summarize_log(stdout),
            "stderr_excerpt": summarize_log(stderr),
        },
    }
    return facts


def extract_runtime_entries(runtime_config, switch_id, table_name):
    if not isinstance(runtime_config, dict):
        return []

    switch_runtime = runtime_config.get(switch_id)
    if not isinstance(switch_runtime, dict):
        switch_runtime = runtime_config.get(str(switch_id), {})
    if not isinstance(switch_runtime, dict):
        return []

    entries = None
    for candidate in _table_name_candidates(table_name):
        if candidate in switch_runtime:
            entries = switch_runtime.get(candidate)
            break
    if not isinstance(entries, list):
        return []

    relevant_entries = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        relevant_entries.append(
            {
                "match": entry.get("match", {}) if isinstance(entry.get("match", {}), dict) else {},
                "action": str(entry.get("action", "NoAction")),
                "action_params": (
                    entry.get("action_params", {})
                    if isinstance(entry.get("action_params", {}), dict)
                    else {}
                ),
            }
        )
    return relevant_entries


def extract_topology_slice(topology, switch_id, runtime_entries=None):
    if not isinstance(topology, dict):
        return {}

    runtime_entries = runtime_entries or []
    ports = _extract_switch_ports(topology, switch_id)
    if ports is None:
        return {}

    port_names = set(ports.keys())
    port_numbers = {str(value) for value in ports.values()}
    referenced_ports = _runtime_referenced_ports(runtime_entries)

    connected_hosts = {}
    for host_name, host_data in topology.get("hosts", {}).items():
        if not isinstance(host_data, dict):
            continue
        connection = host_data.get("conectado_a") or host_data.get("connected_to")
        if connection in port_names:
            connected_hosts[host_name] = {
                key: value
                for key, value in host_data.items()
                if key in {"ip", "mac", "conectado_a", "connected_to"}
            }

    links = []
    for link in topology.get("links", []):
        if not isinstance(link, dict):
            continue
        link_from = link.get("from") or link.get("source")
        link_to = link.get("to") or link.get("target")
        if link_from in port_names or link_to in port_names:
            links.append(link)

    return {
        "switch": str(switch_id),
        "ports": ports,
        "referenced_ports": sorted(referenced_ports & port_numbers),
        "connected_hosts": connected_hosts,
        "links": links,
    }


def extract_p4_slice(fsm_data, pipeline, table_name, p4_source_paths=None):
    table_def = _find_table_def(fsm_data, pipeline, table_name)
    if not table_def:
        return {"table_source": "", "action_sources": []}

    source_paths = _normalize_source_paths(p4_source_paths)
    table_source = _source_for_def(
        table_def,
        source_paths,
        kind="table",
        name=table_name.split(".")[-1],
    )
    action_sources = []
    for action_name in table_def.get("actions", []):
        action_def = _find_action_def(fsm_data, action_name)
        if not action_def:
            continue
        source = _source_for_def(
            action_def,
            source_paths,
            kind="action",
            name=action_name.split(".")[-1],
        )
        if not source:
            primitive_fragments = []
            for primitive in action_def.get("primitives", []):
                source_info = primitive.get("source_info", {})
                fragment = source_info.get("source_fragment")
                if fragment:
                    primitive_fragments.append(str(fragment))
            if primitive_fragments:
                source = f"{action_name}: " + "; ".join(primitive_fragments)
        if source:
            action_sources.append(source)

    return {"table_source": table_source, "action_sources": action_sources}


def extract_field_updates(input_states, output_states):
    updates_by_field = {}
    for index, output_state in enumerate(output_states):
        if not isinstance(output_state, dict):
            continue
        output_updates = output_state.get("field_updates", {})
        if not isinstance(output_updates, dict):
            continue
        input_updates = {}
        if index < len(input_states) and isinstance(input_states[index], dict):
            candidate = input_states[index].get("field_updates", {})
            if isinstance(candidate, dict):
                input_updates = candidate
        for field, value in output_updates.items():
            if input_updates.get(field) == value:
                continue
            bucket = updates_by_field.setdefault(field, {"count": 0, "examples": []})
            bucket["count"] += 1
            if len(bucket["examples"]) < 2:
                bucket["examples"].append(_short_value(value))

    summaries = []
    for field in sorted(updates_by_field):
        bucket = updates_by_field[field]
        plural = "state" if bucket["count"] == 1 else "states"
        example = "; ".join(bucket["examples"])
        summary = f"Updated in {bucket['count']} output {plural}."
        if example:
            summary = f"{summary} Example: {example}"
        summaries.append({"field": str(field), "summary": summary})
    return summaries


def count_drop_states(output_states, stdout=""):
    exact_drop_states = 0
    for state in output_states:
        if _state_has_exact_drop(state):
            exact_drop_states += 1

    log_drop_states = 0
    for line in (stdout or "").splitlines():
        normalized = line.lower()
        if "todos os pacotes deste estado" in normalized and "descart" in normalized:
            log_drop_states += 1
        elif "drop (sempre)" in normalized:
            log_drop_states += 1

    return max(exact_drop_states, log_drop_states)


def build_symbolic_facts(
    *,
    input_count,
    output_count,
    drop_states,
    field_updates,
    runtime_entries,
    topology_slice,
):
    facts = [
        {
            "id": "fact-reachability-001",
            "kind": "reachability",
            "summary": f"Table execution produced {output_count} output state(s) from {input_count} input state(s).",
        }
    ]
    if drop_states:
        facts.append(
            {
                "id": "fact-drop-001",
                "kind": "drop",
                "summary": f"{drop_states} state(s) indicate drop via standard_metadata.egress_spec or verifier logs.",
            }
        )
    for index, update in enumerate(field_updates, start=1):
        facts.append(
            {
                "id": f"fact-update-{index:03d}",
                "kind": "field_update",
                "summary": f"{update['field']}: {update['summary']}",
            }
        )
    if runtime_entries:
        facts.append(
            {
                "id": "fact-runtime-001",
                "kind": "runtime_match",
                "summary": f"{len(runtime_entries)} runtime entrie(s) match the selected switch and table.",
            }
        )
    if topology_slice:
        port_count = len(topology_slice.get("ports", {}))
        facts.append(
            {
                "id": "fact-topology-001",
                "kind": "topology",
                "summary": f"Topology slice for switch {topology_slice.get('switch')} includes {port_count} port(s).",
            }
        )
    return facts


def summarize_log(log_text):
    if not log_text:
        return ""
    lines = [line.strip() for line in str(log_text).splitlines() if line.strip()]
    interesting = [
        line
        for line in lines
        if any(
            token in line.lower()
            for token in ("aviso", "erro", "resultado", "drop", "descart", "alcan")
        )
    ]
    selected = interesting or lines
    excerpt = "\n".join(selected[:12])
    if len(excerpt) <= MAX_EXCERPT_CHARS:
        return excerpt
    return excerpt[: MAX_EXCERPT_CHARS - 3] + "..."


def _analysis_id(pipeline, switch_id, table_name, input_filename, output_filename):
    raw = "|".join(
        [str(pipeline), str(switch_id), str(table_name), str(input_filename), str(output_filename)]
    )
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    slug = re.sub(r"[^A-Za-z0-9]+", "-", f"{pipeline}-{switch_id}-{table_name}").strip("-")
    return f"{slug}-{digest}"


def _table_name_candidates(table_name):
    simple = str(table_name).split(".")[-1]
    return [str(table_name), simple]


def _extract_switch_ports(topology, switch_id):
    switches = topology.get("switches")
    if isinstance(switches, dict):
        switch_data = switches.get(switch_id) or switches.get(str(switch_id))
        if isinstance(switch_data, dict):
            ports = switch_data.get("portas") or switch_data.get("ports")
            if isinstance(ports, dict):
                return ports
    nodes = topology.get("nodes")
    if isinstance(nodes, dict):
        switch_data = nodes.get(switch_id) or nodes.get(str(switch_id))
        if isinstance(switch_data, dict):
            ports = switch_data.get("ports") or switch_data.get("portas")
            if isinstance(ports, dict):
                return ports
    return None


def _runtime_referenced_ports(runtime_entries):
    ports = set()
    for entry in runtime_entries:
        if not isinstance(entry, dict):
            continue
        candidates = []
        params = entry.get("action_params", {})
        if isinstance(params, dict):
            candidates.extend(params.items())
        match = entry.get("match", {})
        if isinstance(match, dict):
            candidates.extend(match.items())
        for key, value in candidates:
            if "port" in str(key).lower() or "egress" in str(key).lower():
                ports.add(str(value))
    return ports


def _state_has_exact_drop(state):
    if not isinstance(state, dict):
        return False

    updates = state.get("field_updates", {})
    if isinstance(updates, dict):
        for key in ("standard_metadata.egress_spec", "standard_metadata.egress_port"):
            if _is_exact_drop_value(updates.get(key)):
                return True

    constraints = state.get("z3_constraints_smt2", [])
    if isinstance(constraints, list):
        for constraint in constraints:
            text = str(constraint).strip()
            if _constraint_sets_drop(text):
                return True
    return False


def _is_exact_drop_value(value):
    if value is None:
        return False
    if isinstance(value, int):
        return value == DROP_PORT_VALUE
    text = str(value).strip().lower()
    if text in {"511", "0x1ff", "#x1ff", DROP_PORT_BINARY}:
        return True
    if text in {"#b" + "1" * 9, "(_ bv511 9)"}:
        return True
    return False


def _constraint_sets_drop(text):
    normalized = re.sub(r"\s+", " ", text.lower())
    drop_tokens = (DROP_PORT_BINARY, "#x1ff", "511", "(_ bv511 9)")
    if "standard_metadata.egress_spec" not in normalized:
        return False
    if not normalized.startswith("(="):
        return False
    return any(token in normalized for token in drop_tokens)


def _short_value(value):
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= MAX_SUMMARY_VALUE_CHARS:
        return text
    return text[: MAX_SUMMARY_VALUE_CHARS - 3] + "..."


def _find_table_def(fsm_data, pipeline, table_name):
    if not isinstance(fsm_data, dict):
        return None
    for pipeline_def in fsm_data.get("pipelines", []):
        if pipeline and pipeline_def.get("name") != pipeline:
            continue
        for table_def in pipeline_def.get("tables", []):
            if table_def.get("name") in _table_name_candidates(table_name):
                return table_def
    for pipeline_def in fsm_data.get("pipelines", []):
        for table_def in pipeline_def.get("tables", []):
            if table_def.get("name") in _table_name_candidates(table_name):
                return table_def
    return None


def _find_action_def(fsm_data, action_name):
    if not isinstance(fsm_data, dict):
        return None
    for action_def in fsm_data.get("actions", []):
        if action_def.get("name") == action_name:
            return action_def
    return None


def _normalize_source_paths(p4_source_paths):
    if p4_source_paths is None:
        return []
    if isinstance(p4_source_paths, (str, Path)):
        candidates = [p4_source_paths]
    else:
        candidates = list(p4_source_paths)
    normalized = []
    for candidate in candidates:
        if candidate:
            normalized.append(Path(candidate))
    return normalized


def _source_for_def(definition, source_paths, *, kind, name):
    source_info = definition.get("source_info", {}) if isinstance(definition, dict) else {}
    line = source_info.get("line")
    filename = source_info.get("filename")
    candidates = list(source_paths)
    if filename:
        candidates.append(Path(filename))
        candidates.append(Path(filename).name)

    for candidate in candidates:
        path = Path(candidate)
        if not path.exists() or not path.is_file():
            continue
        source = _slice_from_source_file(path, line, kind, name)
        if source:
            return source

    fragment = source_info.get("source_fragment")
    return str(fragment) if fragment else ""


def _slice_from_source_file(path, line, kind, name):
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return ""
    if not lines:
        return ""

    if isinstance(line, int) and line > 0:
        start = max(0, line - 20)
        end = min(len(lines), line + 40)
    else:
        start = 0
        end = len(lines)

    pattern = re.compile(rf"\b{re.escape(kind)}\s+{re.escape(name)}\b")
    anchor = None
    for idx in range(start, end):
        if pattern.search(lines[idx]):
            anchor = idx
            break
    if anchor is None:
        return ""

    collected = []
    depth = 0
    seen_open = False
    for idx in range(anchor, min(len(lines), anchor + 100)):
        line_text = lines[idx]
        collected.append(line_text.rstrip())
        depth += line_text.count("{")
        if "{" in line_text:
            seen_open = True
        depth -= line_text.count("}")
        if seen_open and depth <= 0:
            break
    return "\n".join(collected).strip()
