import re
from collections import OrderedDict
from collections.abc import Iterator
from typing import Any

from anyio import to_thread
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from relay.domain.errors import FieldError, ValidationFailedError

_MAX_REPORTED_ERRORS = 20
_CACHE_SIZE = 1024
_MAX_PATTERN_LENGTH = 256
# A quantified group that itself contains a quantifier, e.g. (a+)+ or (\w*)*: the classic
# shape of catastrophic backtracking. Tenant patterns run on our CPU, so refuse them up front.
_NESTED_QUANTIFIER = re.compile(r"\((?:[^()\\]|\\.)*[+*}](?:[^()\\]|\\.)*\)(?:[+*]|\{\d*,)")


def _patterns(node: Any, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}/{key}"
            if key == "pattern" and isinstance(value, str):
                yield here, value
            elif key == "patternProperties" and isinstance(value, dict):
                yield from ((f"{here}/{name}", name) for name in value)
            yield from _patterns(value, here)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from _patterns(item, f"{path}/{index}")


def _risky_patterns(schema: dict[str, Any]) -> list[FieldError]:
    problems: list[FieldError] = []
    for path, pattern in _patterns(schema):
        if len(pattern) > _MAX_PATTERN_LENGTH:
            problems.append(
                {"path": path, "message": f"pattern is longer than {_MAX_PATTERN_LENGTH} chars"}
            )
        elif _NESTED_QUANTIFIER.search(pattern):
            problems.append(
                {"path": path, "message": "nested quantifiers can backtrack catastrophically"}
            )
    return problems


def ensure_valid_schema(schema: dict[str, Any]) -> None:
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        location = "/".join(str(p) for p in exc.path) or "(root)"
        raise ValidationFailedError(
            "payload_schema is not a valid JSON Schema (draft 2020-12)",
            details=[{"path": location, "message": exc.message}],
        ) from exc
    risky = _risky_patterns(schema)
    if risky:
        raise ValidationFailedError(
            "payload_schema contains regular expressions Relay will not evaluate", details=risky
        )


class ValidatorCache:
    """Compiled validators keyed by (event type id, schema version). Bumping the version
    on every schema change is what keeps this cache coherent across API processes."""

    def __init__(self, size: int = _CACHE_SIZE) -> None:
        self._size = size
        self._entries: OrderedDict[tuple[str, int], Draft202012Validator] = OrderedDict()

    def get(self, event_type_id: str, version: int, schema: dict[str, Any]) -> Draft202012Validator:
        key = (event_type_id, version)
        validator = self._entries.get(key)
        if validator is None:
            validator = Draft202012Validator(
                schema, format_checker=Draft202012Validator.FORMAT_CHECKER
            )
            self._entries[key] = validator
            if len(self._entries) > self._size:
                self._entries.popitem(last=False)
        else:
            self._entries.move_to_end(key)
        return validator


_validators = ValidatorCache()


async def validate_payload_async(
    event_type_id: str, version: int, schema: dict[str, Any], payload: dict[str, Any]
) -> None:
    """Validation can be CPU-heavy for large payloads; run it off the event loop."""
    await to_thread.run_sync(validate_payload, event_type_id, version, schema, payload)


def validate_payload(
    event_type_id: str, version: int, schema: dict[str, Any], payload: dict[str, Any]
) -> None:
    validator = _validators.get(event_type_id, version, schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(map(str, e.absolute_path)))
    if errors:
        raise ValidationFailedError(
            "payload does not match the event type schema",
            details=[
                {
                    "path": "/" + "/".join(str(p) for p in error.absolute_path),
                    "message": error.message,
                }
                for error in errors[:_MAX_REPORTED_ERRORS]
            ],
        )
