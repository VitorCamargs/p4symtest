#!/usr/bin/env python3
"""
Unified interactive menu for P4SymTest benchmarks.

This script should run inside the backend container (p4symtest-backend).
Results are saved in /app/workspace/benchmark_runs.
"""

from __future__ import annotations

import csv
import concurrent.futures
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence, Tuple

from synthetic_p4_generator import SyntheticP4Generator


WORKSPACE_DIR = Path("/app/workspace")
RUN_SCRIPTS_DIR = WORKSPACE_DIR
OUTPUT_ROOT = WORKSPACE_DIR / "benchmark_runs"
CLI_DIR = Path(__file__).resolve().parent
P4C_BIN = Path("/usr/local/bin/p4c")
SWITCH_ID = "s1"

RUN_PARSER = RUN_SCRIPTS_DIR / "run_parser.py"
RUN_TABLE = RUN_SCRIPTS_DIR / "run_table.py"
RUN_TABLE_EGRESS = RUN_SCRIPTS_DIR / "run_table_egress.py"
RUN_DEPARSER = RUN_SCRIPTS_DIR / "run_deparser.py"
RUN_TABLE_WITH_CACHE = RUN_SCRIPTS_DIR / "run_table_with_cache.py"

BENCH_EXHAUSTIVE_DIR = Path("/app/benchmark_exhaustive")
DEPARSE_OPTIMIZER_MODULE = BENCH_EXHAUSTIVE_DIR / "deparser_optimizer.py"
TABLE_CACHE_MODULE = BENCH_EXHAUSTIVE_DIR / "table_execution_cache.py"

PLOT_PARSER = CLI_DIR / "plot_parser_graph.py"
PLOT_TABLES = CLI_DIR / "plot_tables_graph.py"
PLOT_DEPARSER = CLI_DIR / "plot_deparser_graph.py"
PLOT_FULL = CLI_DIR / "plot_full_graph.py"

STAGE_TIMEOUT_S = 300


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
        return value if value >= minimum else default
    except ValueError:
        return default


COMPACT_LOGS = _env_flag("P4SYMTEST_BENCH_COMPACT_LOGS", True)
HEARTBEAT_ENABLED = _env_flag("P4SYMTEST_BENCH_HEARTBEAT", True)
HEARTBEAT_INTERVAL_S = _env_int("P4SYMTEST_BENCH_HEARTBEAT_INTERVAL_S", 60, minimum=5)


def now_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def build_range(start: int, end: int, step: int) -> List[int]:
    if step <= 0:
        raise ValueError("step must be > 0")
    if end < start:
        raise ValueError("end must be >= start")
    return list(range(start, end + 1, step))


def format_elapsed(total_seconds: float) -> str:
    total_seconds = max(0.0, float(total_seconds))
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds - (hours * 3600) - (minutes * 60)
    if hours > 0:
        return f"{hours}h {minutes}m {seconds:.1f}s"
    if minutes > 0:
        return f"{minutes}m {seconds:.1f}s"
    return f"{seconds:.3f}s"


def ask_int(prompt: str, default: int, minimum: int = 1) -> int:
    while True:
        raw = input(f"{prompt} [{default}]: ").strip()
        if not raw:
            return default
        try:
            value = int(raw)
            if value < minimum:
                print(f"  Invalid value: must be >= {minimum}.")
                continue
            return value
        except ValueError:
            print("  Invalid value: enter an integer.")


def ask_choice(prompt: str, options: Dict[str, str], default: str) -> str:
    labels = " | ".join([f"{key}={label}" for key, label in options.items()])
    while True:
        raw = input(f"{prompt} ({labels}) [{default}]: ").strip()
        if not raw:
            raw = default
        if raw in options:
            return raw
        print("  Invalid option.")


def ensure_required_paths() -> None:
    missing = [p for p in [P4C_BIN, RUN_PARSER, RUN_TABLE, RUN_TABLE_EGRESS, RUN_DEPARSER] if not p.exists()]
    if missing:
        print("Error: required scripts/dependencies were not found in the container:")
        for item in missing:
            print(f"  - {item}")
        sys.exit(1)


def run_command(cmd: Sequence[str], cwd: Path | None = None, timeout: int = 1800) -> Tuple[bool, float, str]:
    return run_command_with_heartbeat(cmd=cmd, cwd=cwd, timeout=timeout, heartbeat_label=None)


def run_command_with_heartbeat(
    cmd: Sequence[str],
    cwd: Path | None = None,
    timeout: int = 1800,
    heartbeat_label: str | None = None,
    heartbeat_interval_s: int = 20,
    env: Dict[str, str] | None = None,
    discard_stdout: bool = True,
) -> Tuple[bool, float, str]:
    start = time.time()
    try:
        proc = subprocess.Popen(
            list(cmd),
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.DEVNULL if discard_stdout else subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=env,
        )
    except Exception as exc:  # pragma: no cover
        return False, time.time() - start, f"Exception: {exc}"

    try:
        while True:
            elapsed = time.time() - start
            remaining = timeout - elapsed
            if remaining <= 0:
                proc.kill()
                proc.communicate()
                return False, time.time() - start, f"Timeout after {timeout}s"

            heartbeat_active = HEARTBEAT_ENABLED and bool(heartbeat_label)
            wait_timeout = min(max(1, heartbeat_interval_s), remaining) if heartbeat_active else remaining

            try:
                out, err = proc.communicate(timeout=wait_timeout)
                duration = time.time() - start
                ok = proc.returncode == 0
                err_text = (err or "").strip()
                out_text = (out or "").strip()
                if ok:
                    return True, duration, ""
                return False, duration, (err_text if err_text else out_text)[:1200]
            except subprocess.TimeoutExpired:
                if heartbeat_active:
                    print(f"      ... {heartbeat_label} still running ({time.time() - start:.1f}s)")
                continue
    except Exception as exc:  # pragma: no cover
        try:
            proc.kill()
            proc.communicate()
        except Exception:
            pass
        return False, time.time() - start, f"Exception: {exc}"


