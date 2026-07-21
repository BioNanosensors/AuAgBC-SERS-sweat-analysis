"""Format-tolerant, non-semantic Raman CSV import.

Import deliberately does not derive sample identity, concentration, replicate, or
instrument from a filename.  It only identifies the numerical axis and expands
every usable intensity column.  Scientific metadata is joined later from the
manifest.
"""

from __future__ import annotations

import csv
import hashlib
import math
import re
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .errors import ImportFormatError
from .models import Spectrum


_DELIMITERS: tuple[str, ...] = (",", "\t", ";")
_MIN_POINTS = 5


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Return a lowercase SHA-256 digest without loading the whole file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk_size):
            digest.update(block)
    return digest.hexdigest()


def _decode(raw: bytes, path: Path) -> tuple[str, str]:
    encodings = ("utf-8-sig", "utf-16", "cp1252", "latin-1")
    failures: list[str] = []
    for encoding in encodings:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError as exc:
            failures.append(f"{encoding}: byte {exc.start}")
    raise ImportFormatError(f"Could not decode {path}; attempts were {', '.join(failures)}.")


def _cells(line: str, delimiter: str) -> list[str]:
    try:
        return next(csv.reader([line], delimiter=delimiter))
    except csv.Error:
        return line.split(delimiter)


def _number(value: str, *, decimal_comma: bool = False) -> float:
    cleaned = value.strip().strip('"').replace("\u2212", "-")
    if decimal_comma and "," in cleaned and "." not in cleaned:
        cleaned = cleaned.replace(",", ".")
    if not cleaned:
        return math.nan
    try:
        result = float(cleaned)
    except ValueError:
        return math.nan
    return result if math.isfinite(result) else math.nan


def _numeric_row(line: str, delimiter: str) -> tuple[bool, int]:
    parts = _cells(line, delimiter)
    decimal_comma = delimiter != ","
    if len(parts) < 2 or not math.isfinite(_number(parts[0], decimal_comma=decimal_comma)):
        return False, 0
    count = sum(math.isfinite(_number(cell, decimal_comma=decimal_comma)) for cell in parts)
    return count >= 2, count


def _locate_data(lines: list[str], path: Path) -> tuple[str, int]:
    """Find the delimiter and first numerical row using a contiguous-run score."""
    best: tuple[int, int, int, int, str] | None = None
    for delimiter_rank, delimiter in enumerate(_DELIMITERS):
        inspected = [_numeric_row(line, delimiter) for line in lines]
        runs = [0] * len(lines)
        running = 0
        for index in range(len(lines) - 1, -1, -1):
            if inspected[index][0]:
                running += 1
            else:
                running = 0
            runs[index] = running
        for index, ((valid, width), run) in enumerate(zip(inspected, runs)):
            if not valid or run < _MIN_POINTS:
                continue
            # Prefer the longest numerical block, then a wider table, then its
            # earliest row and the conventional delimiter order above.
            proposed = (run, width, -index, -delimiter_rank, delimiter)
            if best is None or proposed > best:
                best = proposed
    if best is None:
        raise ImportFormatError(
            f"Could not find a block of at least {_MIN_POINTS} two-column numerical rows in {path}. "
            "Export the spectrum as comma-, semicolon-, or tab-delimited text."
        )
    return best[4], -best[2]


def _header_before(lines: list[str], data_start: int, delimiter: str, width: int) -> tuple[int | None, list[str]]:
    for index in range(data_start - 1, max(-1, data_start - 4), -1):
        if not lines[index].strip():
            continue
        parts = [part.strip().lstrip("#").strip() for part in _cells(lines[index], delimiter)]
        if len(parts) >= 2 and len(parts) >= width and not math.isfinite(_number(parts[0], decimal_comma=delimiter != ",")):
            names = [part or f"column_{position}" for position, part in enumerate(parts)]
            return index, names
        break
    return None, ["Raman shift cm-1"] + [f"Intensity_{index}" for index in range(1, width)]


