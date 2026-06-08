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

Each non-blank line of the file must be a JSON **object**. Blank lines are
skipped; a malformed line or a line that is valid JSON but not an object
(e.g. a bare string or array) raises `TraceGrepError` with the offending
line number.

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

## Behaviour notes

- All filters are **AND**-combined; an event must satisfy every supplied
  criterion to match.
- `pattern`, `value_contains`, and `value_regex` are **case-insensitive** and
  match against the string form of each value.
- `value`, `value_contains`, and `value_regex` search a single `field` when
  one is given, otherwise they scan every field of the event.
- `has_error` treats `error`, `err`, and `exception` as error fields, and a
  *falsy* value (e.g. `""`, `0`, `null`) counts as **no error**.
- `invert=True` returns the events that do **not** match; their
  `matched_fields` is empty.

## Development

The library has no runtime dependencies and the test suite uses only the
Python standard library (`unittest`):

```bash
git clone https://github.com/MukundaKatta/trace-grep
cd trace-grep
python -m unittest discover -s tests
```

CI runs the same command on Python 3.10–3.13 (see
`.github/workflows/ci.yml`).

## License

MIT
