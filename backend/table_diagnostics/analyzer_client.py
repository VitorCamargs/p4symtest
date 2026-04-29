import json
import os
import socket
import urllib.error
import urllib.request

FACTS_VERSION = "2026-04-llm-warning-v1"
PROMPT_VERSION = "table-warning-v1"

_REQUIRED_DIAGNOSTIC_KEYS = {
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


def _env_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def table_diagnostics_enabled(env=None):
    if env is None:
        env = os.environ
    explicit = env.get("P4SYMTEST_TABLE_DIAGNOSTICS_ENABLED")
    if explicit is None:
        explicit = env.get("TABLE_DIAGNOSTICS_ENABLED")
    return _env_bool(explicit)


def _analyzer_url(env):
    base_url = (
        env.get("P4SYMTEST_LLM_ANALYZER_URL")
        or env.get("LLM_ANALYZER_URL")
        or "http://llm-analyzer:8000"
    )
    endpoint = (
        env.get("P4SYMTEST_LLM_ANALYZER_ENDPOINT")
        or env.get("LLM_ANALYZER_ENDPOINT")
        or "/analyze/table-warning"
    )
    return base_url.rstrip("/") + "/" + endpoint.lstrip("/")


def _analyzer_timeout(env):
    value = (
        env.get("P4SYMTEST_LLM_ANALYZER_TIMEOUT_SECONDS")
        or env.get("LLM_ANALYZER_TIMEOUT_SECONDS")
        or "2.0"
    )
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 2.0
    return max(parsed, 0.1)


def _diagnostics_mode(env):
    value = (
        env.get("P4SYMTEST_TABLE_DIAGNOSTICS_MODE")
        or env.get("TABLE_DIAGNOSTICS_MODE")
        or env.get("LLM_ANALYZER_DIAGNOSTICS_MODE")
    )
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def diagnostics_unavailable(table_name, reason, detail=""):
    observed = "diagnostics_unavailable"
    if reason:
        observed = f"{observed}: {reason}"
    if detail:
        observed = f"{observed} ({str(detail)[:240]})"
    return {
        "diagnostics_version": FACTS_VERSION,
        "table_name": table_name,
        "expected_behavior": "Diagnostics unavailable.",
        "observed_behavior": observed,
        "warnings": [],
        "inconclusive": True,
        "evidence": [],
        "model_info": {
            "provider": "backend",
            "model": "diagnostics_unavailable",
            "prompt_version": PROMPT_VERSION,
        },
        "rag_context_ids": [],
    }


def _validate_diagnostics_payload(payload):
    if not isinstance(payload, dict):
        return False
    if not _REQUIRED_DIAGNOSTIC_KEYS.issubset(payload.keys()):
        return False
    if not isinstance(payload.get("warnings"), list):
        return False
    if not isinstance(payload.get("evidence"), list):
        return False
    if not isinstance(payload.get("model_info"), dict):
        return False
    if not isinstance(payload.get("rag_context_ids"), list):
        return False
    if not isinstance(payload.get("inconclusive"), bool):
        return False
    return True


def request_table_diagnostics(facts, env=None, urlopen=None):
    if env is None:
        env = os.environ
    if not table_diagnostics_enabled(env):
        return None

    table_name = facts.get("table_name", "") if isinstance(facts, dict) else ""
    url = _analyzer_url(env)
    timeout = _analyzer_timeout(env)
    diagnostics_mode = _diagnostics_mode(env)
    payload = (
        {"facts": facts, "diagnostics_mode": diagnostics_mode}
        if diagnostics_mode
        else facts
    )
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    opener = urlopen or urllib.request.urlopen

    try:
        with opener(request, timeout=timeout) as response:
            raw = response.read()
    except (TimeoutError, socket.timeout) as exc:
        return diagnostics_unavailable(table_name, "timeout", exc)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        return diagnostics_unavailable(table_name, "request_error", exc)

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return diagnostics_unavailable(table_name, "invalid_json", exc)

    if not _validate_diagnostics_payload(payload):
        return diagnostics_unavailable(table_name, "invalid_payload")
    return payload