def _unique_headers(headers: list[str], width: int) -> list[str]:
    result: list[str] = []
    counts: dict[str, int] = {}
    for index in range(width):
        base = headers[index].strip() if index < len(headers) and headers[index].strip() else f"column_{index}"
        count = counts.get(base, 0)
        counts[base] = count + 1
        result.append(base if count == 0 else f"{base}__{count + 1}")
    return result


def _metadata_from_preamble(lines: Iterable[str], delimiter: str) -> tuple[dict[str, list[str]], list[str]]:
    metadata: dict[str, list[str]] = {}
    raw_lines: list[str] = []
    for raw_line in lines:
        line = raw_line.strip().lstrip("\ufeff")
        if not line:
            continue
        raw_lines.append(line)
        pair: list[str] | None = None
        for separator in (delimiter, "\t", "=", ":"):
            if separator not in line:
                continue
            pieces = line.split(separator, 1)
            if pieces[0].strip() and not math.isfinite(_number(pieces[0])):
                pair = pieces
                break
        if pair is None:
            continue
        key = pair[0].strip().lstrip("#").strip()
        value = pair[1].strip()
        if key:
            metadata.setdefault(key, []).append(value)
    return metadata, raw_lines


def _column_selector(selector: str | int, headers: list[str]) -> int:
    if isinstance(selector, int) or str(selector).strip().isdigit():
        index = int(selector)
        if index < 1 or index >= len(headers):
            raise ImportFormatError(
                f"intensity_column index {index} is invalid; usable intensity indexes are 1..{len(headers) - 1}."
            )
        return index
    wanted = str(selector).strip()
    exact = [index for index, header in enumerate(headers) if index > 0 and header == wanted]
    if not exact:
        folded = [index for index, header in enumerate(headers) if index > 0 and header.casefold() == wanted.casefold()]
        exact = folded
    if len(exact) != 1:
        available = ", ".join(repr(item) for item in headers[1:])
        raise ImportFormatError(f"intensity_column {wanted!r} does not identify exactly one column. Available: {available}.")
    return exact[0]


