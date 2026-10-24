"""Strict CSV loading, timestamp parsing, and evidence provenance."""

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path


class InputError(ValueError):
    pass


def timestamp(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError("timezone required")
        return result
    except (ValueError, AttributeError) as exc:
        raise InputError(f"Invalid timezone-aware timestamp: {value!r}") from exc


def boolean(value):
    if value not in ("true", "false"):
        raise InputError(f"Expected true or false, got {value!r}")
    return value == "true"


def json_value(value, kind):
    try:
        result = json.loads(value)
    except (ValueError, TypeError) as exc:
        raise InputError(f"Invalid JSON cell: {value!r}") from exc
    if not isinstance(result, kind):
        raise InputError(f"Expected JSON {kind.__name__}")
    return result


def read_csv(path, required=(), optional=False):
    path = Path(path)
    if optional and not path.exists():
        return []
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            headers = reader.fieldnames or []
            missing = set(required) - set(headers)
            if missing or len(headers) != len(set(headers)):
                raise InputError(f"{path.name}: missing or duplicated headers: {sorted(missing)}")
            rows = []
            previous_end = reader.line_num
            for row in reader:
                line = previous_end + 1
                previous_end = reader.line_num
                if None in row or any(v is None for v in row.values()):
                    raise InputError(f"{path.name}:{line}: malformed CSV row")
                row["_ref"] = f"{path.name}:{line}"
                rows.append(row)
            return rows
    except (OSError, UnicodeError) as exc:
        raise InputError(f"Cannot read {path}: {exc}") from exc


def unique(rows, key):
    seen = set()
    for row in rows:
        value = row.get(key, "")
        if not value or value in seen:
            raise InputError(f"{row['_ref']}: empty or duplicate {key}")
        seen.add(value)


def manifest(root):
    """Hash inputs without copying their content into logs."""
    root = Path(root)
    return [{"file": p.relative_to(root).as_posix(), "bytes": p.stat().st_size,
             "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in sorted(root.rglob("*")) if p.is_file()]


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path, rows, columns):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(row[k], ensure_ascii=False) if isinstance(row.get(k), (list, dict))
                             else row.get(k, "") for k in columns})
