"""Tests for trace-grep (standard-library ``unittest`` only).

Run with::

    python3 -m unittest discover -s tests
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from trace_grep import (  # noqa: E402
    GrepMatch,
    TraceGrepError,
    grep_events,
    grep_field,
    grep_file,
    grep_text,
)


EVENTS = [
    {"kind": "llm_call", "name": "research", "cost_usd": 0.01, "lane": "supervisor"},
    {"kind": "tool_call", "name": "web_search", "cost_usd": 0.0, "lane": "worker-1"},
    {"kind": "tool_call", "name": "read_file", "cost_usd": 0.0, "lane": "worker-1", "error": "timeout"},
    {"kind": "llm_call", "name": "synthesis", "cost_usd": 0.05, "lane": "supervisor"},
    {"kind": "log", "name": "checkpoint", "cost_usd": 0.0, "lane": "supervisor"},
]


class PatternTests(unittest.TestCase):
    def test_pattern_finds_matching(self):
        matches = grep_events(EVENTS, pattern="web_search")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].event["name"], "web_search")

    def test_pattern_case_insensitive(self):
        self.assertEqual(len(grep_events(EVENTS, pattern="WEB_SEARCH")), 1)

    def test_pattern_no_match(self):
        self.assertEqual(grep_events(EVENTS, pattern="nonexistent_xyz"), [])

    def test_pattern_multiple_matches(self):
        # "worker" appears in lane for events 1 and 2.
        self.assertEqual(len(grep_events(EVENTS, pattern="worker")), 2)

    def test_pattern_returns_grepmatches(self):
        matches = grep_events(EVENTS, pattern="web_search")
        self.assertIsInstance(matches[0], GrepMatch)
        self.assertEqual(matches[0].index, 1)

    def test_pattern_searches_nested_values(self):
        events = [{"meta": {"lane": "worker"}}, {"meta": {"lane": "supervisor"}}]
        matches = grep_events(events, pattern="worker")
        self.assertEqual(len(matches), 1)


class FieldValueTests(unittest.TestCase):
    def test_field_value_exact(self):
        self.assertEqual(len(grep_events(EVENTS, field="kind", value="tool_call")), 2)

    def test_field_value_no_match(self):
        self.assertEqual(grep_events(EVENTS, field="kind", value="unknown"), [])

    def test_field_value_float(self):
        matches = grep_events(EVENTS, field="cost_usd", value=0.05)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].event["name"], "synthesis")

    def test_field_value_zero(self):
        # 0.0 is falsy but a legitimate exact value.
        matches = grep_events(EVENTS, field="cost_usd", value=0.0)
        self.assertEqual(len(matches), 3)

    def test_field_value_false(self):
        events = [{"flag": False}, {"flag": True}]
        matches = grep_events(events, field="flag", value=False)
        self.assertEqual(len(matches), 1)

    def test_field_without_value_checks_existence(self):
        matches = grep_events(EVENTS, field="error")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].event["name"], "read_file")

    def test_field_present_with_falsy_value_still_matches(self):
        events = [{"count": 0}, {"other": 1}]
        matches = grep_events(events, field="count")
        self.assertEqual(len(matches), 1)


class ValueContainsTests(unittest.TestCase):
    def test_value_contains_in_field(self):
        # "research" and "web_search" both contain "search".
        matches = grep_events(EVENTS, field="name", value_contains="search")
        names = {m.event["name"] for m in matches}
        self.assertEqual(names, {"web_search", "research"})

    def test_value_contains_case_insensitive(self):
        self.assertEqual(
            len(grep_events(EVENTS, field="name", value_contains="SEARCH")), 2
        )

    def test_value_contains_no_field(self):
        # Search across all fields.
        self.assertEqual(len(grep_events(EVENTS, value_contains="supervisor")), 3)


class ValueRegexTests(unittest.TestCase):
    def test_value_regex_in_field(self):
        matches = grep_events(EVENTS, field="name", value_regex=r"^(web|read)")
        self.assertEqual(len(matches), 2)

    def test_value_regex_no_field(self):
        self.assertEqual(len(grep_events(EVENTS, value_regex=r"worker-\d")), 2)

    def test_value_regex_invalid_raises(self):
        with self.assertRaisesRegex(TraceGrepError, "invalid regex"):
            grep_events(EVENTS, value_regex="[invalid")


class HasFieldTests(unittest.TestCase):
    def test_has_field_present(self):
        self.assertEqual(len(grep_events(EVENTS, has_field="error")), 1)

    def test_has_field_absent(self):
        self.assertEqual(grep_events(EVENTS, has_field="nonexistent"), [])

    def test_has_field_null_value_treated_as_absent(self):
        events = [{"count": None}, {"count": 5}]
        matches = grep_events(events, has_field="count")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].event["count"], 5)


class HasErrorTests(unittest.TestCase):
    def test_has_error_true(self):
        matches = grep_events(EVENTS, has_error=True)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].event["name"], "read_file")

    def test_has_error_false(self):
        self.assertEqual(len(grep_events(EVENTS, has_error=False)), 4)

    def test_has_error_empty_string_is_not_an_error(self):
        events = [{"error": ""}, {"error": "boom"}]
        self.assertEqual(len(grep_events(events, has_error=True)), 1)
        self.assertEqual(len(grep_events(events, has_error=False)), 1)

    def test_has_error_alternate_keys(self):
        events = [{"err": "x"}, {"exception": "y"}, {"ok": 1}]
        self.assertEqual(len(grep_events(events, has_error=True)), 2)


class InvertTests(unittest.TestCase):
    def test_invert_pattern(self):
        matches = grep_events(EVENTS, pattern="tool_call", invert=True)
        for m in matches:
            self.assertNotIn("tool_call", str(m.event))

    def test_invert_field_value(self):
        matches = grep_events(EVENTS, field="kind", value="tool_call", invert=True)
        self.assertTrue(all(m.event["kind"] != "tool_call" for m in matches))
        self.assertEqual(len(matches), 3)

    def test_invert_has_empty_matched_fields(self):
        matches = grep_events(EVENTS, field="kind", value="tool_call", invert=True)
        self.assertTrue(all(m.matched_fields == {} for m in matches))


class MatchedFieldsTests(unittest.TestCase):
    def test_matched_fields_populated(self):
        for m in grep_events(EVENTS, field="kind", value="tool_call"):
            self.assertIn("kind", m.matched_fields)

    def test_index_correct(self):
        matches = grep_events(EVENTS, field="name", value="web_search")
        self.assertEqual(matches[0].index, 1)


class ShorthandTests(unittest.TestCase):
    def test_grep_text(self):
        self.assertEqual(len(grep_text(EVENTS, "supervisor")), 3)

    def test_grep_text_invert(self):
        self.assertEqual(len(grep_text(EVENTS, "supervisor", invert=True)), 2)

    def test_grep_field_exact(self):
        self.assertEqual(len(grep_field(EVENTS, "kind", "llm_call")), 2)

    def test_grep_field_contains(self):
        self.assertEqual(len(grep_field(EVENTS, "name", contains="search")), 2)

    def test_grep_field_regex(self):
        self.assertEqual(len(grep_field(EVENTS, "lane", regex=r"worker-\d")), 2)


class GrepFileTests(unittest.TestCase):
    def _write_jsonl(self, lines):
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")
        self.addCleanup(Path(path).unlink, missing_ok=True)
        return path

    def test_grep_file(self):
        path = self._write_jsonl(json.dumps(e) for e in EVENTS)
        self.assertEqual(len(grep_file(path, pattern="tool_call")), 2)

    def test_grep_file_skips_blank_lines(self):
        path = self._write_jsonl(['{"kind": "a"}', "", "   ", '{"kind": "b"}'])
        # Blank lines are ignored, leaving 2 parsed events; no filters -> all match.
        self.assertEqual(len(grep_file(path)), 2)
        self.assertEqual(len(grep_file(path, field="kind", value="a")), 1)

    def test_grep_file_missing_raises(self):
        with self.assertRaisesRegex(TraceGrepError, "not found"):
            grep_file("/tmp/__no_trace__.jsonl", pattern="x")

    def test_grep_file_invalid_json_raises(self):
        path = self._write_jsonl(["not json"])
        with self.assertRaisesRegex(TraceGrepError, "invalid JSON"):
            grep_file(path, pattern="x")

    def test_grep_file_non_object_line_raises(self):
        # A valid-JSON but non-object line (bare string/array) must be rejected
        # with a clear error rather than crashing later in matching.
        path = self._write_jsonl(['{"k": "v"}', '"bare string"'])
        with self.assertRaisesRegex(TraceGrepError, "expected a JSON object"):
            grep_file(path, pattern="v")


class CombinedCriteriaTests(unittest.TestCase):
    def test_and_field_and_pattern(self):
        matches = grep_events(
            EVENTS, field="kind", value="tool_call", pattern="worker"
        )
        self.assertEqual(len(matches), 2)

    def test_and_field_and_has_error(self):
        matches = grep_events(
            EVENTS, field="kind", value="tool_call", has_error=True
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].event["name"], "read_file")


class EdgeCaseTests(unittest.TestCase):
    def test_empty_events(self):
        self.assertEqual(grep_events([], pattern="anything"), [])

    def test_no_filters_matches_all(self):
        self.assertEqual(len(grep_events(EVENTS)), len(EVENTS))

    def test_non_dict_event_raises(self):
        with self.assertRaisesRegex(TraceGrepError, "must be a dict"):
            grep_events([{"k": "v"}, "not a dict"], pattern="v")

    def test_non_dict_event_reports_index(self):
        with self.assertRaisesRegex(TraceGrepError, "index 1"):
            grep_events([{"k": "v"}, 42], pattern="v")


if __name__ == "__main__":
    unittest.main()
