#!/usr/bin/env python3
"""Compare package-generated legacy-v2 spectra with the preserved CSV snapshot.

This is verification-only: it reads both trees and writes deterministic metrics
tables.  It never modifies spectra, manifests, or processing configuration.
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


FAMILIES = (
    (
        "Stability/03_07_24",
        "outputs/qa/stability_2024-07-03_legacy_v2/processed_spectra",
        "data/quarantine/legacy_snapshot/Stability/03_07_24/Processed Spectra",
    ),
    (
        "Stability/19_05_24",
        "outputs/qa/stability_2024-05-19_legacy_v2/processed_spectra",
        "data/quarantine/legacy_snapshot/Stability/19_05_24/Processed Spectra",
    ),
    (
        "Stability/24_09_24",
        "outputs/qa/stability_2024-09-24_legacy_v2/processed_spectra",
        "data/quarantine/legacy_snapshot/Stability/24_09_24/Processed Spectra",
    ),
    (
        "Optimisation/500_5_5_L",
        "outputs/qa/optimisation_500_5_5_l_legacy_v2/processed_spectra",
        "data/quarantine/legacy_snapshot/Optimisation/500_5_5_L/Processed Spectra",
    ),
    (
        "Optimisation/750_5_5_H",
        "outputs/qa/optimisation_750_5_5_h_legacy_v2/processed_spectra",
        "data/quarantine/legacy_snapshot/Optimisation/750_5_5_H/Processed Spectra",
    ),
)
SPECTRUM_SUFFIX = "_blank_subtracted_processed.csv"

DETAIL_COLUMNS = (
    "family",
    "basename",
    "status",
    "generated_file",
    "reference_file",
    "generated_points",
    "reference_points",
    "comparison_points",
    "comparison_mode",
    "x_exact",
    "x_allclose_1e_12",
    "exact_array_equal",
    "allclose_1e_12",
    "allclose_1e_9",
    "allclose_1e_7",
    "rmse",
    "mae",
    "max_abs",
    "pearson_r",
)

SUMMARY_COLUMNS = (
    "family",
    "expected_files",
    "generated_files",
    "matched_files",
    "missing_generated_files",
    "orphan_generated_files",
    "exact_array_equal_files",
    "allclose_1e_12_files",
    "allclose_1e_9_files",
    "allclose_1e_7_files",
    "x_exact_files",
    "max_rmse",
    "median_rmse",
    "max_max_abs",
    "min_pearson_r",
    "missing_generated_names",
    "orphan_generated_names",
)


@dataclass(frozen=True)
class NumericSpectrum:
    x: tuple[float, ...]
    y: tuple[float, ...]


def _float(value: str) -> float | None:
    try:
        number = float(value.strip().strip('"').replace("\u2212", "-"))
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _split(line: str, delimiter: str) -> list[str]:
    try:
        return next(csv.reader([line], delimiter=delimiter))
    except csv.Error:
        return line.split(delimiter)


def read_two_column_spectrum(path: Path) -> NumericSpectrum:
    raw = path.read_bytes()
    text = None
    for encoding in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:  # latin-1 is total, retained as a defensive assertion.
        raise ValueError(f"Could not decode {path}")
    lines = text.splitlines()
    best: tuple[int, int, str] | None = None
    for rank, delimiter in enumerate((",", "\t", ";")):
        count = 0
        for line in lines:
            cells = _split(line, delimiter)
            if len(cells) >= 2 and _float(cells[0]) is not None and _float(cells[1]) is not None:
                count += 1
        candidate = (count, -rank, delimiter)
        if best is None or candidate > best:
            best = candidate
    if best is None or best[0] < 2:
        raise ValueError(f"No two-column numeric spectrum found in {path}")
    delimiter = best[2]
    x_values: list[float] = []
    y_values: list[float] = []
    for line in lines:
        cells = _split(line, delimiter)
        if len(cells) < 2:
            continue
        x_value = _float(cells[0])
        y_value = _float(cells[1])
        if x_value is not None and y_value is not None:
            x_values.append(x_value)
            y_values.append(y_value)
    if len(x_values) < 2:
        raise ValueError(f"Fewer than two paired numeric rows found in {path}")
    return NumericSpectrum(tuple(x_values), tuple(y_values))


def _isclose(left: float, right: float, tolerance: float) -> bool:
    return abs(left - right) <= tolerance + tolerance * abs(right)


def _allclose(left: Sequence[float], right: Sequence[float], tolerance: float) -> bool:
    return len(left) == len(right) and all(_isclose(a, b, tolerance) for a, b in zip(left, right))


def _increasing_unique(x_values: Sequence[float], y_values: Sequence[float]) -> tuple[list[float], list[float]]:
    pairs = sorted(zip(x_values, y_values), key=lambda pair: pair[0])
    unique_x: list[float] = []
    sums: list[float] = []
    counts: list[int] = []
    for x_value, y_value in pairs:
        if unique_x and x_value == unique_x[-1]:
            sums[-1] += y_value
            counts[-1] += 1
        else:
            unique_x.append(x_value)
            sums.append(y_value)
            counts.append(1)
    return unique_x, [total / count for total, count in zip(sums, counts)]


def _interpolate(query: Sequence[float], source_x: Sequence[float], source_y: Sequence[float]) -> list[float]:
    x_values, y_values = _increasing_unique(source_x, source_y)
    output: list[float] = []
    right = 1
    for query_value in query:
        while right < len(x_values) and x_values[right] < query_value:
            right += 1
        if right >= len(x_values):
            output.append(y_values[-1])
        elif query_value <= x_values[0]:
            output.append(y_values[0])
        else:
            left = right - 1
            span = x_values[right] - x_values[left]
            weight = (query_value - x_values[left]) / span if span else 0.0
            output.append(y_values[left] + weight * (y_values[right] - y_values[left]))
    return output


def _pearson(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) < 2:
        return math.nan
    left_mean = math.fsum(left) / len(left)
    right_mean = math.fsum(right) / len(right)
    numerator = math.fsum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    left_ss = math.fsum((a - left_mean) ** 2 for a in left)
    right_ss = math.fsum((b - right_mean) ** 2 for b in right)
    denominator = math.sqrt(left_ss * right_ss)
    return numerator / denominator if denominator else math.nan


def compare_pair(generated: NumericSpectrum, reference: NumericSpectrum) -> dict[str, object]:
    x_exact = generated.x == reference.x
    x_near = _allclose(generated.x, reference.x, 1e-12)
    if len(generated.x) == len(reference.x) and x_near:
        generated_y = list(generated.y)
        reference_y = list(reference.y)
        comparison_mode = "pointwise"
    else:
        low = max(min(generated.x), min(reference.x))
        high = min(max(generated.x), max(reference.x))
        indexes = [index for index, value in enumerate(generated.x) if low <= value <= high]
        if len(indexes) < 2:
            raise ValueError("Spectra have fewer than two points in their overlapping x-range")
        query = [generated.x[index] for index in indexes]
        generated_y = [generated.y[index] for index in indexes]
        reference_y = _interpolate(query, reference.x, reference.y)
        comparison_mode = "reference_interpolated_to_generated"
    differences = [left - right for left, right in zip(generated_y, reference_y)]
    squared = [difference * difference for difference in differences]
    return {
        "comparison_points": len(differences),
        "comparison_mode": comparison_mode,
        "x_exact": x_exact,
        "x_allclose_1e_12": x_near,
        "exact_array_equal": x_exact and generated.y == reference.y,
        "allclose_1e_12": _allclose(generated_y, reference_y, 1e-12),
        "allclose_1e_9": _allclose(generated_y, reference_y, 1e-9),
        "allclose_1e_7": _allclose(generated_y, reference_y, 1e-7),
        "rmse": math.sqrt(math.fsum(squared) / len(squared)),
        "mae": math.fsum(abs(value) for value in differences) / len(differences),
        "max_abs": max(abs(value) for value in differences),
        "pearson_r": _pearson(generated_y, reference_y),
    }


def _files_by_name(directory: Path) -> dict[str, Path]:
    if not directory.is_dir():
        raise FileNotFoundError(f"Required comparison directory does not exist: {directory}")
    result: dict[str, Path] = {}
    for path in sorted(directory.glob("*.csv"), key=lambda item: item.name.casefold()):
        # Historical folders sometimes also contain processing_report.csv.  It
        # is not a spectrum and is outside this numerical comparison.
        if not path.name.casefold().endswith(SPECTRUM_SUFFIX):
            continue
        key = path.name.casefold()
        if key in result:
            raise ValueError(f"Case-insensitive duplicate basename in {directory}: {path.name}")
        result[key] = path
    return result


def compare_family(repository: Path, family: str, generated_relative: str, reference_relative: str) -> list[dict[str, object]]:
    generated_directory = repository / generated_relative
    reference_directory = repository / reference_relative
    generated = _files_by_name(generated_directory)
    reference = _files_by_name(reference_directory)
    rows: list[dict[str, object]] = []
    for key in sorted(set(generated) | set(reference)):
        generated_path = generated.get(key)
        reference_path = reference.get(key)
        basename = (generated_path or reference_path).name  # type: ignore[union-attr]
        base: dict[str, object] = {
            "family": family,
            "basename": basename,
            "generated_file": generated_path.relative_to(repository).as_posix() if generated_path else "",
            "reference_file": reference_path.relative_to(repository).as_posix() if reference_path else "",
        }
        if generated_path is None:
            rows.append({**base, "status": "missing_generated"})
            continue
        if reference_path is None:
            rows.append({**base, "status": "orphan_generated"})
            continue
        try:
            generated_spectrum = read_two_column_spectrum(generated_path)
            reference_spectrum = read_two_column_spectrum(reference_path)
            comparison = compare_pair(generated_spectrum, reference_spectrum)
            rows.append(
                {
                    **base,
                    "status": "matched",
                    "generated_points": len(generated_spectrum.x),
                    "reference_points": len(reference_spectrum.x),
                    **comparison,
                }
            )
        except Exception as exc:
            rows.append({**base, "status": f"comparison_error: {exc}"})
    return rows


def summarize(family: str, rows: list[dict[str, object]]) -> dict[str, object]:
    matched = [row for row in rows if row["status"] == "matched"]
    missing = [str(row["basename"]) for row in rows if row["status"] == "missing_generated"]
    orphan = [str(row["basename"]) for row in rows if row["status"] == "orphan_generated"]
    errors = [row for row in rows if str(row["status"]).startswith("comparison_error")]
    if errors:
        missing.extend(f"ERROR:{row['basename']}" for row in errors)
    rmse_values = [float(row["rmse"]) for row in matched]
    max_abs_values = [float(row["max_abs"]) for row in matched]
    correlations = [float(row["pearson_r"]) for row in matched if math.isfinite(float(row["pearson_r"]))]
    return {
        "family": family,
        "expected_files": sum(row["status"] != "orphan_generated" for row in rows),
        "generated_files": sum(row["status"] != "missing_generated" for row in rows),
        "matched_files": len(matched),
        "missing_generated_files": sum(row["status"] == "missing_generated" for row in rows),
        "orphan_generated_files": sum(row["status"] == "orphan_generated" for row in rows),
        "exact_array_equal_files": sum(bool(row["exact_array_equal"]) for row in matched),
        "allclose_1e_12_files": sum(bool(row["allclose_1e_12"]) for row in matched),
        "allclose_1e_9_files": sum(bool(row["allclose_1e_9"]) for row in matched),
        "allclose_1e_7_files": sum(bool(row["allclose_1e_7"]) for row in matched),
        "x_exact_files": sum(bool(row["x_exact"]) for row in matched),
        "max_rmse": max(rmse_values, default=math.nan),
        "median_rmse": statistics.median(rmse_values) if rmse_values else math.nan,
        "max_max_abs": max(max_abs_values, default=math.nan),
        "min_pearson_r": min(correlations, default=math.nan),
        "missing_generated_names": ";".join(sorted(missing, key=str.casefold)),
        "orphan_generated_names": ";".join(sorted(orphan, key=str.casefold)),
    }


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return "" if not math.isfinite(value) else format(value, ".17g")
    return str(value)


def write_csv(path: Path, columns: Sequence[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        for row in rows:
            writer.writerow([_cell(row.get(column)) for column in columns])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root; defaults to the parent of this script's directory.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("metadata/validation"),
        help="Output directory relative to the repository root unless absolute.",
    )
    args = parser.parse_args(argv)
    repository = args.repository_root.expanduser().resolve()
    output_directory = args.output_dir.expanduser()
    if not output_directory.is_absolute():
        output_directory = repository / output_directory
    output_directory = output_directory.resolve()

    all_rows: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    for family, generated, reference in FAMILIES:
        rows = compare_family(repository, family, generated, reference)
        all_rows.extend(rows)
        summaries.append(summarize(family, rows))
    summaries.append(summarize("ALL_FIVE_FAMILIES", all_rows))

    detail_path = output_directory / "package_reproduction_metrics.csv"
    summary_path = output_directory / "package_reproduction_summary.csv"
    write_csv(detail_path, DETAIL_COLUMNS, all_rows)
    write_csv(summary_path, SUMMARY_COLUMNS, summaries)
    print(f"Wrote {len(all_rows)} file-level rows to {detail_path}")
    print(f"Wrote {len(summaries)} summary rows to {summary_path}")
    for summary in summaries:
        print(
            f"{summary['family']}: matched={summary['matched_files']}, "
            f"exact={summary['exact_array_equal_files']}, allclose(1e-7)={summary['allclose_1e_7_files']}, "
            f"missing={summary['missing_generated_files']}, orphan={summary['orphan_generated_files']}, "
            f"max_rmse={_cell(summary['max_rmse'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
