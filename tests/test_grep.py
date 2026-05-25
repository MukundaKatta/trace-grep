"""Tests for trace-grep."""

import json
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

import pytest
from trace_grep import GrepMatch, TraceGrepError, grep_events, grep_field, grep_file, grep_text


EVENTS = [
    {"kind": "llm_call", "name": "research", "cost_usd": 0.01, "lane": "supervisor"},
    {"kind": "tool_call", "name": "web_search", "cost_usd": 0.0, "lane": "worker-1"},
    {"kind": "tool_call", "name": "read_file", "cost_usd": 0.0, "lane": "worker-1", "error": "timeout"},
    {"kind": "llm_call", "name": "synthesis", "cost_usd": 0.05, "lane": "supervisor"},
    {"kind": "log", "name": "checkpoint", "cost_usd": 0.0, "lane": "supervisor"},
]


# ---------------------------------------------------------------------------
# pattern (full-text search)
# ---------------------------------------------------------------------------

def test_pattern_finds_matching():
    matches = grep_events(EVENTS, pattern="web_search")
    assert len(matches) == 1
    assert matches[0].event["name"] == "web_search"


def test_pattern_case_insensitive():
    matches = grep_events(EVENTS, pattern="WEB_SEARCH")
    assert len(matches) == 1


def test_pattern_no_match():
    matches = grep_events(EVENTS, pattern="nonexistent_xyz")
    assert matches == []


def test_pattern_multiple_matches():
    matches = grep_events(EVENTS, pattern="worker")
    # worker-1 appears in lane for events 1 and 2
    assert len(matches) == 2


def test_pattern_returns_grepmatches():
    matches = grep_events(EVENTS, pattern="web_search")
    assert isinstance(matches[0], GrepMatch)
    assert matches[0].index == 1


# ---------------------------------------------------------------------------
# field + value
# ---------------------------------------------------------------------------

def test_field_value_exact():
    matches = grep_events(EVENTS, field="kind", value="tool_call")
    assert len(matches) == 2


def test_field_value_no_match():
    matches = grep_events(EVENTS, field="kind", value="unknown")
    assert matches == []


def test_field_value_float():
    matches = grep_events(EVENTS, field="cost_usd", value=0.05)
    assert len(matches) == 1
    assert matches[0].event["name"] == "synthesis"


def test_field_without_value_checks_existence():
    matches = grep_events(EVENTS, field="error")
    assert len(matches) == 1
    assert matches[0].event["name"] == "read_file"


# ---------------------------------------------------------------------------
# value_contains
# ---------------------------------------------------------------------------

def test_value_contains_in_field():
    # "research" also contains "search", so 2 matches: research + web_search
    matches = grep_events(EVENTS, field="name", value_contains="search")
    assert len(matches) == 2
    names = {m.event["name"] for m in matches}
    assert "web_search" in names
    assert "research" in names


def test_value_contains_case_insensitive():
    matches = grep_events(EVENTS, field="name", value_contains="SEARCH")
    assert len(matches) == 2


def test_value_contains_no_field():
    # Search all fields
    matches = grep_events(EVENTS, value_contains="supervisor")
    assert len(matches) == 3  # 3 supervisor events


# ---------------------------------------------------------------------------
# value_regex
# ---------------------------------------------------------------------------

def test_value_regex_in_field():
    matches = grep_events(EVENTS, field="name", value_regex=r"^(web|read)")
    assert len(matches) == 2


def test_value_regex_no_field():
    matches = grep_events(EVENTS, value_regex=r"worker-\d")
    assert len(matches) == 2


def test_value_regex_invalid_raises():
    with pytest.raises(TraceGrepError, match="invalid regex"):
        grep_events(EVENTS, value_regex="[invalid")


# ---------------------------------------------------------------------------
# has_field
# ---------------------------------------------------------------------------

def test_has_field_present():
    matches = grep_events(EVENTS, has_field="error")
    assert len(matches) == 1


def test_has_field_absent():
    matches = grep_events(EVENTS, has_field="nonexistent")
    assert matches == []


# ---------------------------------------------------------------------------
# has_error
# ---------------------------------------------------------------------------

def test_has_error_true():
    matches = grep_events(EVENTS, has_error=True)
    assert len(matches) == 1
    assert matches[0].event["name"] == "read_file"


def test_has_error_false():
    matches = grep_events(EVENTS, has_error=False)
    assert len(matches) == 4  # 5 - 1 with error


# ---------------------------------------------------------------------------
# invert
# ---------------------------------------------------------------------------

def test_invert_pattern():
    matches = grep_events(EVENTS, pattern="tool_call", invert=True)
    # Events not containing "tool_call" anywhere
    for m in matches:
        assert "tool_call" not in str(m.event)


def test_invert_field_value():
    matches = grep_events(EVENTS, field="kind", value="tool_call", invert=True)
    assert all(m.event["kind"] != "tool_call" for m in matches)
    assert len(matches) == 3


# ---------------------------------------------------------------------------
# matched_fields
# ---------------------------------------------------------------------------

def test_matched_fields_populated():
    matches = grep_events(EVENTS, field="kind", value="tool_call")
    for m in matches:
        assert "kind" in m.matched_fields


def test_index_correct():
    matches = grep_events(EVENTS, field="name", value="web_search")
    assert matches[0].index == 1


# ---------------------------------------------------------------------------
# grep_text shorthand
# ---------------------------------------------------------------------------

def test_grep_text():
    matches = grep_text(EVENTS, "supervisor")
    assert len(matches) == 3


def test_grep_text_invert():
    matches = grep_text(EVENTS, "supervisor", invert=True)
    assert len(matches) == 2


# ---------------------------------------------------------------------------
# grep_field shorthand
# ---------------------------------------------------------------------------

def test_grep_field_exact():
    matches = grep_field(EVENTS, "kind", "llm_call")
    assert len(matches) == 2


def test_grep_field_contains():
    # "research" and "web_search" both contain "search"
    matches = grep_field(EVENTS, "name", contains="search")
    assert len(matches) == 2


def test_grep_field_regex():
    matches = grep_field(EVENTS, "lane", regex=r"worker-\d")
    assert len(matches) == 2


# ---------------------------------------------------------------------------
# grep_file
# ---------------------------------------------------------------------------

def test_grep_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for e in EVENTS:
            f.write(json.dumps(e) + "\n")
        path = f.name
    try:
        matches = grep_file(path, pattern="tool_call")
        assert len(matches) == 2
    finally:
        Path(path).unlink(missing_ok=True)


def test_grep_file_missing_raises():
    with pytest.raises(TraceGrepError, match="not found"):
        grep_file("/tmp/__no_trace__.jsonl", pattern="x")


def test_grep_file_invalid_json_raises():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write("not json\n")
        path = f.name
    try:
        with pytest.raises(TraceGrepError, match="invalid JSON"):
            grep_file(path, pattern="x")
    finally:
        Path(path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Multiple criteria (AND)
# ---------------------------------------------------------------------------

def test_and_field_and_pattern():
    matches = grep_events(EVENTS, field="kind", value="tool_call", pattern="worker")
    # tool_call events that also contain "worker" somewhere
    assert len(matches) == 2


def test_and_field_and_has_error():
    matches = grep_events(EVENTS, field="kind", value="tool_call", has_error=True)
    assert len(matches) == 1
    assert matches[0].event["name"] == "read_file"


# ---------------------------------------------------------------------------
# Empty events
# ---------------------------------------------------------------------------

def test_empty_events():
    assert grep_events([], pattern="anything") == []