def json_list_size(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return len(data) if isinstance(data, list) else 0
    except Exception:
        return 0


def write_csv(rows: List[Dict], output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        with output_file.open("w", encoding="utf-8", newline="") as f:
            f.write("")
        return

    # Field order based on first row; append any late keys at the end.
    ordered_fields = list(rows[0].keys())
    all_fields = set(ordered_fields)
    for row in rows[1:]:
        for key in row.keys():
            if key not in all_fields:
                ordered_fields.append(key)
                all_fields.add(key)

    with output_file.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ordered_fields)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(rows: List[Dict], output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    total = len(rows)
    success = sum(1 for row in rows if row.get("success"))
    failed = total - success
    avg_duration = sum(float(row.get("duration_s", 0.0)) for row in rows) / total if total else 0.0
    summary = {
        "total_runs": total,
        "success_runs": success,
        "failed_runs": failed,
        "avg_duration_s": round(avg_duration, 6),
    }
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)


class BenchmarkMenuRunner:
    def __init__(self) -> None:
        ensure_required_paths()
        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        # Silence helper module prints (TableOptimizer/DeparserOptimizer) to reduce stdout overhead.
        os.environ["P4SYMTEST_BENCH_QUIET"] = "1"
        self.compact_logs = COMPACT_LOGS
        self.generator = SyntheticP4Generator(seed=42)
        self._optimized_helpers_checked = False
        self._optimized_helpers_available = False
        self._optimize_and_process_deparser: Callable[[List[Dict], Path, int], Tuple[Path, Dict[str, Any]]] | None = None
        self._expand_deparser_results: Callable[[Path, Dict[str, Any], Path, int], Path] | None = None
        self._table_execution_cache_cls: Any | None = None
        self._optimize_table_input: Any = None
        self._optimized_table_caches: Dict[str, Any] = {}
        self._table_cache_dir = WORKSPACE_DIR / ".table_cache"
        self._table_cache_dir.mkdir(parents=True, exist_ok=True)

    def _vprint(self, msg: str) -> None:
        if not self.compact_logs:
            print(msg)

    def _load_optimized_helpers(self) -> bool:
        if self._optimized_helpers_checked:
            return self._optimized_helpers_available

        self._optimized_helpers_checked = True

        if not DEPARSE_OPTIMIZER_MODULE.exists():
            print(f"[WARN] Optimized mode unavailable: module not found: {DEPARSE_OPTIMIZER_MODULE}")
            return False
        if not TABLE_CACHE_MODULE.exists():
            print(f"[WARN] Optimized mode unavailable: module not found: {TABLE_CACHE_MODULE}")
            return False

        if str(BENCH_EXHAUSTIVE_DIR) not in sys.path:
            sys.path.append(str(BENCH_EXHAUSTIVE_DIR))

        try:
            from deparser_optimizer import expand_deparser_results, optimize_and_process_deparser
            from table_execution_cache import TableExecutionCache, optimize_table_input

            self._optimize_and_process_deparser = optimize_and_process_deparser
            self._expand_deparser_results = expand_deparser_results
            self._table_execution_cache_cls = TableExecutionCache
            self._optimize_table_input = optimize_table_input
            self._optimized_helpers_available = True
            return True
        except Exception as exc:
            print(f"[WARN] Could not load optimized-mode helpers: {exc}")
            return False

    def _get_table_cache(self, table_name: str, run_number: int) -> Any:
        if self._table_execution_cache_cls is None:
            raise RuntimeError("optimized table cache helper is unavailable")
        cache_key = f"{table_name}_run{run_number}"
        if cache_key not in self._optimized_table_caches:
            cache_file = self._table_cache_dir / f"{cache_key}.json"
            self._optimized_table_caches[cache_key] = self._table_execution_cache_cls(cache_file)
        return self._optimized_table_caches[cache_key]

    def _optimized_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        extra = str(BENCH_EXHAUSTIVE_DIR)
        if existing:
            env["PYTHONPATH"] = f"{extra}:{existing}"
        else:
            env["PYTHONPATH"] = extra
        return env

    def _ensure_table_cache_class(self) -> bool:
        if self._table_execution_cache_cls is not None:
            return True
        if str(BENCH_EXHAUSTIVE_DIR) not in sys.path:
            sys.path.append(str(BENCH_EXHAUSTIVE_DIR))
        try:
            from table_execution_cache import TableExecutionCache, optimize_table_input

            self._table_execution_cache_cls = TableExecutionCache
            if self._optimize_table_input is None:
                self._optimize_table_input = optimize_table_input
            return True
        except Exception:
            return False

    def _compile(self, p4_file: Path, build_dir: Path) -> Tuple[bool, float, str, Path]:
        build_dir.mkdir(parents=True, exist_ok=True)
        cmd = [str(P4C_BIN), "--target", "bmv2", "--arch", "v1model", "-o", str(build_dir), str(p4_file)]
        ok, duration, err = run_command(cmd, cwd=p4_file.parent, timeout=STAGE_TIMEOUT_S)
        fsm_file = build_dir / f"{p4_file.stem}.json"
        if ok and not fsm_file.exists():
            return False, duration, f"FSM output not found: {fsm_file}", fsm_file
        return ok, duration, err, fsm_file

    def _run_parser(
        self, fsm_file: Path, output_file: Path, heartbeat_label: str | None = None
    ) -> Tuple[bool, float, str]:
        cmd = ["python3", str(RUN_PARSER), str(fsm_file), str(output_file)]
        return run_command_with_heartbeat(
            cmd,
            cwd=RUN_SCRIPTS_DIR,
            timeout=STAGE_TIMEOUT_S,
            heartbeat_label=heartbeat_label,
            heartbeat_interval_s=HEARTBEAT_INTERVAL_S,
        )

    def _run_ingress_table(
        self,
        fsm_file: Path,
        topology_file: Path,
        runtime_file: Path,
        input_states: Path,
        table_name: str,
        output_file: Path,
        heartbeat_label: str | None = None,
    ) -> Tuple[bool, float, str]:
        cmd = [
            "python3",
            str(RUN_TABLE),
            str(fsm_file),
            str(topology_file),
            str(runtime_file),
            str(input_states),
            SWITCH_ID,
            table_name,
            str(output_file),
        ]
        return run_command_with_heartbeat(
            cmd,
            cwd=RUN_SCRIPTS_DIR,
            timeout=STAGE_TIMEOUT_S,
            heartbeat_label=heartbeat_label,
            heartbeat_interval_s=HEARTBEAT_INTERVAL_S,
        )

    def _run_ingress_table_cached(
        self,
        fsm_file: Path,
        topology_file: Path,
        runtime_file: Path,
        input_states: Path,
        table_name: str,
        output_file: Path,
        cache_file: Path,
        heartbeat_label: str | None = None,
    ) -> Tuple[bool, float, str]:
        cmd = [
            "python3",
            str(RUN_TABLE_WITH_CACHE),
            str(fsm_file),
            str(topology_file),
            str(runtime_file),
            str(input_states),
            SWITCH_ID,
            table_name,
            str(output_file),
            str(cache_file),
        ]
        return run_command_with_heartbeat(
            cmd,
            cwd=RUN_SCRIPTS_DIR,
            timeout=STAGE_TIMEOUT_S,
            heartbeat_label=heartbeat_label,
            heartbeat_interval_s=HEARTBEAT_INTERVAL_S,
            env=self._optimized_env(),
        )

    def _run_ingress_table_cached_legacy(
        self,
        *,
        fsm_file: Path,
        topology_file: Path,
        runtime_file: Path,
        input_states: Path,
        table_name: str,
        output_file: Path,
        run_number: int,
        fsm_data: Dict[str, Any] | None = None,
    ) -> Tuple[bool, float, str]:
        start = time.time()
        if self._optimize_table_input is None:
            return False, 0.0, "optimized cache helpers are unavailable"

        try:
            if fsm_data is None:
                with fsm_file.open("r", encoding="utf-8") as f:
                    fsm_data = json.load(f)

            with input_states.open("r", encoding="utf-8") as f:
                original_states = json.load(f)
            if not isinstance(original_states, list):
                original_states = []

            if not original_states:
                output_file.parent.mkdir(parents=True, exist_ok=True)
                with output_file.open("w", encoding="utf-8") as f:
                    json.dump([], f)
                return True, time.time() - start, ""

            cache = self._get_table_cache(table_name, run_number)

            pipeline_name = "ingress" if "ingress" in table_name.lower() else "egress"
            pipeline = next((p for p in fsm_data.get("pipelines", []) if p.get("name") == pipeline_name), None)
            if pipeline is None:
                return self._run_ingress_table(
                    fsm_file=fsm_file,
                    topology_file=topology_file,
                    runtime_file=runtime_file,
                    input_states=input_states,
                    table_name=table_name,
                    output_file=output_file,
                    heartbeat_label=None,
                )

            table_def = next((t for t in pipeline.get("tables", []) if t.get("name") == table_name), None)
            if table_def is None:
                return self._run_ingress_table(
                    fsm_file=fsm_file,
                    topology_file=topology_file,
                    runtime_file=runtime_file,
                    input_states=input_states,
                    table_name=table_name,
                    output_file=output_file,
                    heartbeat_label=None,
                )

            cached_results: List[Tuple[int, Dict[str, Any]]] = []
            states_to_process: List[Tuple[int, Dict[str, Any]]] = []
            for idx, state in enumerate(original_states):
                hit, cached_result = cache.lookup(state, table_name, table_def, fsm_data)
                if hit:
                    cached_results.append((idx, cached_result))
                else:
                    states_to_process.append((idx, state))

            if not states_to_process:
                final_results: List[Dict[str, Any]] = []
                cache_map = {idx: res for idx, res in cached_results}
                for idx, state in enumerate(original_states):
                    cached = cache_map.get(idx)
                    if cached:
                        result = state.copy()
                        result["field_updates"] = cached.get("field_updates", result.get("field_updates", {}))
                        result["z3_constraints_smt2"] = cached.get(
                            "new_constraints",
                            result.get("z3_constraints_smt2", []),
                        )
                        result["was_cached"] = True
                        final_results.append(result)
                    else:
                        final_results.append(state)
                output_file.parent.mkdir(parents=True, exist_ok=True)
                with output_file.open("w", encoding="utf-8") as f:
                    json.dump(final_results, f, indent=2)
                return True, time.time() - start, ""

            states_only = [s for _, s in states_to_process]
            unique_states, index_mapping = self._optimize_table_input(
                states_only, table_name, table_def, fsm_data, cache
            )

            tmp_tag = uuid.uuid4().hex
            temp_input = input_states.parent / f".temp_{table_name}_{tmp_tag}_{input_states.name}"
            temp_output = output_file.parent / f".temp_{table_name}_{tmp_tag}_{output_file.name}"
            with temp_input.open("w", encoding="utf-8") as f:
                json.dump(unique_states, f)

            ok, _, err = self._run_ingress_table(
                fsm_file=fsm_file,
                topology_file=topology_file,
                runtime_file=runtime_file,
                input_states=temp_input,
                table_name=table_name,
                output_file=temp_output,
                heartbeat_label=None,
            )
            if not ok:
                temp_input.unlink(missing_ok=True)
                temp_output.unlink(missing_ok=True)
                return False, time.time() - start, err

            with temp_output.open("r", encoding="utf-8") as f:
                processed_results = json.load(f)

            hash_to_result: Dict[str, Dict[str, Any]] = {}
            for idx, state in enumerate(unique_states):
                if idx < len(processed_results):
                    result = processed_results[idx]
                    state_hash = cache._compute_table_state_hash(
                        state, table_name, cache.table_relevant_fields[table_name]
                    )
                    hash_to_result[state_hash] = result
                    cache.store(state, result, table_name, table_def, fsm_data)

            full_results: List[Dict[str, Any]] = []
            processed_idx_map = {states_to_process[i][0]: i for i in range(len(states_to_process))}
            for orig_idx, state in enumerate(original_states):
                cached = next((r for i, r in cached_results if i == orig_idx), None)
                if cached:
                    result = state.copy()
                    result["field_updates"] = cached.get("field_updates", result.get("field_updates", {}))
                    result["z3_constraints_smt2"] = cached.get("new_constraints", result.get("z3_constraints_smt2", []))
                    result["was_cached"] = True
                else:
                    proc_idx = processed_idx_map.get(orig_idx)
                    if proc_idx is not None:
                        state_hash = index_mapping.get(proc_idx)
                        result = hash_to_result.get(state_hash, state).copy()
                        result["description"] = state.get("description", "Unknown")
                        result["was_cached"] = False
                    else:
                        result = state
                full_results.append(result)

            output_file.parent.mkdir(parents=True, exist_ok=True)
            with output_file.open("w", encoding="utf-8") as f:
                json.dump(full_results, f, indent=2)

            temp_input.unlink(missing_ok=True)
            temp_output.unlink(missing_ok=True)
            cache.save_cache()
            return True, time.time() - start, ""
        except Exception as exc:
            return False, time.time() - start, str(exc)

    def _run_egress_table_cached_legacy(
        self,
        *,
        fsm_file: Path,
        runtime_file: Path,
        input_states: Path,
        table_name: str,
        output_file: Path,
        run_number: int,
        fsm_data: Dict[str, Any] | None = None,
    ) -> Tuple[bool, float, str]:
        start = time.time()
        if self._optimize_table_input is None:
            return False, 0.0, "optimized cache helpers are unavailable"

        try:
            if fsm_data is None:
                with fsm_file.open("r", encoding="utf-8") as f:
                    fsm_data = json.load(f)

            with input_states.open("r", encoding="utf-8") as f:
                original_states = json.load(f)
            if not isinstance(original_states, list):
                original_states = []

            if not original_states:
                output_file.parent.mkdir(parents=True, exist_ok=True)
                with output_file.open("w", encoding="utf-8") as f:
                    json.dump([], f)
                return True, time.time() - start, ""

            cache = self._get_table_cache(table_name, run_number)

            pipeline = next((p for p in fsm_data.get("pipelines", []) if p.get("name") == "egress"), None)
            if pipeline is None:
                return self._run_egress_table(
                    fsm_file=fsm_file,
                    runtime_file=runtime_file,
                    input_states=input_states,
                    table_name=table_name,
                    output_file=output_file,
                    heartbeat_label=None,
                )

            table_def = next((t for t in pipeline.get("tables", []) if t.get("name") == table_name), None)
            if table_def is None:
                return self._run_egress_table(
                    fsm_file=fsm_file,
                    runtime_file=runtime_file,
                    input_states=input_states,
                    table_name=table_name,
                    output_file=output_file,
                    heartbeat_label=None,
                )

            cached_results: List[Tuple[int, Dict[str, Any]]] = []
            states_to_process: List[Tuple[int, Dict[str, Any]]] = []
            for idx, state in enumerate(original_states):
                hit, cached_result = cache.lookup(state, table_name, table_def, fsm_data)
                if hit:
                    cached_results.append((idx, cached_result))
                else:
                    states_to_process.append((idx, state))

            if not states_to_process:
                final_results: List[Dict[str, Any]] = []
                cache_map = {idx: res for idx, res in cached_results}
                for idx, state in enumerate(original_states):
                    cached = cache_map.get(idx)
                    if cached:
                        result = state.copy()
                        result["field_updates"] = cached.get("field_updates", result.get("field_updates", {}))
                        result["z3_constraints_smt2"] = cached.get(
                            "new_constraints",
                            result.get("z3_constraints_smt2", []),
                        )
                        result["was_cached"] = True
                        final_results.append(result)
                    else:
                        final_results.append(state)
                output_file.parent.mkdir(parents=True, exist_ok=True)
                with output_file.open("w", encoding="utf-8") as f:
                    json.dump(final_results, f, indent=2)
                return True, time.time() - start, ""

            states_only = [s for _, s in states_to_process]
            unique_states, index_mapping = self._optimize_table_input(
                states_only, table_name, table_def, fsm_data, cache
            )

            tmp_tag = uuid.uuid4().hex
            temp_input = input_states.parent / f".temp_{table_name}_{tmp_tag}_{input_states.name}"
            temp_output = output_file.parent / f".temp_{table_name}_{tmp_tag}_{output_file.name}"
            with temp_input.open("w", encoding="utf-8") as f:
                json.dump(unique_states, f)

            ok, _, err = self._run_egress_table(
                fsm_file=fsm_file,
                runtime_file=runtime_file,
                input_states=temp_input,
                table_name=table_name,
                output_file=temp_output,
                heartbeat_label=None,
            )
            if not ok:
                temp_input.unlink(missing_ok=True)
                temp_output.unlink(missing_ok=True)
                return False, time.time() - start, err

            with temp_output.open("r", encoding="utf-8") as f:
                processed_results = json.load(f)

            hash_to_result: Dict[str, Dict[str, Any]] = {}
            for idx, state in enumerate(unique_states):
                if idx < len(processed_results):
                    result = processed_results[idx]
                    state_hash = cache._compute_table_state_hash(
                        state, table_name, cache.table_relevant_fields[table_name]
                    )
                    hash_to_result[state_hash] = result
                    cache.store(state, result, table_name, table_def, fsm_data)

            full_results: List[Dict[str, Any]] = []
            processed_idx_map = {states_to_process[i][0]: i for i in range(len(states_to_process))}
            for orig_idx, state in enumerate(original_states):
                cached = next((r for i, r in cached_results if i == orig_idx), None)
                if cached:
                    result = state.copy()
                    result["field_updates"] = cached.get("field_updates", result.get("field_updates", {}))
                    result["z3_constraints_smt2"] = cached.get("new_constraints", result.get("z3_constraints_smt2", []))
                    result["was_cached"] = True
                else:
                    proc_idx = processed_idx_map.get(orig_idx)
                    if proc_idx is not None:
                        state_hash = index_mapping.get(proc_idx)
                        result = hash_to_result.get(state_hash, state).copy()
                        result["description"] = state.get("description", "Unknown")
                        result["was_cached"] = False
                    else:
                        result = state
                full_results.append(result)

            output_file.parent.mkdir(parents=True, exist_ok=True)
            with output_file.open("w", encoding="utf-8") as f:
                json.dump(full_results, f, indent=2)

            temp_input.unlink(missing_ok=True)
            temp_output.unlink(missing_ok=True)
            cache.save_cache()
            return True, time.time() - start, ""
        except Exception as exc:
            return False, time.time() - start, str(exc)

    def _run_ingress_table_reduced_nonoptimized(
        self,
        *,
        fsm_file: Path,
        topology_file: Path,
        runtime_file: Path,
        input_states: Path,
        table_name: str,
        output_file: Path,
        fsm_data: Dict[str, Any] | None = None,
        heartbeat_label: str | None = None,
    ) -> Tuple[bool, float, str]:
        start = time.time()

        if not self._ensure_table_cache_class() or self._optimize_table_input is None:
            return self._run_ingress_table(
                fsm_file=fsm_file,
                topology_file=topology_file,
                runtime_file=runtime_file,
                input_states=input_states,
                table_name=table_name,
                output_file=output_file,
                heartbeat_label=heartbeat_label,
            )

        try:
            if fsm_data is None:
                with fsm_file.open("r", encoding="utf-8") as f:
                    fsm_data = json.load(f)

            with input_states.open("r", encoding="utf-8") as f:
                original_states = json.load(f)
            if not isinstance(original_states, list):
                original_states = []

            if not original_states:
                output_file.parent.mkdir(parents=True, exist_ok=True)
                with output_file.open("w", encoding="utf-8") as f:
                    json.dump([], f)
                return True, time.time() - start, ""

            pipeline = next((p for p in fsm_data.get("pipelines", []) if p.get("name") == "ingress"), None)
            if pipeline is None:
                return self._run_ingress_table(
                    fsm_file=fsm_file,
                    topology_file=topology_file,
                    runtime_file=runtime_file,
                    input_states=input_states,
                    table_name=table_name,
                    output_file=output_file,
                    heartbeat_label=heartbeat_label,
                )

            table_def = next((t for t in pipeline.get("tables", []) if t.get("name") == table_name), None)
            if table_def is None:
                return self._run_ingress_table(
                    fsm_file=fsm_file,
                    topology_file=topology_file,
                    runtime_file=runtime_file,
                    input_states=input_states,
                    table_name=table_name,
                    output_file=output_file,
                    heartbeat_label=heartbeat_label,
                )

            hash_helper = self._table_execution_cache_cls(None)
            unique_states, index_mapping = self._optimize_table_input(
                original_states, table_name, table_def, fsm_data, hash_helper
            )

            tmp_tag = uuid.uuid4().hex
            temp_input = input_states.parent / f".temp_nonopt_{table_name}_{tmp_tag}_{input_states.name}"
            temp_output = output_file.parent / f".temp_nonopt_{table_name}_{tmp_tag}_{output_file.name}"
            with temp_input.open("w", encoding="utf-8") as f:
                json.dump(unique_states, f)

            ok, _, err = self._run_ingress_table(
                fsm_file=fsm_file,
                topology_file=topology_file,
                runtime_file=runtime_file,
                input_states=temp_input,
                table_name=table_name,
                output_file=temp_output,
                heartbeat_label=None,
            )
            if not ok:
                temp_input.unlink(missing_ok=True)
                temp_output.unlink(missing_ok=True)
                return False, time.time() - start, err

            with temp_output.open("r", encoding="utf-8") as f:
                processed_results = json.load(f)

            relevant_fields = hash_helper.table_relevant_fields.get(table_name, set())
            hash_to_result: Dict[str, Dict[str, Any]] = {}
            for idx, state in enumerate(unique_states):
                if idx < len(processed_results):
                    state_hash = hash_helper._compute_table_state_hash(state, table_name, relevant_fields)
                    hash_to_result[state_hash] = processed_results[idx]

            expanded_results: List[Dict[str, Any]] = []
            for orig_idx, orig_state in enumerate(original_states):
                state_hash = index_mapping.get(orig_idx)
                result = hash_to_result.get(state_hash, orig_state)
                if isinstance(result, dict):
                    expanded = result.copy()
                    expanded["description"] = orig_state.get("description", expanded.get("description", "Unknown"))
                else:
                    expanded = orig_state
                expanded_results.append(expanded)

            output_file.parent.mkdir(parents=True, exist_ok=True)
            with output_file.open("w", encoding="utf-8") as f:
                json.dump(expanded_results, f, indent=2)

            temp_input.unlink(missing_ok=True)
            temp_output.unlink(missing_ok=True)
            return True, time.time() - start, ""
        except Exception as exc:
            return False, time.time() - start, str(exc)

    def _run_egress_table_reduced_nonoptimized(
        self,
        *,
        fsm_file: Path,
        runtime_file: Path,
        input_states: Path,
        table_name: str,
        output_file: Path,
        fsm_data: Dict[str, Any] | None = None,
        heartbeat_label: str | None = None,
    ) -> Tuple[bool, float, str]:
        start = time.time()

        if not self._ensure_table_cache_class() or self._optimize_table_input is None:
            return self._run_egress_table(
                fsm_file=fsm_file,
                runtime_file=runtime_file,
                input_states=input_states,
                table_name=table_name,
                output_file=output_file,
                heartbeat_label=heartbeat_label,
            )

        try:
            if fsm_data is None:
                with fsm_file.open("r", encoding="utf-8") as f:
                    fsm_data = json.load(f)

            with input_states.open("r", encoding="utf-8") as f:
                original_states = json.load(f)
            if not isinstance(original_states, list):
                original_states = []

            if not original_states:
                output_file.parent.mkdir(parents=True, exist_ok=True)
                with output_file.open("w", encoding="utf-8") as f:
                    json.dump([], f)
                return True, time.time() - start, ""

            pipeline = next((p for p in fsm_data.get("pipelines", []) if p.get("name") == "egress"), None)
            if pipeline is None:
                return self._run_egress_table(
                    fsm_file=fsm_file,
                    runtime_file=runtime_file,
                    input_states=input_states,
                    table_name=table_name,
                    output_file=output_file,
                    heartbeat_label=heartbeat_label,
                )

            table_def = next((t for t in pipeline.get("tables", []) if t.get("name") == table_name), None)
            if table_def is None:
                return self._run_egress_table(
                    fsm_file=fsm_file,
                    runtime_file=runtime_file,
                    input_states=input_states,
                    table_name=table_name,
                    output_file=output_file,
                    heartbeat_label=heartbeat_label,
                )

            hash_helper = self._table_execution_cache_cls(None)
            unique_states, index_mapping = self._optimize_table_input(
                original_states, table_name, table_def, fsm_data, hash_helper
            )

            tmp_tag = uuid.uuid4().hex
            temp_input = input_states.parent / f".temp_nonopt_{table_name}_{tmp_tag}_{input_states.name}"
            temp_output = output_file.parent / f".temp_nonopt_{table_name}_{tmp_tag}_{output_file.name}"
            with temp_input.open("w", encoding="utf-8") as f:
                json.dump(unique_states, f)

            ok, _, err = self._run_egress_table(
                fsm_file=fsm_file,
                runtime_file=runtime_file,
                input_states=temp_input,
                table_name=table_name,
                output_file=temp_output,
                heartbeat_label=None,
            )
            if not ok:
                temp_input.unlink(missing_ok=True)
                temp_output.unlink(missing_ok=True)
                return False, time.time() - start, err

            with temp_output.open("r", encoding="utf-8") as f:
                processed_results = json.load(f)

            relevant_fields = hash_helper.table_relevant_fields.get(table_name, set())
            hash_to_result: Dict[str, Dict[str, Any]] = {}
            for idx, state in enumerate(unique_states):
                if idx < len(processed_results):
                    state_hash = hash_helper._compute_table_state_hash(state, table_name, relevant_fields)
                    hash_to_result[state_hash] = processed_results[idx]

            expanded_results: List[Dict[str, Any]] = []
            for orig_idx, orig_state in enumerate(original_states):
                state_hash = index_mapping.get(orig_idx)
                result = hash_to_result.get(state_hash, orig_state)
                if isinstance(result, dict):
                    expanded = result.copy()
                    expanded["description"] = orig_state.get("description", expanded.get("description", "Unknown"))
                else:
                    expanded = orig_state
                expanded_results.append(expanded)

            output_file.parent.mkdir(parents=True, exist_ok=True)
            with output_file.open("w", encoding="utf-8") as f:
                json.dump(expanded_results, f, indent=2)

            temp_input.unlink(missing_ok=True)
            temp_output.unlink(missing_ok=True)
            return True, time.time() - start, ""
        except Exception as exc:
            return False, time.time() - start, str(exc)

    def _run_egress_table(
        self,
        fsm_file: Path,
        runtime_file: Path,
        input_states: Path,
        table_name: str,
        output_file: Path,
        heartbeat_label: str | None = None,
    ) -> Tuple[bool, float, str]:
        cmd = [
            "python3",
            str(RUN_TABLE_EGRESS),
            str(fsm_file),
            str(runtime_file),
            str(input_states),
            SWITCH_ID,
            table_name,
            str(output_file),
        ]
        return run_command_with_heartbeat(
            cmd,
            cwd=RUN_SCRIPTS_DIR,
            timeout=STAGE_TIMEOUT_S,
            heartbeat_label=heartbeat_label,
            heartbeat_interval_s=HEARTBEAT_INTERVAL_S,
        )

    def _run_deparser(
        self, fsm_file: Path, input_states: Path, output_file: Path, heartbeat_label: str | None = None
    ) -> Tuple[bool, float, str]:
        cmd = ["python3", str(RUN_DEPARSER), str(fsm_file), str(input_states), str(output_file)]
        return run_command_with_heartbeat(
            cmd,
            cwd=RUN_SCRIPTS_DIR,
            timeout=STAGE_TIMEOUT_S,
            heartbeat_label=heartbeat_label,
            heartbeat_interval_s=HEARTBEAT_INTERVAL_S,
        )

    def _load_ingress_paths(self, fsm_file: Path) -> List[List[str]]:
        try:
            with fsm_file.open("r", encoding="utf-8") as f:
                fsm_data = json.load(f)
        except Exception:
            return []

        ingress = next((p for p in fsm_data.get("pipelines", []) if p.get("name") == "ingress"), None)
        if not ingress:
            return []

        tables = ingress.get("tables", [])
        conditionals = ingress.get("conditionals", [])
        table_by_name = {t.get("name"): t for t in tables if t.get("name")}
        cond_by_name = {c.get("name"): c for c in conditionals if c.get("name")}
        init_node = ingress.get("init_table")
        paths: List[List[str]] = []

        def explore(node_name: str | None, current_tables: List[str]) -> None:
            if node_name is None:
                paths.append(current_tables.copy())
                return
            table = table_by_name.get(node_name)
            if table is not None:
                explore(table.get("base_default_next"), current_tables + [node_name])
                return
            cond = cond_by_name.get(node_name)
            if cond is not None:
                explore(cond.get("true_next"), current_tables)
                explore(cond.get("false_next"), current_tables)
                return
            # Unknown node: treat as terminal to avoid infinite recursion.
            paths.append(current_tables.copy())

        explore(init_node, [])
        return paths

    def _run_ingress_path_nonoptimized(
        self,
        *,
        fsm_file: Path,
        topology_file: Path,
        runtime_file: Path,
        parser_output: Path,
        table_path: List[str],
        build_dir: Path,
        run_number: int,
        path_idx: int,
        fsm_data: Dict[str, Any] | None = None,
    ) -> Tuple[bool, float, Path | None, str]:
        current_snapshot = parser_output
        total_time = 0.0

        if not table_path:
            return True, total_time, parser_output, ""

        for table_idx, table_name in enumerate(table_path):
            table_out = build_dir / f"full_run{run_number}_path{path_idx}_ingress_{table_idx}.json"
            ok, duration, err = self._run_ingress_table_reduced_nonoptimized(
                fsm_file=fsm_file,
                topology_file=topology_file,
                runtime_file=runtime_file,
                input_states=current_snapshot,
                table_name=table_name,
                output_file=table_out,
                fsm_data=fsm_data,
                heartbeat_label=None,
            )
            total_time += duration
            if table_out.exists():
                current_snapshot = table_out
            if not ok and not table_out.exists():
                return False, total_time, None, f"{table_name}: {err}"
        return True, total_time, current_snapshot, ""

    def _run_ingress_path_optimized(
        self,
        *,
        fsm_file: Path,
        topology_file: Path,
        runtime_file: Path,
        parser_output: Path,
        table_path: List[str],
        build_dir: Path,
        run_number: int,
        path_idx: int,
        fsm_data: Dict[str, Any],
    ) -> Tuple[bool, float, Path | None, str]:
        current_snapshot = parser_output
        total_time = 0.0

        if not table_path:
            return True, total_time, parser_output, ""

        for table_idx, table_name in enumerate(table_path):
            table_out = build_dir / f"full_run{run_number}_path{path_idx}_ingress_opt_{table_idx}.json"
            ok, duration, err = self._run_ingress_table_cached_legacy(
                fsm_file=fsm_file,
                topology_file=topology_file,
                runtime_file=runtime_file,
                input_states=current_snapshot,
                table_name=table_name,
                output_file=table_out,
                run_number=run_number,
                fsm_data=fsm_data,
            )
            total_time += duration
            if table_out.exists():
                current_snapshot = table_out
            if not ok and not table_out.exists():
                return False, total_time, None, f"{table_name}: {err}"
        return True, total_time, current_snapshot, ""

    def _run_ingress_parallel_nonoptimized(
        self,
        *,
        fsm_file: Path,
        topology_file: Path,
        runtime_file: Path,
        parser_output: Path,
        build_dir: Path,
        run_number: int,
    ) -> Tuple[bool, float, Path | None, str, int, int]:
        paths = self._load_ingress_paths(fsm_file)
        total_paths = len(paths)
        if total_paths == 0:
            return False, 0.0, None, "No ingress paths found in FSM.", 0, 0

        fsm_data_for_nonopt_dedup: Dict[str, Any] | None = None
        try:
            with fsm_file.open("r", encoding="utf-8") as f:
                fsm_data_for_nonopt_dedup = json.load(f)
        except Exception:
            fsm_data_for_nonopt_dedup = None

        max_workers = os.cpu_count() or 4
        ingress_total = 0.0
        explored = 0
        final_state_files: List[Path] = []
        errors: List[str] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [
                pool.submit(
                    self._run_ingress_path_nonoptimized,
                    fsm_file=fsm_file,
                    topology_file=topology_file,
                    runtime_file=runtime_file,
                    parser_output=parser_output,
                    table_path=table_path,
                    build_dir=build_dir,
                    run_number=run_number,
                    path_idx=path_idx,
                    fsm_data=fsm_data_for_nonopt_dedup,
                )
                for path_idx, table_path in enumerate(paths)
            ]
            pending = set(futures)
            completed = 0
            wait_start = time.time()
            heartbeat_count = 0
            while pending:
                done, pending = concurrent.futures.wait(
                    pending,
                    timeout=HEARTBEAT_INTERVAL_S,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
                if not done:
                    heartbeat_count += 1
                    if not self.compact_logs or heartbeat_count % 3 == 0:
                        elapsed = time.time() - wait_start
                        print(
                            "      ... Ingress parallel still running "
                            f"({elapsed:.1f}s) [{completed}/{total_paths} paths done, {len(pending)} pending]"
                        )
                    continue

                for future in done:
                    completed += 1
                    try:
                        ok, path_time, final_state_file, err = future.result()
                    except Exception as exc:
                        errors.append(str(exc))
                        continue
                    ingress_total += path_time
                    if ok and final_state_file is not None and final_state_file.exists():
                        explored += 1
                        final_state_files.append(final_state_file)
                    elif err:
                        errors.append(err)

        if explored == 0:
            err = errors[0] if errors else "No ingress path produced valid output."
            return False, ingress_total, None, err, total_paths, explored

        merged_states: List[Dict[str, Any]] = []
        for state_file in set(final_state_files):
            try:
                with state_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    merged_states.extend(data)
            except Exception:
                continue

        merged_output = build_dir / f"full_run{run_number}_ingress_merged.json"
        with merged_output.open("w", encoding="utf-8") as f:
            json.dump(merged_states, f, ensure_ascii=False, indent=2)

        if explored != total_paths:
            err_preview = "; ".join(errors[:3]) if errors else "Some paths failed."
            return False, ingress_total, merged_output, err_preview, total_paths, explored
        return True, ingress_total, merged_output, "", total_paths, explored

    def _run_ingress_parallel_optimized(
        self,
        *,
        fsm_file: Path,
        topology_file: Path,
        runtime_file: Path,
        parser_output: Path,
        build_dir: Path,
        run_number: int,
    ) -> Tuple[bool, float, Path | None, str, int, int]:
        try:
            with fsm_file.open("r", encoding="utf-8") as f:
                fsm_data = json.load(f)
        except Exception as exc:
            return False, 0.0, None, f"Failed to load FSM for optimized ingress: {exc}", 0, 0

        paths = self._load_ingress_paths(fsm_file)
        total_paths = len(paths)
        if total_paths == 0:
            return False, 0.0, None, "No ingress paths found in FSM.", 0, 0

        max_workers = os.cpu_count() or 4
        ingress_total = 0.0
        explored = 0
        final_state_files: List[Path] = []
        errors: List[str] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [
                pool.submit(
                    self._run_ingress_path_optimized,
                    fsm_file=fsm_file,
                    topology_file=topology_file,
                    runtime_file=runtime_file,
                    parser_output=parser_output,
                    table_path=table_path,
                    build_dir=build_dir,
                    run_number=run_number,
                    path_idx=path_idx,
                    fsm_data=fsm_data,
                )
                for path_idx, table_path in enumerate(paths)
            ]
            pending = set(futures)
            completed = 0
            wait_start = time.time()
            heartbeat_count = 0
            while pending:
                done, pending = concurrent.futures.wait(
                    pending,
                    timeout=HEARTBEAT_INTERVAL_S,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
                if not done:
                    heartbeat_count += 1
                    if not self.compact_logs or heartbeat_count % 3 == 0:
                        elapsed = time.time() - wait_start
                        print(
                            "      ... Ingress parallel [opt] still running "
                            f"({elapsed:.1f}s) [{completed}/{total_paths} paths done, {len(pending)} pending]"
                        )
                    continue

                for future in done:
                    completed += 1
                    try:
                        ok, path_time, final_state_file, err = future.result()
                    except Exception as exc:
                        errors.append(str(exc))
                        continue
                    ingress_total += path_time
                    if ok and final_state_file is not None and final_state_file.exists():
                        explored += 1
                        final_state_files.append(final_state_file)
                    elif err:
                        errors.append(err)

        if explored == 0:
            err = errors[0] if errors else "No ingress path produced valid output."
            return False, ingress_total, None, err, total_paths, explored

        merged_states: List[Dict[str, Any]] = []
        for state_file in set(final_state_files):
            try:
                with state_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    merged_states.extend(data)
            except Exception:
                continue

        merged_output = build_dir / f"full_run{run_number}_ingress_opt_merged.json"
        with merged_output.open("w", encoding="utf-8") as f:
            json.dump(merged_states, f, ensure_ascii=False, indent=2)

        if explored != total_paths:
            err_preview = "; ".join(errors[:3]) if errors else "Some paths failed."
            return False, ingress_total, merged_output, err_preview, total_paths, explored
        return True, ingress_total, merged_output, "", total_paths, explored

    def _new_run_dirs(self, mode: str) -> Tuple[Path, Path]:
        run_dir = OUTPUT_ROOT / f"{mode}_{now_tag()}"
        gen_dir = run_dir / "synthetic_p4s"
        gen_dir.mkdir(parents=True, exist_ok=True)
        return run_dir, gen_dir

    def _run_graph_script(self, script: Path, csv_file: Path, output_pdf: Path, open_pdf: bool) -> bool:
        if not script.exists():
            print(f"Error: graph script not found: {script}")
            return False
        if not csv_file.exists():
            print(f"Error: CSV not found: {csv_file}")
            return False

        cmd = [
            "python3",
            str(script),
            "--csv",
            str(csv_file),
            "--output-pdf",
            str(output_pdf),
        ]
        if open_pdf:
            cmd.append("--open")

        env = os.environ.copy()
        env.setdefault("P4SYMTEST_OPEN_REQUEST_FILE", "/app/workspace/.benchmark_open_requests")

        print(f"\nRunning graph with: {' '.join(cmd)}")
        proc = subprocess.run(cmd, cwd=str(script.parent), env=env)
        if proc.returncode != 0:
            print(f"Failed to generate graph (exit={proc.returncode}).")
            return False
        return True

    def _post_benchmark_menu(self, mode: str, run_dir: Path, csv_file: Path) -> bool:
        script_map = {
            "parser": PLOT_PARSER,
            "tables": PLOT_TABLES,
            "deparser": PLOT_DEPARSER,
            "full": PLOT_FULL,
            "full_optimized": PLOT_FULL,
        }
        script = script_map.get(mode)
        if script is None:
            return True

        output_pdf = run_dir / f"graph_{mode}.pdf"

        while True:
            print("Options:")
            print("1) Generate graph")
            print("2) Back to main menu")
            print("0) Exit")
            choice = input("Choose an option: ").strip()

            if choice == "1":
                open_choice = ask_choice("Open PDF automatically", {"1": "Yes", "2": "No"}, "1")
                open_pdf = open_choice == "1"
                ok = self._run_graph_script(script, csv_file, output_pdf, open_pdf)
                if ok:
                    print(f"Graph saved to: {output_pdf.resolve()}")
                continue

            if choice == "2":
                return True

            if choice == "0":
                return False

            print("Invalid option.")

    def benchmark_parser(self) -> bool:
        print("\n=== Benchmark: Parser ===")
        benchmark_start = time.time()
        runs = ask_int("Runs per configuration", 10, 1)
        parser_start = ask_int("Parser states (start)", 3, 1)
        parser_max = ask_int("Parser states (max)", 20, parser_start)
        parser_step = ask_int("Parser states (step)", 3, 1)
        headers_per_state = ask_int("Headers per state", 2, 1)

        parser_values = build_range(parser_start, parser_max, parser_step)
        run_dir, gen_dir = self._new_run_dirs("parser")
        rows: List[Dict] = []

        print(f"\nGenerating/running {len(parser_values)} configurations...")
        for parser_states in parser_values:
            meta = self.generator.generate_program(
                parser_states=parser_states,
                headers_per_state=headers_per_state,
                ingress_tables=1,
                egress_tables=1,
                actions_per_table=1,
                output_dir=gen_dir,
            )

            p4_file = Path(meta["p4_file"])
            build_dir = gen_dir / f"{meta['id']}_build"
            compile_ok, compile_time, compile_err, fsm_file = self._compile(p4_file, build_dir)

            if not compile_ok:
                rows.append(
                    {
                        "benchmark": "parser",
                        "config_id": meta["id"],
                        "parser_states": parser_states,
                        "run_number": 0,
                        "success": False,
                        "duration_s": round(compile_time, 6),
                        "output_states": 0,
                        "error": f"compile: {compile_err}",
                    }
                )
                print(f"  [X] {meta['id']} compile failed")
                continue

            print(f"  [OK] {meta['id']} compiled. Running parser ({runs}x)...")
            for run_number in range(1, runs + 1):
                parser_out = build_dir / f"parser_states_run{run_number}.json"
                ok, duration, err = self._run_parser(fsm_file, parser_out)
                rows.append(
                    {
                        "benchmark": "parser",
                        "config_id": meta["id"],
                        "parser_states": parser_states,
                        "run_number": run_number,
                        "success": ok,
                        "duration_s": round(duration, 6),
                        "compile_time_s": round(compile_time, 6) if run_number == 1 else 0.0,
                        "output_states": json_list_size(parser_out),
                        "error": err if not ok else "",
                    }
                )

        csv_file = run_dir / "parser_raw.csv"
        summary_file = run_dir / "summary.json"
        write_csv(rows, csv_file)
        write_summary(rows, summary_file)
        total_elapsed = time.time() - benchmark_start
        print(
            f"\nParser benchmark completed.\n"
            f"  - CSV: {csv_file}\n"
            f"  - Summary: {summary_file}\n"
            f"  - Total elapsed: {format_elapsed(total_elapsed)} ({total_elapsed:.3f}s)\n"
        )
        return self._post_benchmark_menu("parser", run_dir, csv_file)

    def benchmark_tables(self) -> bool:
        print("\n=== Benchmark: Ingress/Egress Tables ===")
        benchmark_start = time.time()
        pipeline_choice = ask_choice(
            "Pipeline",
            {"1": "Ingress", "2": "Egress", "3": "Ingress + Egress"},
            "1",
        )
        if pipeline_choice == "1":
            pipelines = ["ingress"]
        elif pipeline_choice == "2":
            pipelines = ["egress"]
        else:
            pipelines = ["ingress", "egress"]

        runs = ask_int("Runs per configuration", 10, 1)
        parser_start = ask_int("Parser states (start, paper-aligned range 3..15 -> ~4..40 entrance states)", 3, 1)
        parser_max = ask_int("Parser states (max)", 15, parser_start)
        parser_step = ask_int("Parser states (step)", 3, 1)
        actions_start = ask_int("Actions per table (start)", 2, 1)
        actions_max = ask_int("Actions per table (max)", 15, actions_start)
        actions_step = ask_int("Actions per table (step)", 3, 1)
        headers_per_state = ask_int("Headers per state", 1, 1)

        parser_values = build_range(parser_start, parser_max, parser_step)
        action_values = build_range(actions_start, actions_max, actions_step)
        run_dir, gen_dir = self._new_run_dirs("tables")
        rows: List[Dict] = []

        total_cfg = len(pipelines) * len(parser_values) * len(action_values)
        cfg_idx = 0
        for pipeline in pipelines:
            for parser_states in parser_values:
                for actions in action_values:
                    cfg_idx += 1
                    ingress_tables = 1 if pipeline == "ingress" else 0
                    egress_tables = 1 if pipeline == "egress" else 0

                    meta = self.generator.generate_program(
                        parser_states=parser_states,
                        headers_per_state=headers_per_state,
                        ingress_tables=ingress_tables,
                        egress_tables=egress_tables,
                        actions_per_table=actions,
                        output_dir=gen_dir,
                    )

                    print(
                        f"  [{cfg_idx}/{total_cfg}] {pipeline.upper()} "
                        f"states={parser_states} actions={actions}"
                    )
                    p4_file = Path(meta["p4_file"])
                    topology_file = Path(meta["topology_file"])
                    runtime_file = Path(meta["runtime_file"])
                    build_dir = gen_dir / f"{meta['id']}_{pipeline}_build"
                    compile_ok, compile_time, compile_err, fsm_file = self._compile(p4_file, build_dir)

                    if not compile_ok:
                        rows.append(
                            {
                                "benchmark": "tables",
                                "pipeline": pipeline,
                                "config_id": meta["id"],
                                "parser_states": parser_states,
                                "actions_per_table": actions,
                                "run_number": 0,
                                "success": False,
                                "duration_s": round(compile_time, 6),
                                "parser_output_states": 0,
                                "table_output_states": 0,
                                "error": f"compile: {compile_err}",
                            }
                        )
                        continue

                    parser_out = build_dir / "parser_states.json"
                    parser_ok, parser_time, parser_err = self._run_parser(fsm_file, parser_out)
                    parser_states_out = json_list_size(parser_out)
                    if not parser_ok or parser_states_out == 0:
                        rows.append(
                            {
                                "benchmark": "tables",
                                "pipeline": pipeline,
                                "config_id": meta["id"],
                                "parser_states": parser_states,
                                "actions_per_table": actions,
                                "run_number": 0,
                                "success": False,
                                "duration_s": round(parser_time, 6),
                                "parser_output_states": parser_states_out,
                                "table_output_states": 0,
                                "error": f"parser: {parser_err}" if parser_err else "parser output empty",
                            }
                        )
                        continue

                    for run_number in range(1, runs + 1):
                        table_out = build_dir / f"{pipeline}_table_run{run_number}.json"
                        if pipeline == "ingress":
                            ok, duration, err = self._run_ingress_table(
                                fsm_file=fsm_file,
                                topology_file=topology_file,
                                runtime_file=runtime_file,
                                input_states=parser_out,
                                table_name="MyIngress.ingress_table_0",
                                output_file=table_out,
                            )
                        else:
                            ok, duration, err = self._run_egress_table(
                                fsm_file=fsm_file,
                                runtime_file=runtime_file,
                                input_states=parser_out,
                                table_name="MyEgress.egress_table_0",
                                output_file=table_out,
                            )

                        rows.append(
                            {
                                "benchmark": "tables",
                                "pipeline": pipeline,
                                "config_id": meta["id"],
                                "parser_states": parser_states,
                                "actions_per_table": actions,
                                "run_number": run_number,
                                "success": ok,
                                "duration_s": round(duration, 6),
                                "compile_time_s": round(compile_time, 6) if run_number == 1 else 0.0,
                                "parser_time_s": round(parser_time, 6) if run_number == 1 else 0.0,
                                "parser_output_states": parser_states_out,
                                "table_output_states": json_list_size(table_out),
                                "error": err if not ok else "",
                            }
                        )

        csv_file = run_dir / "tables_raw.csv"
        summary_file = run_dir / "summary.json"
        write_csv(rows, csv_file)
        write_summary(rows, summary_file)
        total_elapsed = time.time() - benchmark_start
        print(
            f"\nTable benchmark completed.\n"
            f"  - CSV: {csv_file}\n"
            f"  - Summary: {summary_file}\n"
            f"  - Total elapsed: {format_elapsed(total_elapsed)} ({total_elapsed:.3f}s)\n"
        )
        return self._post_benchmark_menu("tables", run_dir, csv_file)

    def benchmark_deparser(self) -> bool:
        print("\n=== Benchmark: Deparser ===")
        benchmark_start = time.time()
        runs = ask_int("Runs per configuration", 10, 1)
        parser_start = ask_int("Parser states (start)", 3, 1)
        parser_max = ask_int("Parser states (max)", 30, parser_start)
        parser_step = ask_int("Parser states (step)", 3, 1)
        headers_per_state = ask_int("Headers per state", 1, 1)

        parser_values = build_range(parser_start, parser_max, parser_step)
        run_dir, gen_dir = self._new_run_dirs("deparser")
        rows: List[Dict] = []

        print(f"\nGenerating/running {len(parser_values)} configurations...")
        for parser_states in parser_values:
            meta = self.generator.generate_program(
                parser_states=parser_states,
                headers_per_state=headers_per_state,
                ingress_tables=1,
                egress_tables=1,
                actions_per_table=2,
                output_dir=gen_dir,
            )

            p4_file = Path(meta["p4_file"])
            build_dir = gen_dir / f"{meta['id']}_build"
            compile_ok, compile_time, compile_err, fsm_file = self._compile(p4_file, build_dir)
            if not compile_ok:
                rows.append(
                    {
                        "benchmark": "deparser",
                        "config_id": meta["id"],
                        "parser_states": parser_states,
                        "run_number": 0,
                        "success": False,
                        "duration_s": round(compile_time, 6),
                        "input_states": 0,
                        "output_states": 0,
                        "error": f"compile: {compile_err}",
                    }
                )
                continue

            parser_out = build_dir / "parser_states.json"
            parser_ok, parser_time, parser_err = self._run_parser(fsm_file, parser_out)
            parser_states_out = json_list_size(parser_out)
            if not parser_ok or parser_states_out == 0:
                rows.append(
                    {
                        "benchmark": "deparser",
                        "config_id": meta["id"],
                        "parser_states": parser_states,
                        "run_number": 0,
                        "success": False,
                        "duration_s": round(parser_time, 6),
                        "input_states": parser_states_out,
                        "output_states": 0,
                        "error": f"parser: {parser_err}" if parser_err else "parser output empty",
                    }
                )
                continue

            print(f"  [OK] {meta['id']} parser={parser_states_out} states. Running deparser ({runs}x)...")
            for run_number in range(1, runs + 1):
                deparser_out = build_dir / f"deparser_run{run_number}.json"
                ok, duration, err = self._run_deparser(fsm_file, parser_out, deparser_out)
                rows.append(
                    {
                        "benchmark": "deparser",
                        "config_id": meta["id"],
                        "parser_states": parser_states,
                        "run_number": run_number,
                        "success": ok,
                        "duration_s": round(duration, 6),
                        "compile_time_s": round(compile_time, 6) if run_number == 1 else 0.0,
                        "parser_time_s": round(parser_time, 6) if run_number == 1 else 0.0,
                        "input_states": parser_states_out,
                        "output_states": json_list_size(deparser_out),
                        "error": err if not ok else "",
                    }
                )

        csv_file = run_dir / "deparser_raw.csv"
        summary_file = run_dir / "summary.json"
        write_csv(rows, csv_file)
        write_summary(rows, summary_file)
        total_elapsed = time.time() - benchmark_start
        print(
            f"\nDeparser benchmark completed.\n"
            f"  - CSV: {csv_file}\n"
            f"  - Summary: {summary_file}\n"
            f"  - Total elapsed: {format_elapsed(total_elapsed)} ({total_elapsed:.3f}s)\n"
        )
        return self._post_benchmark_menu("deparser", run_dir, csv_file)

    def benchmark_full(self, optimized: bool = False) -> bool:
        mode_label = "OPTIMIZED" if optimized else "NON-OPTIMIZED"
        print(f"\n=== Benchmark: Full Pipeline ({mode_label}) ===")
        benchmark_start = time.time()
        if optimized and not self._load_optimized_helpers():
            print("[WARN] Continuing with NON-OPTIMIZED execution because optimized helpers are unavailable.")
            optimized = False
        runs = ask_int("Runs per configuration", 5, 1)
        parser_states = ask_int("Parser states (fixed)", 8, 1)
        ingress_start = ask_int("Ingress tables (start)", 2, 1)
        ingress_max = ask_int("Ingress tables (max)", 12, ingress_start)
        ingress_step = ask_int("Ingress tables (step)", 2, 1)
        egress_tables = ask_int("Egress tables (fixed)", 1, 0)
        actions_per_table = ask_int("Actions per table", 2, 1)
        headers_per_state = ask_int("Headers per state", 1, 1)

        ingress_values = build_range(ingress_start, ingress_max, ingress_step)
        full_mode = "full_optimized" if optimized else "full"
        run_dir, gen_dir = self._new_run_dirs(full_mode)
        rows: List[Dict] = []

        total_cfg = len(ingress_values)
        print(
            f"\nGenerating/running {total_cfg} full configurations "
            f"({mode_label.lower()}; {total_cfg * runs} total runs)..."
        )
        for cfg_idx, ingress_tables in enumerate(ingress_values, start=1):
            meta = self.generator.generate_program(
                parser_states=parser_states,
                headers_per_state=headers_per_state,
                ingress_tables=ingress_tables,
                egress_tables=egress_tables,
                actions_per_table=actions_per_table,
                output_dir=gen_dir,
                ingress_logic_type="parallel",
                prog_id_suffix="_full",
            )

            print(
                f"\n[CFG {cfg_idx}/{total_cfg}] {meta['id']} | "
                f"ingress={ingress_tables} egress={egress_tables} runs={runs}"
            )
            p4_file = Path(meta["p4_file"])
            topology_file = Path(meta["topology_file"])
            runtime_file = Path(meta["runtime_file"])
            build_dir = gen_dir / f"{meta['id']}_build"
            self._vprint("  - Compiling P4...")
            compile_ok, compile_time, compile_err, fsm_file = self._compile(p4_file, build_dir)
            if not compile_ok:
                print(f"  [X] Compile failed in {compile_time:.3f}s: {compile_err}")
                rows.append(
                    {
                        "benchmark": full_mode,
                        "config_id": meta["id"],
                        "ingress_tables": ingress_tables,
                        "egress_tables": egress_tables,
                        "run_number": 0,
                        "success": False,
                        "duration_s": round(compile_time, 6),
                        "parser_states_out": 0,
                        "deparser_states_out": 0,
                        "error": f"compile: {compile_err}",
                    }
                )
                continue
            self._vprint(f"  [OK] Compile completed in {compile_time:.3f}s")

            for run_number in range(1, runs + 1):
                run_start = time.time()
                if self.compact_logs:
                    print(f"    [RUN {run_number}/{runs}] started")
                else:
                    print(f"    [RUN {run_number}/{runs}] Running parser...")
                parser_out = build_dir / f"full_parser_run{run_number}.json"
                parser_ok, parser_time, parser_err = self._run_parser(
                    fsm_file,
                    parser_out,
                    heartbeat_label=f"Parser RUN {run_number}/{runs}",
                )
                parser_states_out = json_list_size(parser_out)
                if not parser_ok or parser_states_out == 0:
                    err_msg = f"parser: {parser_err}" if parser_err else "parser output empty"
                    print(
                        f"    [X] Parser failed in {parser_time:.3f}s "
                        f"(states={parser_states_out}): {err_msg}"
                    )
                    run_duration = round(time.time() - run_start, 6)
                    rows.append(
                        {
                            "benchmark": full_mode,
                            "config_id": meta["id"],
                            "ingress_tables": ingress_tables,
                            "egress_tables": egress_tables,
                            "run_number": run_number,
                            "success": False,
                            "duration_s": run_duration,
                            "compile_time_s": round(compile_time, 6) if run_number == 1 else 0.0,
                            "parser_time_s": round(parser_time, 6),
                            "ingress_time_s": 0.0,
                            "egress_time_s": 0.0,
                            "deparser_time_s": 0.0,
                            "parser_states_out": parser_states_out,
                            "deparser_states_out": 0,
                            "error": err_msg,
                        }
                    )
                    continue
                self._vprint(f"    [OK] Parser in {parser_time:.3f}s (states={parser_states_out})")

                current_snapshot = parser_out
                ingress_total = 0.0
                egress_total = 0.0
                run_success = True
                error_msg = ""
                if optimized:
                    self._vprint("      [Ingress] Running path-level parallel execution (optimized mode with cache)...")
                    (
                        ingress_ok,
                        ingress_total,
                        merged_snapshot,
                        ingress_err,
                        total_paths,
                        explored_paths,
                    ) = self._run_ingress_parallel_optimized(
                        fsm_file=fsm_file,
                        topology_file=topology_file,
                        runtime_file=runtime_file,
                        parser_output=parser_out,
                        build_dir=build_dir,
                        run_number=run_number,
                    )
                    if not ingress_ok or merged_snapshot is None:
                        run_success = False
                        error_msg = f"ingress parallel (optimized): {ingress_err}"
                        print(
                            f"      [X] Ingress parallel failed "
                            f"({explored_paths}/{total_paths} paths): {error_msg}"
                        )
                    else:
                        current_snapshot = merged_snapshot
                        self._vprint(
                            f"      [OK] Ingress parallel completed (aggregated table-time {ingress_total:.3f}s) "
                            f"({explored_paths}/{total_paths} paths explored)"
                        )
                else:
                    self._vprint("      [Ingress] Running path-level parallel execution (non-optimized mode)...")
                    (
                        ingress_ok,
                        ingress_total,
                        merged_snapshot,
                        ingress_err,
                        total_paths,
                        explored_paths,
                    ) = self._run_ingress_parallel_nonoptimized(
                        fsm_file=fsm_file,
                        topology_file=topology_file,
                        runtime_file=runtime_file,
                        parser_output=parser_out,
                        build_dir=build_dir,
                        run_number=run_number,
                    )
                    if not ingress_ok or merged_snapshot is None:
                        run_success = False
                        error_msg = f"ingress parallel: {ingress_err}"
                        print(
                            f"      [X] Ingress parallel failed "
                            f"({explored_paths}/{total_paths} paths): {error_msg}"
                        )
                    else:
                        current_snapshot = merged_snapshot
                        self._vprint(
                            f"      [OK] Ingress parallel completed (aggregated table-time {ingress_total:.3f}s) "
                            f"({explored_paths}/{total_paths} paths explored)"
                        )

                if run_success:
                    fsm_data_for_egress_cache: Dict[str, Any] | None = None
                    try:
                        with fsm_file.open("r", encoding="utf-8") as f:
                            fsm_data_for_egress_cache = json.load(f)
                    except Exception:
                        fsm_data_for_egress_cache = None
                    for idx in range(egress_tables):
                        table_name = f"MyEgress.egress_table_{idx}"
                        table_out = build_dir / f"full_run{run_number}_egress_{idx}.json"
                        self._vprint(f"      [Egress {idx + 1}/{egress_tables}] {table_name}...")
                        if optimized:
                            ok, duration, err = self._run_egress_table_cached_legacy(
                                fsm_file=fsm_file,
                                runtime_file=runtime_file,
                                input_states=current_snapshot,
                                table_name=table_name,
                                output_file=table_out,
                                run_number=run_number,
                                fsm_data=fsm_data_for_egress_cache,
                            )
                        else:
                            ok, duration, err = self._run_egress_table_reduced_nonoptimized(
                                fsm_file=fsm_file,
                                runtime_file=runtime_file,
                                input_states=current_snapshot,
                                table_name=table_name,
                                output_file=table_out,
                                fsm_data=fsm_data_for_egress_cache,
                                heartbeat_label=f"Egress {idx + 1}/{egress_tables} ({table_name})",
                            )
                        egress_total += duration
                        if table_out.exists():
                            current_snapshot = table_out
                        if not ok and not table_out.exists():
                            run_success = False
                            error_msg = f"egress {table_name}: {err}"
                            print(f"      [X] Failed in {duration:.3f}s: {error_msg}")
                            break
                        if ok:
                            self._vprint(f"      [OK] {duration:.3f}s")
                        else:
                            self._vprint(
                                f"      [!] Returned an error in {duration:.3f}s, "
                                "but partial output was generated; continuing."
                            )

                deparser_time = 0.0
                deparser_out_states = 0
                if run_success:
                    deparser_out = build_dir / f"full_run{run_number}_deparser.json"
                    deparser_input = current_snapshot
                    deparser_opt_map: Dict[str, Any] | None = None
                    if optimized and self._optimize_and_process_deparser is not None:
                        try:
                            with current_snapshot.open("r", encoding="utf-8") as f:
                                all_final_states = json.load(f)
                            deparser_input, deparser_opt_map = self._optimize_and_process_deparser(
                                all_final_states, build_dir, run_number
                            )
                        except Exception as exc:
                            print(f"      [WARN] Deparser optimization failed: {exc}. Using original states.")
                            deparser_input = current_snapshot
                            deparser_opt_map = None
                    self._vprint("      [Deparser] Running...")
                    deparser_ok, deparser_time, deparser_err = self._run_deparser(
                        fsm_file=fsm_file,
                        input_states=deparser_input,
                        output_file=deparser_out,
                        heartbeat_label=(
                            f"Deparser RUN {run_number}/{runs} [opt]"
                            if optimized
                            else f"Deparser RUN {run_number}/{runs}"
                        ),
                    )
                    if not deparser_ok:
                        run_success = False
                        error_msg = f"deparser: {deparser_err}"
                        print(f"      [X] Failed in {deparser_time:.3f}s: {error_msg}")
                    else:
                        if optimized and deparser_opt_map is not None and self._expand_deparser_results is not None:
                            try:
                                expanded_file = self._expand_deparser_results(
                                    deparser_out, deparser_opt_map, build_dir, run_number
                                )
                                deparser_out_states = json_list_size(expanded_file)
                            except Exception as exc:
                                print(
                                    "      [WARN] Failed to expand optimized deparser results: "
                                    f"{exc}. Keeping optimized output."
                                )
                                deparser_out_states = json_list_size(deparser_out)
                        else:
                            deparser_out_states = json_list_size(deparser_out)
                        self._vprint(
                            f"      [OK] {deparser_time:.3f}s "
                            f"(states={deparser_out_states})"
                        )

                run_duration = round(time.time() - run_start, 6)
                rows.append(
                    {
                        "benchmark": full_mode,
                        "config_id": meta["id"],
                        "ingress_tables": ingress_tables,
                        "egress_tables": egress_tables,
                        "run_number": run_number,
                        "success": run_success,
                        "duration_s": run_duration,
                        "compile_time_s": round(compile_time, 6) if run_number == 1 else 0.0,
                        "parser_time_s": round(parser_time, 6),
                        "ingress_time_s": round(ingress_total, 6),
                        "egress_time_s": round(egress_total, 6),
                        "deparser_time_s": round(deparser_time, 6),
                        "parser_states_out": parser_states_out,
                        "deparser_states_out": deparser_out_states,
                        "error": error_msg,
                    }
                )
                if run_success:
                    print(
                        f"    [OK] RUN {run_number}/{runs} completed in {run_duration:.3f}s "
                        f"(parser={parser_time:.3f}s ingress={ingress_total:.3f}s "
                        f"egress={egress_total:.3f}s deparser={deparser_time:.3f}s)"
                    )
                else:
                    print(f"    [X] RUN {run_number}/{runs} failed in {run_duration:.3f}s: {error_msg}")

        csv_file = run_dir / "full_raw.csv"
        summary_file = run_dir / "summary.json"
        write_csv(rows, csv_file)
        write_summary(rows, summary_file)
        total_elapsed = time.time() - benchmark_start
        print(
            f"\nFull benchmark ({mode_label.lower()}) completed.\n"
            f"  - CSV: {csv_file}\n"
            f"  - Summary: {summary_file}\n"
            f"  - Total elapsed: {format_elapsed(total_elapsed)} ({total_elapsed:.3f}s)\n"
        )
        return self._post_benchmark_menu(full_mode, run_dir, csv_file)


def print_menu() -> None:
    print("\n" + "=" * 72)
    print("P4SymTest Benchmark CLI")
    print("=" * 72)
    print("1) Benchmark Parser")
    print("2) Benchmark Ingress/Egress Tables")
    print("3) Benchmark Deparser")
    print("4) Benchmark Full Pipeline (Non-Optimized)")
    print("5) Benchmark Full Pipeline (Optimized)")
    print("0) Exit")


def main() -> None:
    runner = BenchmarkMenuRunner()
    print(f"Results will be saved in: {OUTPUT_ROOT}")
    if COMPACT_LOGS:
        print(
            "Log mode: compact "
            "(set P4SYMTEST_BENCH_COMPACT_LOGS=0 for detailed logs)."
        )
    while True:
        print_menu()
        choice = input("Choose an option: ").strip()
        if choice == "0":
            print("Exiting.")
            return
        if choice == "1":
            keep_running = runner.benchmark_parser()
            if not keep_running:
                print("Exiting.")
                return
            continue
        if choice == "2":
            keep_running = runner.benchmark_tables()
            if not keep_running:
                print("Exiting.")
                return
            continue
        if choice == "3":
            keep_running = runner.benchmark_deparser()
            if not keep_running:
                print("Exiting.")
                return
            continue
        if choice == "4":
            keep_running = runner.benchmark_full(optimized=False)
            if not keep_running:
                print("Exiting.")
                return
            continue
        if choice == "5":
            keep_running = runner.benchmark_full(optimized=True)
            if not keep_running:
                print("Exiting.")
                return
            continue
        print("Invalid option.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(130)