def read_spectrum_file(path: str | Path, intensity_column: str | int | None = None) -> list[Spectrum]:
    """Read one CSV-like file and return one :class:`Spectrum` per intensity column.

    Portable-instrument preambles are retained under ``import_metadata``.  The
    original row order is retained so ``legacy_individual`` can reproduce the
    historical v2 script, including descending axes.
    """
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ImportFormatError(f"Spectrum file does not exist or is not a file: {source}")
    raw = source.read_bytes()
    text, encoding = _decode(raw, source)
    lines = text.splitlines()
    delimiter, data_start = _locate_data(lines, source)
    first_parts = _cells(lines[data_start], delimiter)
    width = len(first_parts)
    header_line, raw_headers = _header_before(lines, data_start, delimiter, width)
    headers = _unique_headers(raw_headers, width)
    preamble_end = header_line if header_line is not None else data_start
    vendor_metadata, preamble_lines = _metadata_from_preamble(lines[:preamble_end], delimiter)

    rows: list[list[float]] = []
    decimal_comma = delimiter != ","
    for line in lines[data_start:]:
        parts = _cells(line, delimiter)
        if len(parts) < 2:
            continue
        x_value = _number(parts[0], decimal_comma=decimal_comma)
        if not math.isfinite(x_value):
            continue
        numeric = [_number(parts[index], decimal_comma=decimal_comma) if index < len(parts) else math.nan for index in range(width)]
        rows.append(numeric)
    if len(rows) < _MIN_POINTS:
        raise ImportFormatError(f"Only {len(rows)} numerical rows were found in {source}; at least {_MIN_POINTS} are required.")

    matrix = np.asarray(rows, dtype=float)
    x_all = matrix[:, 0]
    minimum_column_points = max(_MIN_POINTS, int(math.ceil(0.6 * np.isfinite(x_all).sum())))
    usable = [
        index
        for index in range(1, matrix.shape[1])
        if int(np.sum(np.isfinite(x_all) & np.isfinite(matrix[:, index]))) >= minimum_column_points
    ]
    explicitly_intensity = [
        index
        for index in usable
        if re.search(r"(?:intensity|counts?|signal)", headers[index], flags=re.IGNORECASE)
        and not re.search(r"(?:standard\s*deviation|\bsd\b|\bcv\b|coefficient|error)", headers[index], flags=re.IGNORECASE)
    ]
    if explicitly_intensity:
        # A labelled table may also contain numerical SD/CV/axis columns.  When
        # the exporter explicitly labels intensity, expand every such column
        # and do not misrepresent the statistical auxiliaries as spectra.
        usable = explicitly_intensity
    if intensity_column is not None:
        selected = _column_selector(intensity_column, headers)
        if selected not in usable:
            raise ImportFormatError(
                f"Selected intensity column {headers[selected]!r} has fewer than {minimum_column_points} paired numerical points."
            )
        usable = [selected]
    if not usable:
        raise ImportFormatError(f"No intensity column in {source} has enough numerical values paired with the Raman-shift axis.")

    source_hash = hashlib.sha256(raw).hexdigest()
    common_metadata: dict[str, Any] = {
        "format": "portable_vendor_csv" if data_start > 3 or len(preamble_lines) >= 3 else "simple_csv",
        "encoding": encoding,
        "delimiter": {",": "comma", ";": "semicolon", "\t": "tab"}[delimiter],
        "data_start_line": data_start + 1,
        "header_line": None if header_line is None else header_line + 1,
        "axis_column": headers[0],
        "intensity_columns": [headers[index] for index in usable],
        "vendor_metadata": vendor_metadata,
        "preamble_lines": preamble_lines,
    }
    spectra: list[Spectrum] = []
    for column_index in usable:
        valid = np.isfinite(x_all) & np.isfinite(matrix[:, column_index])
        x = x_all[valid].astype(float, copy=True)
        y = matrix[valid, column_index].astype(float, copy=True)
        if np.unique(x).size < 3:
            raise ImportFormatError(f"Column {headers[column_index]!r} in {source} has fewer than three unique shifts.")
        metadata = dict(common_metadata)
        metadata["points"] = int(len(x))
        metadata["x_min_cm1"] = float(np.min(x))
        metadata["x_max_cm1"] = float(np.max(x))
        metadata["axis_direction"] = "increasing" if x[-1] > x[0] else "decreasing"
        spectra.append(
            Spectrum(
                x=x,
                y=y,
                source_path=source,
                source_column=headers[column_index],
                source_column_index=column_index,
                source_sha256=source_hash,
                import_metadata=metadata,
            )
        )
    return spectra


def inspect_spectrum_file(path: str | Path) -> dict[str, Any]:
    """Return JSON-serialisable structural information about one spectrum file."""
    spectra = read_spectrum_file(path)
    first = spectra[0]
    return {
        "file": str(first.source_path),
        "sha256": first.source_sha256,
        "format": first.import_metadata["format"],
        "encoding": first.import_metadata["encoding"],
        "delimiter": first.import_metadata["delimiter"],
        "data_start_line": first.import_metadata["data_start_line"],
        "axis_column": first.import_metadata["axis_column"],
        "axis_direction": first.import_metadata["axis_direction"],
        "intensity_columns": [
            {
                "name": spectrum.source_column,
                "index": spectrum.source_column_index,
                "points": int(len(spectrum.x)),
                "x_min_cm1": float(np.min(spectrum.x)),
                "x_max_cm1": float(np.max(spectrum.x)),
            }
            for spectrum in spectra
        ],
        "vendor_metadata": first.import_metadata["vendor_metadata"],
        "preamble_lines": first.import_metadata["preamble_lines"],
    }
