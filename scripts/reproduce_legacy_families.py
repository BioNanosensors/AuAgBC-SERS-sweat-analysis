#!/usr/bin/env python3
"""Regenerate the five legacy portable-Raman families used for validation.

The source manifest is filtered by its explicit ``record_group`` values.  No
identity is inferred from filenames or spectral similarity.  Generated family
manifests and pipeline outputs are written only below ``outputs/qa``.

Existing output folders are handled with the unified pipeline's ``--force``
mode.  That mode overwrites named products but does not delete unrelated files.
This wrapper never removes files or directories.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Sequence


PROFILE = "legacy_individual"
REQUIRED_COLUMNS = (
    "file",
    "record_group",
    "sample_type",
    "concentration_molar",
    "replicate",
    "accumulation",
    "instrument",
    "acquisition",
)
EXPECTED_CONCENTRATIONS = frozenset(Decimal("1").scaleb(-exponent) for exponent in range(3, 16))


@dataclass(frozen=True)
class FamilySpec:
    label: str
    record_group: str
    manifest_name: str
    output_relative: str
    expected_rows: int


FAMILIES = (
    FamilySpec(
        label="Stability/03_07_24",
        record_group="stability_2024-07-03",
        manifest_name="stability_2024-07-03_manifest.csv",
        output_relative="outputs/qa/stability_2024-07-03_legacy_v2",
        expected_rows=165,
    ),
    FamilySpec(
        label="Stability/19_05_24",
        record_group="stability_2024-05-19",
        manifest_name="stability_2024-05-19_manifest.csv",
        output_relative="outputs/qa/stability_2024-05-19_legacy_v2",
        expected_rows=160,
    ),
    FamilySpec(
        label="Stability/24_09_24",
        record_group="stability_2024-09-24",
        manifest_name="stability_2024-09-24_manifest.csv",
        output_relative="outputs/qa/stability_2024-09-24_legacy_v2",
        expected_rows=210,
    ),
    FamilySpec(
        label="Optimisation/500_5_5_L",
        record_group="optimisation_500_5_5_l",
        manifest_name="optimisation_500_5_5_l_manifest.csv",
        output_relative="outputs/qa/optimisation_500_5_5_l_legacy_v2",
        expected_rows=210,
    ),
    FamilySpec(
        label="Optimisation/750_5_5_H",
        record_group="optimisation_750_5_5_h",
        manifest_name="optimisation_750_5_5_h_manifest.csv",
        output_relative="outputs/qa/optimisation_750_5_5_h_legacy_v2",
        expected_rows=210,
    ),
)


class ReproductionError(RuntimeError):
    """Raised when inputs or a requested output target fail a safety check."""


@dataclass(frozen=True)
class PreparedFamily:
    spec: FamilySpec
    manifest_path: Path
    output_path: Path
    row_count: int


def _read_source_manifest(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        raise ReproductionError(f"Source manifest does not exist: {path}")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or [])
            rows = [dict(row) for row in reader]
    except (OSError, csv.Error) as exc:
        raise ReproductionError(f"Could not read source manifest {path}: {exc}") from exc
    missing = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
    if missing:
        raise ReproductionError(f"Source manifest is missing required columns: {', '.join(missing)}")
    if not rows:
        raise ReproductionError(f"Source manifest contains no rows: {path}")
    return fieldnames, rows


def _decimal(value: str, *, family: str, file_value: str) -> Decimal:
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ReproductionError(
            f"{family}: non-numerical concentration_molar {value!r} in {file_value!r}"
        ) from exc
    if not number.is_finite() or number <= 0:
        raise ReproductionError(
            f"{family}: concentration_molar must be finite and positive in {file_value!r}; received {value!r}"
        )
    return number


def _validate_family_rows(spec: FamilySpec, rows: list[dict[str, str]]) -> None:
    if len(rows) != spec.expected_rows:
        raise ReproductionError(
            f"{spec.label}: expected {spec.expected_rows} manifest rows, found {len(rows)}. "
            "Stop and review metadata/raw_processing_manifest.csv before processing."
        )
    seen_files: set[str] = set()
    concentrations: set[Decimal] = set()
    blank_count = 0
    for row in rows:
        file_value = str(row.get("file", "")).strip().replace("\\", "/")
        if not file_value:
            raise ReproductionError(f"{spec.label}: a selected row has an empty file value")
        file_key = file_value.casefold()
        if file_key in seen_files:
            raise ReproductionError(f"{spec.label}: duplicate file in selected manifest: {file_value}")
        seen_files.add(file_key)
        if str(row.get("record_group", "")).strip() != spec.record_group:
            raise ReproductionError(f"{spec.label}: selected row has the wrong record_group: {file_value}")
        if str(row.get("instrument", "")).strip() != "portable_raman":
            raise ReproductionError(f"{spec.label}: expected portable_raman metadata for {file_value}")
        if not str(row.get("replicate", "")).strip() or not str(row.get("accumulation", "")).strip():
            raise ReproductionError(f"{spec.label}: replicate or accumulation metadata is empty for {file_value}")

        sample_type = str(row.get("sample_type", "")).strip().casefold()
        concentration_text = str(row.get("concentration_molar", "")).strip()
        if sample_type == "blank":
            blank_count += 1
            if concentration_text:
                raise ReproductionError(f"{spec.label}: blank row has a concentration value: {file_value}")
        elif sample_type == "4atp":
            concentrations.add(_decimal(concentration_text, family=spec.label, file_value=file_value))
        else:
            raise ReproductionError(f"{spec.label}: unexpected sample_type {sample_type!r} in {file_value!r}")

    if blank_count != 15:
        raise ReproductionError(f"{spec.label}: expected 15 explicit blank rows, found {blank_count}")
    if concentrations != EXPECTED_CONCENTRATIONS:
        missing = sorted(EXPECTED_CONCENTRATIONS - concentrations)
        extra = sorted(concentrations - EXPECTED_CONCENTRATIONS)
        raise ReproductionError(
            f"{spec.label}: concentration metadata does not cover the expected 1e-15 to 1e-3 M series; "
            f"missing={missing}, extra={extra}"
        )


def _write_manifest(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="raise", lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    except (OSError, csv.Error, ValueError) as exc:
        raise ReproductionError(f"Could not write generated manifest {path}: {exc}") from exc


def _known_output_path(repository: Path, spec: FamilySpec) -> Path:
    qa_root = (repository / "outputs" / "qa").resolve()
    output_path = (repository / spec.output_relative).resolve()
    try:
        output_path.relative_to(qa_root)
    except ValueError as exc:
        raise ReproductionError(f"Refusing output outside the repository's outputs/qa directory: {output_path}") from exc
    expected = (qa_root / Path(spec.output_relative).name).resolve()
    if output_path != expected:
        raise ReproductionError(f"Refusing unrecognised output target: {output_path}")
    return output_path


def prepare_family_manifests(
    repository: Path,
    *,
    manifest_directory: Path | None = None,
    families: Sequence[FamilySpec] = FAMILIES,
) -> list[PreparedFamily]:
    """Filter and validate all requested families, preserving every source cell."""

    repository = repository.expanduser().resolve()
    source_manifest = repository / "metadata" / "raw_processing_manifest.csv"
    fieldnames, source_rows = _read_source_manifest(source_manifest)
    destination = (manifest_directory or repository / "outputs" / "qa").expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)

    prepared: list[PreparedFamily] = []
    for spec in families:
        rows = [row for row in source_rows if str(row.get("record_group", "")).strip() == spec.record_group]
        rows.sort(key=lambda row: (str(row["file"]).replace("\\", "/").casefold(), str(row["file"])))
        _validate_family_rows(spec, rows)
        manifest_path = destination / spec.manifest_name
        _write_manifest(manifest_path, fieldnames, rows)
        prepared.append(
            PreparedFamily(
                spec=spec,
                manifest_path=manifest_path,
                output_path=_known_output_path(repository, spec),
                row_count=len(rows),
            )
        )
    return prepared


def _pipeline_command(repository: Path, family: PreparedFamily) -> list[str]:
    expected_output = _known_output_path(repository, family.spec)
    if family.output_path.resolve() != expected_output:
        raise ReproductionError(f"Refusing unrecognised output target: {family.output_path}")
    process_script = repository / "process_raman.py"
    if not process_script.is_file():
        raise ReproductionError(f"Unified pipeline entry point does not exist: {process_script}")
    command = [
        sys.executable,
        str(process_script),
        "process",
        str(family.manifest_path),
        "--input-root",
        str(repository),
        "--output",
        str(expected_output),
        "--profile",
        PROFILE,
    ]
    if expected_output.is_dir() and any(expected_output.iterdir()):
        # The target is one of the five constant, validated output paths.  The
        # pipeline overwrites named products only; it never recursively deletes.
        command.append("--force")
    return command


def run_pipeline(repository: Path, prepared: Sequence[PreparedFamily]) -> None:
    total = len(prepared)
    for index, family in enumerate(prepared, start=1):
        print(
            f"[{index}/{total}] Processing {family.spec.label} "
            f"({family.row_count} manifest rows) -> {family.output_path.relative_to(repository).as_posix()}",
            flush=True,
        )
        command = _pipeline_command(repository, family)
        try:
            completed = subprocess.run(command, cwd=repository, check=False)
        except OSError as exc:
            raise ReproductionError(f"Could not start the unified pipeline for {family.spec.label}: {exc}") from exc
        if completed.returncode != 0:
            raise ReproductionError(
                f"Unified pipeline failed for {family.spec.label} with exit code {completed.returncode}. "
                "Earlier completed families were retained; no files were deleted."
            )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root; defaults to the parent of this script's directory.",
    )
    parser.add_argument(
        "--manifests-only",
        action="store_true",
        help="Validate and generate the five filtered manifests without running the numerical pipeline.",
    )
    args = parser.parse_args(argv)
    repository = args.repository_root.expanduser().resolve()
    try:
        prepared = prepare_family_manifests(repository)
        for family in prepared:
            print(
                f"Prepared {family.row_count} rows for {family.spec.label}: "
                f"{family.manifest_path.relative_to(repository).as_posix()}"
            )
        if args.manifests_only:
            print("Manifest validation complete; numerical processing was skipped by request.")
            return 0
        run_pipeline(repository, prepared)
    except ReproductionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print("All five families were regenerated. Run scripts/validate_legacy_reproduction.py next.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
