"""Canonical metadata model + format-agnostic CSV parsing/validation."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MetadataModel:
    title: str = ""
    description: str = ""
    keywords: list[str] = field(default_factory=list)
    author: str = ""
    copyright: str = ""
    rating: int = 5

    def active_fields(self, write_fields: list[str] | None = None) -> dict:
        """Return only the fields the user enabled in settings."""
        data = {
            "title": self.title,
            "description": self.description or self.title,
            "keywords": list(self.keywords),
            "author": self.author,
            "copyright": self.copyright,
            "rating": self.rating,
        }
        if not write_fields:
            return data
        wanted = {w.strip().lower() for w in write_fields}
        return {k: v for k, v in data.items() if k in wanted}


@dataclass
class CsvRow:
    lineno: int
    filename: str
    metadata: MetadataModel


@dataclass
class CsvValidation:
    ok: bool
    total_rows: int
    checks: list[tuple[bool, str]]
    errors: list[str]
    rows: list[CsvRow]


def _normalize_columns(names: list[str]) -> dict[str, str]:
    """Map normalized column name -> original header."""
    mapping: dict[str, str] = {}
    for raw in names:
        key = (raw or "").strip().lower().lstrip("\ufeff")
        if key and key not in mapping:
            mapping[key] = raw
    return mapping


def _parse_keywords(value: object) -> list[str]:
    if value is None:
        return []
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return []
    return [k.strip() for k in text.split(",") if k.strip()]


def load_csv(path: str | Path, default_rating: int = 5) -> CsvValidation:
    """Load + validate a metadata CSV (UTF-8 / UTF-8-SIG, case-insensitive headers)."""
    path = Path(path)
    checks: list[tuple[bool, str]] = []
    errors: list[str] = []

    def fail(msg: str) -> CsvValidation:
        errors.append(msg)
        return CsvValidation(ok=False, total_rows=0, checks=checks, errors=errors, rows=[])

    if not path.is_file():
        return fail(f"CSV file not found: {path}")
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            # Sniff dialect but always tolerate plain commas
            sample = fh.read(8192)
            fh.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t"])
                delimiter = dialect.delimiter
            except Exception:
                delimiter = ","
            reader = csv.DictReader(fh, delimiter=delimiter)
            if not reader.fieldnames:
                return fail("The CSV file has no header row.")
            mapping = _normalize_columns(list(reader.fieldnames))
            checks.append((True, "CSV loaded"))
            for required, label in (("filename", "Filename"), ("title", "Title"),
                                    ("description", "Description"), ("keywords", "Keywords")):
                found = required in mapping
                checks.append((found, f"{label} column {'found' if found else 'missing'}"))
            if "filename" not in mapping:
                return fail(
                    'Required "filename" column not found.',
                )
            rows: list[CsvRow] = []
            seen: dict[str, int] = {}
            skipped_empty = 0
            for i, record in enumerate(reader, start=2):
                norm = {(k or "").strip().lower().lstrip("\ufeff"): v for k, v in record.items() if k}
                # Commas inside unquoted keywords create extra columns (None key) — rejoin them.
                extras = record.get(None) or []
                kw_raw = norm.get("keywords", "")
                if extras:
                    kw_raw = ",".join([str(kw_raw)] + [str(e) for e in extras])
                raw_name = norm.get("filename", "")
                name = "" if raw_name is None else str(raw_name).strip()
                if not name:
                    skipped_empty += 1
                    continue
                key = name.lower()
                seen[key] = seen.get(key, 0) + 1
                title = "" if norm.get("title") is None else str(norm.get("title")).strip()
                desc_raw = norm.get("description")
                description = "" if desc_raw is None else str(desc_raw).strip()
                if not description:
                    description = title
                rows.append(CsvRow(
                    lineno=i,
                    filename=name,
                    metadata=MetadataModel(
                        title=title,
                        description=description,
                        keywords=_parse_keywords(kw_raw),
                        author="" if norm.get("author") is None else str(norm.get("author")).strip(),
                        copyright="" if norm.get("copyright") is None else str(norm.get("copyright")).strip(),
                        rating=default_rating,
                    ),
                ))
            dupes = [k for k, c in seen.items() if c > 1]
            checks.append((True, f"{len(rows)} data rows detected"))
            if skipped_empty:
                checks.append((True, f"{skipped_empty} empty rows skipped"))
            if dupes:
                checks.append((False, f"{len(dupes)} duplicate filenames in CSV"))
                errors.append(f"Duplicate filenames found: {', '.join(dupes[:5])}" + ("..." if len(dupes) > 5 else ""))
            if "title" not in mapping:
                errors.append('Recommended "title" column is missing; SEO rename will be skipped.')
            ok = "filename" in mapping and not dupes
            return CsvValidation(ok=ok, total_rows=len(rows), checks=checks, errors=errors, rows=rows)
    except UnicodeDecodeError:
        return fail("Could not decode the CSV. Please save it as UTF-8 (or UTF-8 with BOM) and try again.")
    except Exception as exc:
        return fail(f"Could not read the CSV file: {exc}")
