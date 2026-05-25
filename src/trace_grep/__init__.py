"""trace-grep: grep JSONL agent trace events by field value patterns.

Public API:
    grep_events(events, *, pattern, field, value, ...) -> list[GrepMatch]
    grep_file(source, ...) -> list[GrepMatch]
    grep_text(events, text) -> list[GrepMatch]
    grep_field(events, field, value, ...) -> list[GrepMatch]
    GrepMatch      — event, index, matched_fields
    TraceGrepError — base exception
"""

from .core import GrepMatch, TraceGrepError, grep_events, grep_field, grep_file, grep_text

__all__ = ["grep_events", "grep_file", "grep_text", "grep_field", "GrepMatch", "TraceGrepError"]
__version__ = "0.1.0"
