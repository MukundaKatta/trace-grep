"""Grep JSONL agent traces by field value patterns."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class TraceGrepError(Exception):
    """Raised on unrecoverable grep failures."""


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def _load_jsonl(source: str | Path) -> list[dict[str, Any]]:
    p = Path(source)
    if not p.exists():
        raise TraceGrepError(f"file not found: {p}")
    events: list[dict[str, Any]] = []
    for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise TraceGrepError(f"{p}:{lineno}: invalid JSON: {e}") from e
    return events


# ---------------------------------------------------------------------------
# GrepMatch
# ---------------------------------------------------------------------------

@dataclass
class GrepMatch:
    """A single event that matched the grep query.

    Attributes:
        event: the full event dict.
        index: 0-based position in the original event list.
        matched_fields: dict of {field: value} for fields that matched.
    """

    event: dict[str, Any]
    index: int
    matched_fields: dict[str, Any]


# ---------------------------------------------------------------------------
# Core grep function
# ---------------------------------------------------------------------------

def grep_events(
    events: list[dict[str, Any]],
    *,
    pattern: str | None = None,
    field: str | None = None,
    value: Any = None,
    value_contains: str | None = None,
    value_regex: str | None = None,
    has_field: str | None = None,
    has_error: bool | None = None,
    invert: bool = False,
) -> list[GrepMatch]:
    """Search JSONL events by field and value criteria.

    Each argument is an optional filter; all provided filters must match
    (AND logic). Use ``invert=True`` to return non-matching events.

    Args:
        events: list of event dicts.
        pattern: search all field values (as strings) for this substring.
            Case-insensitive.
        field: when combined with value/value_contains/value_regex, restrict
            to this specific field. When used alone, matches events that have
            this field.
        value: exact value match for ``field``.
        value_contains: substring match in ``str(field_value)``.
        value_regex: regex match in ``str(field_value)``.
        has_field: event must have this field (non-None).
        has_error: if True, match events with a non-empty error/err/exception
            field. If False, match events without.
        invert: return events that do NOT match all criteria.

    Returns:
        List of GrepMatch in original order.
    """
    compiled_regex: re.Pattern | None = None
    if value_regex is not None:
        try:
            compiled_regex = re.compile(value_regex, re.IGNORECASE)
        except re.error as e:
            raise TraceGrepError(f"invalid regex '{value_regex}': {e}") from e

    results: list[GrepMatch] = []

    for idx, event in enumerate(events):
        matched = _matches(
            event,
            pattern=pattern,
            field=field,
            value=value,
            value_contains=value_contains,
            compiled_regex=compiled_regex,
            has_field=has_field,
            has_error=has_error,
        )
        if matched is not None and not invert:
            results.append(GrepMatch(event=event, index=idx, matched_fields=matched))
        elif matched is None and invert:
            results.append(GrepMatch(event=event, index=idx, matched_fields={}))

    return results


def _matches(
    event: dict[str, Any],
    *,
    pattern: str | None,
    field: str | None,
    value: Any,
    value_contains: str | None,
    compiled_regex: re.Pattern | None,
    has_field: str | None,
    has_error: bool | None,
) -> dict[str, Any] | None:
    """Return matched_fields dict if event matches all criteria, else None."""
    matched: dict[str, Any] = {}

    # Pattern: search all values
    if pattern is not None:
        low = pattern.lower()
        found = False
        for k, v in event.items():
            if low in str(v).lower():
                matched[k] = v
                found = True
        if not found:
            return None

    # has_field
    if has_field is not None:
        if event.get(has_field) is None:
            return None
        matched[has_field] = event[has_field]

    # has_error
    if has_error is not None:
        error_val = (
            event.get("error") or event.get("err") or event.get("exception")
        )
        has = bool(error_val)
        if has != has_error:
            return None
        if has:
            key = next(
                (k for k in ("error", "err", "exception") if event.get(k)), None
            )
            if key:
                matched[key] = event[key]

    # Field-based filters
    if field is not None:
        field_val = event.get(field)
        if field_val is None:
            return None
        str_val = str(field_val)

        if value is not None and field_val != value:
            return None

        if value_contains is not None and value_contains.lower() not in str_val.lower():
            return None

        if compiled_regex is not None and not compiled_regex.search(str_val):
            return None

        matched[field] = field_val
    else:
        # Value filters without a specific field — search all fields
        if value is not None:
            found = any(v == value for v in event.values())
            if not found:
                return None

        if value_contains is not None:
            low = value_contains.lower()
            found = any(low in str(v).lower() for v in event.values())
            if not found:
                return None

        if compiled_regex is not None:
            found = any(compiled_regex.search(str(v)) for v in event.values())
            if not found:
                return None

    return matched


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------

def grep_file(
    source: str | Path,
    **kwargs: Any,
) -> list[GrepMatch]:
    """Load a JSONL file and grep its events."""
    events = _load_jsonl(source)
    return grep_events(events, **kwargs)


def grep_text(
    events: list[dict[str, Any]],
    text: str,
    *,
    invert: bool = False,
) -> list[GrepMatch]:
    """Shorthand: search all field values for a substring."""
    return grep_events(events, pattern=text, invert=invert)


def grep_field(
    events: list[dict[str, Any]],
    field: str,
    value: Any = None,
    *,
    contains: str | None = None,
    regex: str | None = None,
    invert: bool = False,
) -> list[GrepMatch]:
    """Shorthand: search a specific field by exact value, substring, or regex."""
    return grep_events(
        events,
        field=field,
        value=value,
        value_contains=contains,
        value_regex=regex,
        invert=invert,
    )
