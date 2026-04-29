#!/usr/bin/env python3
"""Validate LLM warning contract examples with a small schema subset.

This avoids adding a jsonschema dependency during the contracts-only phase.
It validates the subset used by the local contract schemas: object, array,
string, number, boolean, required, properties, items, enum, minimum, maximum,
and additionalProperties.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent


PAIRS = [
    ("schemas/rag_chunk.schema.json", "examples/rag_chunk.example.json"),
    ("schemas/table_analysis_facts.schema.json", "examples/table_analysis_facts.example.json"),
    ("schemas/table_warning_diagnostics.schema.json", "examples/table_warning_diagnostics.example.json"),
    (
        "schemas/table_result_with_optional_diagnostics.schema.json",
        "examples/table_result_without_diagnostics.example.json",
    ),
    (
        "schemas/table_result_with_optional_diagnostics.schema.json",
        "examples/table_result_with_diagnostics.example.json",
    ),
]


class ValidationError(Exception):
    pass


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def type_matches(expected: str, value: Any) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    return True


def validate(schema: dict[str, Any], value: Any, path: str = "$") -> None:
    expected_type = schema.get("type")
    if expected_type and not type_matches(expected_type, value):
        raise ValidationError(f"{path}: expected {expected_type}, got {type(value).__name__}")

    if "enum" in schema and value not in schema["enum"]:
        raise ValidationError(f"{path}: value {value!r} not in enum {schema['enum']!r}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ValidationError(f"{path}: value {value!r} below minimum {schema['minimum']!r}")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValidationError(f"{path}: value {value!r} above maximum {schema['maximum']!r}")

    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                raise ValidationError(f"{path}: missing required key {key!r}")

        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(properties))
            if extra:
                raise ValidationError(f"{path}: unexpected keys {extra!r}")

        for key, child in value.items():
            if key in properties:
                validate(properties[key], child, f"{path}.{key}")

    if isinstance(value, list) and "items" in schema:
        for idx, item in enumerate(value):
            validate(schema["items"], item, f"{path}[{idx}]")


def main() -> int:
    for schema_rel, example_rel in PAIRS:
        schema = load_json(ROOT / schema_rel)
        example = load_json(ROOT / example_rel)
        validate(schema, example)
        print(f"OK {example_rel} matches {schema_rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

