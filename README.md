# trace-grep

Grep JSONL agent traces by field value patterns — substring, exact, and regex.

Zero dependencies. Python 3.10+. MIT.

## Install

```bash
pip install trace-grep
```

## Usage

```python
from trace_grep import grep_events, grep_file, grep_text, grep_field

events = load_my_events()

# Full-text search across all fields
matches = grep_text(events, "timeout")

# Exact field match
matches = grep_field(events, "kind", "tool_call")

# Substring match in a specific field
matches = grep_field(events, "name", contains="search")

# Regex match
matches = grep_field(events, "name", regex=r"^web_")

# Has error
matches = grep_events(events, has_error=True)

# Invert (find non-matching events)
matches = grep_field(events, "kind", "tool_call", invert=True)
```

## From a file

```python
from trace_grep import grep_file

matches = grep_file("logs/run.jsonl", pattern="error", has_error=True)
```

## Combine criteria (AND)

```python
matches = grep_events(
    events,
    field="kind", value="tool_call",
    has_error=True,
)
```

## GrepMatch

```python
@dataclass
class GrepMatch:
    event: dict          # the full event
    index: int           # 0-based position in the input list
    matched_fields: dict # {field: value} for matched fields
```

## API

### `grep_events(events, *, pattern, field, value, value_contains, value_regex, has_field, has_error, invert)`

Full filtering API. All arguments are optional AND-combined.

### `grep_text(events, text, *, invert=False)`

Shorthand: search all field values for a substring.

### `grep_field(events, field, value=None, *, contains, regex, invert=False)`

Shorthand: filter by a specific field.

### `grep_file(source, **kwargs)`

Load a JSONL file and apply filters.

## License

MIT
