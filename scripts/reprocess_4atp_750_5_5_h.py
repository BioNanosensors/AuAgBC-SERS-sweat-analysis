#!/usr/bin/env python3
"""Regenerate and audit the confirmed-blank 750_5_5_H 4-ATP analysis.

The script keeps three questions separate:

* the preserved historical output records the mixed 15-spectrum blank lineage;
* ``controlled_legacy_confirmed_blank`` changes only to the author-confirmed
  five-channel blank while retaining the recovered legacy numerical chain; and
* ``reference_2026`` is a separate current-workflow sensitivity analysis.

No scientific identity is inferred from filenames or spectral similarity.  The
195 sample rows come from the curated manifest and remain ``raw_unverified``.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import importlib.metadata
import io
import json
import math
import platform
import shutil
import statistics
import sys
import tempfile
import warnings
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
for import_root in (REPOSITORY_ROOT, SOURCE_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from auagbc_sers.errors import RamanPipelineError  # noqa: E402
from auagbc_sers.io import read_spectrum_file, sha256_file  # noqa: E402
from auagbc_sers.models import PeakSpec  # noqa: E402
from auagbc_sers.pipeline import process_job  # noqa: E402
from auagbc_sers.processing import peak_value  # noqa: E402


SCHEMA_VERSION = "1.0"
SOURCE_RECORD_GROUP = "optimisation_750_5_5_h"
CONFIRMED_BLANK_SOURCE_GROUP = "optimisation_750_5_5_h_confirmed_blank"
ANALYSIS_RECORD_GROUP = "optimisation_750_5_5_h_confirmed_blank_reanalysis"
CONFIRMED_BLANK_RELATIVE = Path(
    "data/raw/4atp/optimisation/750_5_5_H/Blanck_AABC_750_5_5_H.csv"
)
CONFIRMED_BLANK_SHA256 = (
    "e36f0ad7a57ebab8cba038309284305cfecc98d1586499fe73e266e301257dd9"
)
CONFIG_DIRECTORY_RELATIVE = Path("configs/reanalysis")
RELEASE_ROOT_RELATIVE = Path("data/processed/4atp/optimisation/750_5_5_H")
HISTORICAL_PROCESSED_RELATIVE = Path(
    "data/quarantine/legacy_snapshot/Optimisation/750_5_5_H/Processed Spectra"
)
RELEASE_REQUIREMENTS_RELATIVE = Path("requirements-release.txt")
FFT_CUTOFF_LOCK_RELATIVE = Path(
    "metadata/processing_locks/optimisation_750_5_5_h_fft_cutoffs.csv"
)
GENERATION_PYTHON_VERSION = "3.12.13"
CHECK_PYTHON_VERSIONS = ("3.12.10", "3.12.13")
CANONICAL_PLATFORM_SYSTEM = "Windows"
CANONICAL_PLATFORM_MACHINE = "AMD64"

CONTROLLED_NAME = "controlled_legacy_confirmed_blank"
REFERENCE_NAME = "reference_2026"
COMPARISON_NAME = "comparison"
HISTORICAL_NAME = "historical_mixed_blank_legacy"

CONTROLLED_MANIFEST_NAME = (
    "optimisation_750_5_5_h_confirmed_blank_legacy_v2_manifest.csv"
)
CONTROLLED_CONFIG_NAME = "optimisation_750_5_5_h_confirmed_blank_legacy_v2.json"
REFERENCE_MANIFEST_NAME = (
    "optimisation_750_5_5_h_confirmed_blank_reference_2026_manifest.csv"
)
REFERENCE_CONFIG_NAME = (
    "optimisation_750_5_5_h_confirmed_blank_reference_2026.json"
)

MANIFEST_FIELDS = (
    "file",
    "record_group",
    "sample_type",
    "concentration_molar",
    "concentration_label",
    "replicate",
    "accumulation",
    "instrument",
    "acquisition",
    "analyte",
    "matrix",
    "provenance_status",
    "source_record_group",
    "source_axis_status",
    "blank_replication_design",
    "intensity_column",
    "baseline_lambda",
    "filter_fft_peak_index",
    "analysis_lineage",
)

FFT_CUTOFF_LOCK_FIELDS = (
    "lineage",
    "file",
    "source_sha256",
    "manifest_intensity_selector",
    "source_intensity_column",
    "record_id",
    "sample_type",
    "spectrum_points",
    "positive_frequency_max_index",
    "filter_fft_peak_index",
    "normalized_cutoff",
    "percentile",
    "order",
    "lock_basis",
)

CONCENTRATION_LABELS = {
    Decimal("1e-3"): "1 mM",
    Decimal("1e-4"): "100 µM",
    Decimal("1e-5"): "10 µM",
    Decimal("1e-6"): "1 µM",
    Decimal("1e-7"): "100 nM",
    Decimal("1e-8"): "10 nM",
    Decimal("1e-9"): "1 nM",
    Decimal("1e-10"): "100 pM",
    Decimal("1e-11"): "10 pM",
    Decimal("1e-12"): "1 pM",
    Decimal("1e-13"): "100 fM",
    Decimal("1e-14"): "10 fM",
    Decimal("1e-15"): "1 fM",
}

PEAK_SPECS = (
    PeakSpec(center_cm1=392.32, window_cm1=10.0, method="height"),
    PeakSpec(center_cm1=1078.50, window_cm1=7.0, method="height"),
    PeakSpec(center_cm1=1589.62, window_cm1=8.0, method="height"),
)

SELECTED_PIPELINE_FILES = (
    "spectra_replicate.csv",
    "spectra_concentration.csv",
    "peaks_scan.csv",
    "peaks_replicate.csv",
    "peaks_concentration.csv",
    "resolved_manifest.csv",
    "processing_report.csv",
    "source_metadata.json",
)


class ReanalysisError(RuntimeError):
    """Raised when a release assumption or numerical contract is not met."""


@dataclass(frozen=True)
class LineageRun:
    name: str
    profile: str
    manifest_path: Path
    config_path: Path
    output_path: Path
    run: dict[str, Any]
    numerical_library_warnings: tuple[str, ...]


@dataclass(frozen=True)
class SpectrumArrays:
    x: np.ndarray
    y: np.ndarray


@dataclass(frozen=True)
class SampleRecord:
    file: str
    concentration_molar: str
    concentration_label: str
    replicate: str
    accumulation: str
    historical: SpectrumArrays
    controlled: SpectrumArrays
    reference: SpectrumArrays


COMPARISONS = (
    (
        "historical_vs_controlled_legacy",
        "historical_mixed_blank_legacy",
        "controlled_legacy_confirmed_blank",
        "blank_only_effect",
        "historical",
        "controlled",
    ),
    (
        "controlled_legacy_vs_reference_2026",
        "controlled_legacy_confirmed_blank",
        "reference_2026",
        "workflow_effect",
        "controlled",
        "reference",
    ),
    (
        "historical_vs_reference_2026",
        "historical_mixed_blank_legacy",
        "reference_2026",
        "combined_blank_and_workflow_effect",
        "historical",
        "reference",
    ),
)


def _portable(path: Path) -> str:
    return path.as_posix()


def _decimal(value: object, *, context: str) -> Decimal:
    try:
        result = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ReanalysisError(f"{context} is not a decimal concentration: {value!r}") from exc
    if not result.is_finite() or result <= 0:
        raise ReanalysisError(f"{context} must be finite and positive: {value!r}")
    return result


def _read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        raise ReanalysisError(f"Required CSV does not exist: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), [dict(row) for row in reader]


def _fft_cutoff_locks(
    repository: Path,
) -> dict[str, dict[tuple[str, str], dict[str, str]]]:
    """Load and validate the record-level cutoff lock used by this release.

    The historical percentile rule contains true midpoint ties.  The lock is
    analogous to a dependency lockfile: it records the peak index resolved by
    the canonical run so an audited replay cannot take a different CPU-specific
    floating-point branch.
    """
    path = repository / FFT_CUTOFF_LOCK_RELATIVE
    fieldnames, rows = _read_csv_rows(path)
    if tuple(fieldnames) != FFT_CUTOFF_LOCK_FIELDS:
        raise ReanalysisError(
            f"FFT cutoff lock columns differ from the required schema: {fieldnames}"
        )
    expected_counts = {
        HISTORICAL_NAME: 210,
        CONTROLLED_NAME: 200,
        REFERENCE_NAME: 200,
    }
    result: dict[str, dict[tuple[str, str], dict[str, str]]] = {
        name: {} for name in expected_counts
    }
    record_ids: dict[str, set[str]] = {name: set() for name in expected_counts}
    source_hashes: dict[str, str] = {}
    for line_number, row in enumerate(rows, start=2):
        lineage = row.get("lineage", "").strip()
        if lineage not in expected_counts:
            raise ReanalysisError(
                f"FFT cutoff lock row {line_number} has unknown lineage {lineage!r}."
            )
        file = row.get("file", "").strip().replace("\\", "/")
        selector = row.get("manifest_intensity_selector", "").strip()
        record_id = row.get("record_id", "").strip()
        source_column = row.get("source_intensity_column", "").strip()
        sample_type = row.get("sample_type", "").strip().casefold()
        lock_basis = row.get("lock_basis", "").strip()
        source_hash = row.get("source_sha256", "").strip().casefold()
        if (
            not file
            or not selector
            or not record_id
            or not source_column
            or not lock_basis
            or sample_type not in {"4atp", "blank"}
            or len(source_hash) != 64
            or any(character not in "0123456789abcdef" for character in source_hash)
        ):
            raise ReanalysisError(
                f"FFT cutoff lock row {line_number} has an empty identity field."
            )
        key = (file, selector)
        if key in result[lineage]:
            raise ReanalysisError(
                f"FFT cutoff lock duplicates {lineage} selector {key}."
            )
        if record_id in record_ids[lineage]:
            raise ReanalysisError(
                f"FFT cutoff lock duplicates {lineage} record_id {record_id!r}."
            )
        record_ids[lineage].add(record_id)
        try:
            peak_index = int(row["filter_fft_peak_index"])
            cutoff = float(row["normalized_cutoff"])
            percentile = float(row["percentile"])
            order = int(row["order"])
            points = int(row["spectrum_points"])
            denominator = int(row["positive_frequency_max_index"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ReanalysisError(
                f"FFT cutoff lock row {line_number} has invalid numerical fields."
            ) from exc
        expected_points = 441 if lineage == REFERENCE_NAME else 512
        if points != expected_points or denominator != points // 2 - 1:
            raise ReanalysisError(
                f"FFT cutoff lock row {line_number} has an inconsistent point-count contract."
            )
        if not 1 <= peak_index < denominator:
            raise ReanalysisError(
                f"FFT cutoff lock row {line_number} peak {peak_index} is outside 1..{denominator - 1}."
            )
        if not np.isclose(cutoff, peak_index / denominator, rtol=0.0, atol=1e-15):
            raise ReanalysisError(
                f"FFT cutoff lock row {line_number} cutoff does not match its peak index."
            )
        expected_percentile = 60.0 if lineage == REFERENCE_NAME else (5.0 if sample_type == "blank" else 10.0)
        expected_order = 2 if lineage == REFERENCE_NAME else 3
        if percentile != expected_percentile or order != expected_order:
            raise ReanalysisError(
                f"FFT cutoff lock row {line_number} has percentile/order "
                f"{percentile}/{order}, expected {expected_percentile}/{expected_order}."
            )
        if file in source_hashes and source_hashes[file] != source_hash:
            raise ReanalysisError(
                f"FFT cutoff lock assigns conflicting hashes to {file}."
            )
        source_hashes[file] = source_hash
        result[lineage][key] = dict(row)
    for lineage, expected in expected_counts.items():
        if len(result[lineage]) != expected:
            raise ReanalysisError(
                f"FFT cutoff lock requires {expected} {lineage} rows; found {len(result[lineage])}."
            )
    for file, expected_hash in source_hashes.items():
        source = repository / Path(file)
        if not source.is_file() or sha256_file(source) != expected_hash:
            raise ReanalysisError(
                f"FFT cutoff lock source identity does not match {file}."
            )
    return result


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        return format(value, ".17g")
    if isinstance(value, (dict, list)):
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    return str(value)


def _csv_bytes(
    fieldnames: Sequence[str], rows: Iterable[Mapping[str, object]]
) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(fieldnames)
    for row in rows:
        writer.writerow([_cell(row.get(field)) for field in fieldnames])
    return buffer.getvalue().encode("utf-8")


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _code_identity(repository: Path) -> list[dict[str, str]]:
    """Hash the generator and every package module used by the pipeline."""
    paths = [
        repository / "scripts" / "reprocess_4atp_750_5_5_h.py",
        repository / "pyproject.toml",
        repository / RELEASE_REQUIREMENTS_RELATIVE,
    ]
    paths.extend(sorted((repository / "src" / "auagbc_sers").glob("*.py")))
    identity: list[dict[str, str]] = []
    for path in paths:
        if not path.is_file():
            raise ReanalysisError(f"Code-identity file is missing: {path}")
        identity.append(
            {
                "path": path.relative_to(repository).as_posix(),
                "sha256": sha256_file(path),
            }
        )
    return identity


def _expected_release_packages(repository: Path) -> dict[str, str]:
    path = repository / RELEASE_REQUIREMENTS_RELATIVE
    if not path.is_file():
        raise ReanalysisError(f"Canonical release constraints are missing: {path}")
    expected: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.count("==") != 1:
            raise ReanalysisError(
                f"{path.name} line {line_number} must use one exact name==version pin."
            )
        name, version = (part.strip() for part in line.split("==", 1))
        if not name or not version or name in expected:
            raise ReanalysisError(
                f"Invalid or duplicate release pin on {path.name} line {line_number}."
            )
        expected[name] = version
    if not expected:
        raise ReanalysisError(f"Canonical release constraints contain no pins: {path}")
    return expected


def _installed_distribution_version(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def _validate_canonical_release_environment(
    repository: Path, *, allow_check_patch: bool = False
) -> dict[str, object]:
    """Refuse persistent publication from a noncanonical numerical stack."""
    expected = _expected_release_packages(repository)
    actual: dict[str, str] = {}
    mismatches: list[str] = []
    python_version = platform.python_version()
    platform_system = platform.system()
    platform_machine = platform.machine()
    allowed_python = (
        CHECK_PYTHON_VERSIONS
        if allow_check_patch
        else (GENERATION_PYTHON_VERSION,)
    )
    if python_version not in allowed_python:
        mismatches.append(
            f"Python {python_version} (expected {' or '.join(allowed_python)})"
        )
    if platform_system != CANONICAL_PLATFORM_SYSTEM:
        mismatches.append(
            f"platform {platform_system} (expected {CANONICAL_PLATFORM_SYSTEM})"
        )
    if platform_machine.casefold() != CANONICAL_PLATFORM_MACHINE.casefold():
        mismatches.append(
            f"machine {platform_machine} (expected {CANONICAL_PLATFORM_MACHINE})"
        )
    for distribution, expected_version in expected.items():
        actual_version = _installed_distribution_version(distribution)
        actual[distribution] = actual_version
        if actual_version != expected_version:
            mismatches.append(
                f"{distribution} {actual_version} (expected {expected_version})"
            )
    if mismatches:
        raise ReanalysisError(
            "Persistent release generation and exact checking require the canonical environment: "
            + "; ".join(mismatches)
            + '. Install it with: python -m pip install -e ".[test]" '
            "-c requirements-release.txt"
        )
    return {
        "python": python_version,
        "system": platform_system,
        "machine": platform_machine,
        "packages": dict(sorted(actual.items(), key=lambda item: item[0].casefold())),
    }


def _sample_source_rows(repository: Path) -> list[dict[str, str]]:
    manifest_path = repository / "metadata" / "raw_processing_manifest.csv"
    fieldnames, rows = _read_csv_rows(manifest_path)
    required = {
        "file",
        "record_group",
        "sample_type",
        "concentration_molar",
        "replicate",
        "accumulation",
        "instrument",
        "acquisition",
        "provenance_status",
    }
    missing = sorted(required.difference(fieldnames))
    if missing:
        raise ReanalysisError(
            "raw_processing_manifest.csv is missing columns: " + ", ".join(missing)
        )
    selected = [
        row
        for row in rows
        if row.get("record_group", "").strip() == SOURCE_RECORD_GROUP
        and row.get("sample_type", "").strip().casefold() == "4atp"
    ]
    selected.sort(key=lambda row: (row["file"].casefold(), row["file"]))
    if len(selected) != 195:
        raise ReanalysisError(
            f"Expected 195 high-power sample rows, found {len(selected)}."
        )
    return selected


def build_manifest_rows(repository: Path, *, lineage: str) -> list[dict[str, str]]:
    """Build one explicit 200-row manifest without relabelling source files."""
    if lineage not in {CONTROLLED_NAME, REFERENCE_NAME}:
        raise ReanalysisError(f"Unknown reanalysis lineage: {lineage}")
    cutoff_locks = _fft_cutoff_locks(repository)[lineage]
    used_locks: set[tuple[str, str]] = set()
    rows: list[dict[str, str]] = []
    for source in _sample_source_rows(repository):
        concentration = _decimal(
            source["concentration_molar"], context=source["file"]
        )
        label = CONCENTRATION_LABELS.get(concentration)
        if label is None:
            raise ReanalysisError(
                f"Unexpected concentration {concentration} in {source['file']}"
            )
        if source.get("provenance_status") != "raw_unverified":
            raise ReanalysisError(
                f"Sample provenance unexpectedly changed for {source['file']}: "
                f"{source.get('provenance_status')!r}"
            )
        file = source["file"].replace("\\", "/")
        lock_key = (file, "1")
        if lock_key not in cutoff_locks:
            raise ReanalysisError(
                f"{lineage}: no FFT cutoff lock exists for {lock_key}."
            )
        if cutoff_locks[lock_key]["sample_type"].casefold() != "4atp":
            raise ReanalysisError(
                f"{lineage}: FFT cutoff lock sample type differs for {file}."
            )
        used_locks.add(lock_key)
        rows.append(
            {
                "file": file,
                "record_group": ANALYSIS_RECORD_GROUP,
                "sample_type": "4atp",
                "concentration_molar": str(source["concentration_molar"]).strip(),
                "concentration_label": label,
                "replicate": str(source["replicate"]).strip(),
                "accumulation": str(source["accumulation"]).strip(),
                "instrument": str(source["instrument"]).strip(),
                "acquisition": str(source["acquisition"]).strip(),
                "analyte": "4-ATP",
                "matrix": "AuAgBC substrate",
                "provenance_status": "raw_unverified",
                "source_record_group": SOURCE_RECORD_GROUP,
                "source_axis_status": (
                    "prepared_axis_differs_from_vendor_original_approx_0.39937_cm-1"
                ),
                "blank_replication_design": "",
                "intensity_column": "1",
                "baseline_lambda": "3000" if lineage == CONTROLLED_NAME else "",
                "filter_fft_peak_index": cutoff_locks[lock_key][
                    "filter_fft_peak_index"
                ],
                "analysis_lineage": lineage,
            }
        )

    blank_path = repository / CONFIRMED_BLANK_RELATIVE
    if not blank_path.is_file():
        raise ReanalysisError(f"Confirmed blank is missing: {blank_path}")
    if sha256_file(blank_path) != CONFIRMED_BLANK_SHA256:
        raise ReanalysisError("Confirmed blank SHA-256 does not match the audited source.")
    for accumulation in range(1, 6):
        file = _portable(CONFIRMED_BLANK_RELATIVE)
        selector = str(accumulation)
        lock_key = (file, selector)
        if lock_key not in cutoff_locks:
            raise ReanalysisError(
                f"{lineage}: no FFT cutoff lock exists for {lock_key}."
            )
        if (
            cutoff_locks[lock_key]["sample_type"].casefold() != "blank"
            or cutoff_locks[lock_key]["source_intensity_column"] != selector
        ):
            raise ReanalysisError(
                f"{lineage}: FFT cutoff lock blank identity differs for {lock_key}."
            )
        used_locks.add(lock_key)
        rows.append(
            {
                "file": file,
                "record_group": ANALYSIS_RECORD_GROUP,
                "sample_type": "blank",
                "concentration_molar": "",
                "concentration_label": "Blank",
                "replicate": "1",
                "accumulation": str(accumulation),
                "instrument": "portable_raman",
                "acquisition": "750_5_5_H",
                "analyte": "",
                "matrix": "AuAgBC substrate without 4-ATP",
                "provenance_status": "raw_author_confirmed",
                "source_record_group": CONFIRMED_BLANK_SOURCE_GROUP,
                "source_axis_status": "vendor_original",
                "blank_replication_design": "one_export_five_technical_scans",
                "intensity_column": selector,
                "baseline_lambda": "8000" if lineage == CONTROLLED_NAME else "",
                "filter_fft_peak_index": cutoff_locks[lock_key][
                    "filter_fft_peak_index"
                ],
                "analysis_lineage": lineage,
            }
        )
    if used_locks != set(cutoff_locks):
        unused = sorted(set(cutoff_locks) - used_locks)
        raise ReanalysisError(
            f"{lineage}: FFT cutoff lock has selectors absent from the manifest: {unused[:5]}"
        )
    validate_manifest_rows(rows, lineage=lineage)
    return rows


def validate_manifest_rows(
    rows: Sequence[Mapping[str, str]], *, lineage: str
) -> None:
    """Enforce the scientific design before any numerical processing."""
    if len(rows) != 200:
        raise ReanalysisError(f"{lineage}: expected 200 manifest rows, found {len(rows)}")
    samples = [row for row in rows if row.get("sample_type") == "4atp"]
    blanks = [row for row in rows if row.get("sample_type") == "blank"]
    if len(samples) != 195 or len(blanks) != 5:
        raise ReanalysisError(
            f"{lineage}: expected 195 samples and five blank channels; found "
            f"{len(samples)} and {len(blanks)}"
        )
    if {row.get("record_group") for row in rows} != {ANALYSIS_RECORD_GROUP}:
        raise ReanalysisError(f"{lineage}: analysis rows do not share one record_group")
    if any("blank_rep" in row.get("file", "").casefold() for row in rows):
        raise ReanalysisError(f"{lineage}: historical composite blank rows are forbidden")
    if {row.get("file") for row in blanks} != {_portable(CONFIRMED_BLANK_RELATIVE)}:
        raise ReanalysisError(f"{lineage}: blank rows do not use the confirmed source")
    if {row.get("intensity_column") for row in blanks} != {"1", "2", "3", "4", "5"}:
        raise ReanalysisError(f"{lineage}: blank selectors must be 1 through 5")
    if {row.get("replicate") for row in blanks} != {"1"} or {
        row.get("accumulation") for row in blanks
    } != {"1", "2", "3", "4", "5"}:
        raise ReanalysisError(
            f"{lineage}: the blank must be one replicate with five technical scans"
        )
    if {row.get("provenance_status") for row in blanks} != {
        "raw_author_confirmed"
    }:
        raise ReanalysisError(f"{lineage}: blank status is not canonical")
    if {row.get("provenance_status") for row in samples} != {"raw_unverified"}:
        raise ReanalysisError(f"{lineage}: sample status must remain raw_unverified")
    if {row.get("instrument") for row in rows} != {"portable_raman"}:
        raise ReanalysisError(f"{lineage}: every row must use portable_raman")
    if {row.get("acquisition") for row in rows} != {"750_5_5_H"}:
        raise ReanalysisError(f"{lineage}: every row must use acquisition 750_5_5_H")
    try:
        locked_peaks = [int(row.get("filter_fft_peak_index", "")) for row in rows]
    except (TypeError, ValueError) as exc:
        raise ReanalysisError(
            f"{lineage}: every row requires an integer filter_fft_peak_index lock"
        ) from exc
    maximum_frequency_index = 219 if lineage == REFERENCE_NAME else 255
    if any(peak < 1 or peak >= maximum_frequency_index for peak in locked_peaks):
        raise ReanalysisError(
            f"{lineage}: filter_fft_peak_index must lie in 1..{maximum_frequency_index - 1}"
        )
    selectors = [
        (row.get("file"), row.get("intensity_column")) for row in rows
    ]
    if len(set(selectors)) != len(selectors):
        raise ReanalysisError(f"{lineage}: duplicate file/intensity-column selector")

    concentration_counts = Counter(
        _decimal(row["concentration_molar"], context=row["file"]) for row in samples
    )
    if set(concentration_counts) != set(CONCENTRATION_LABELS) or set(
        concentration_counts.values()
    ) != {15}:
        raise ReanalysisError(
            f"{lineage}: expected 15 rows at each of the 13 concentrations"
        )
    expected_design = {
        (str(replicate), str(accumulation))
        for replicate in range(1, 4)
        for accumulation in range(1, 6)
    }
    for concentration in CONCENTRATION_LABELS:
        design = {
            (row.get("replicate", ""), row.get("accumulation", ""))
            for row in samples
            if _decimal(row["concentration_molar"], context=row["file"])
            == concentration
        }
        if design != expected_design:
            raise ReanalysisError(
                f"{lineage}: {concentration} does not contain exactly replicates "
                "1-3 crossed with accumulations 1-5"
            )
    for row in samples:
        concentration = _decimal(row["concentration_molar"], context=row["file"])
        if row.get("concentration_label") != CONCENTRATION_LABELS[concentration]:
            raise ReanalysisError(
                f"{lineage}: incorrect label for {concentration}: "
                f"{row.get('concentration_label')!r}"
            )
    hundred_micromolar = [
        row for row in samples if _decimal(row["concentration_molar"], context=row["file"]) == Decimal("1e-4")
    ]
    if len(hundred_micromolar) != 15 or {
        row.get("concentration_label") for row in hundred_micromolar
    } != {"100 µM"}:
        raise ReanalysisError(f"{lineage}: 1e-4 M must be labelled 100 µM")

    if lineage == CONTROLLED_NAME:
        if {row.get("baseline_lambda") for row in samples} != {"3000"}:
            raise ReanalysisError("Controlled samples require explicit lambda=3000")
        if {row.get("baseline_lambda") for row in blanks} != {"8000"}:
            raise ReanalysisError("Controlled blank channels require explicit lambda=8000")
    elif any(row.get("baseline_lambda") for row in rows):
        raise ReanalysisError(
            "reference_2026 must resolve lambda=3000 from its profile, not inherit a legacy override"
        )


def _config_value(*, lineage: str, manifest_name: str) -> dict[str, object]:
    if lineage == CONTROLLED_NAME:
        profile = "legacy_individual"
        stage = "raw"
        output = "../../outputs/reanalysis/optimisation_750_5_5_h_controlled_legacy_confirmed_blank"
    elif lineage == REFERENCE_NAME:
        profile = "reference_2026"
        stage = "processed"
        output = "../../outputs/reanalysis/optimisation_750_5_5_h_reference_2026"
    else:  # pragma: no cover - guarded by callers
        raise ReanalysisError(f"Unknown lineage: {lineage}")
    return {
        "schema_version": SCHEMA_VERSION,
        "profile": profile,
        "manifest": manifest_name,
        "input_root": "../..",
        "output_root": output,
        "options": {
            "blank": {
                "stage": stage,
                "strategy": "mean",
                "interpolation": "linear",
                "group_by": ["record_group", "instrument"],
                "sample_types": ["blank"],
            },
            "aggregation": {"group_by": ["record_group"]},
        },
    }


def expected_configuration_files(repository: Path) -> dict[Path, bytes]:
    directory = repository / CONFIG_DIRECTORY_RELATIVE
    controlled_rows = build_manifest_rows(repository, lineage=CONTROLLED_NAME)
    reference_rows = build_manifest_rows(repository, lineage=REFERENCE_NAME)
    return {
        directory / CONTROLLED_MANIFEST_NAME: _csv_bytes(MANIFEST_FIELDS, controlled_rows),
        directory / CONTROLLED_CONFIG_NAME: _json_bytes(
            _config_value(
                lineage=CONTROLLED_NAME, manifest_name=CONTROLLED_MANIFEST_NAME
            )
        ),
        directory / REFERENCE_MANIFEST_NAME: _csv_bytes(MANIFEST_FIELDS, reference_rows),
        directory / REFERENCE_CONFIG_NAME: _json_bytes(
            _config_value(
                lineage=REFERENCE_NAME, manifest_name=REFERENCE_MANIFEST_NAME
            )
        ),
    }


def write_configuration_files(repository: Path) -> dict[Path, bytes]:
    files = expected_configuration_files(repository)
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return files


def check_configuration_files(repository: Path) -> list[str]:
    errors: list[str] = []
    for path, expected in expected_configuration_files(repository).items():
        if not path.is_file():
            errors.append(f"Missing configuration file: {path.relative_to(repository)}")
        elif path.read_bytes() != expected:
            errors.append(f"Stale configuration file: {path.relative_to(repository)}")
    return errors


def _run_profiles(repository: Path, temporary_root: Path) -> dict[str, LineageRun]:
    directory = repository / CONFIG_DIRECTORY_RELATIVE
    specifications = (
        (
            CONTROLLED_NAME,
            "legacy_individual",
            directory / CONTROLLED_MANIFEST_NAME,
            directory / CONTROLLED_CONFIG_NAME,
        ),
        (
            REFERENCE_NAME,
            "reference_2026",
            directory / REFERENCE_MANIFEST_NAME,
            directory / REFERENCE_CONFIG_NAME,
        ),
    )
    results: dict[str, LineageRun] = {}
    for name, profile, manifest, config in specifications:
        output = temporary_root / name
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            run = process_job(
                config,
                output_root=output,
                input_root=repository,
            )
        library_warnings = tuple(
            sorted(
                {
                    f"{item.category.__name__}: {item.message}"
                    for item in captured
                }
            )
        )
        counts = run.get("counts", {})
        expected_counts = {
            "manifest_rows": 200,
            "source_files": 196,
            "scan_spectra": 200,
            "blank_spectra": 5,
            "replicate_spectra": 40,
            "concentration_spectra": 14,
        }
        for key, expected in expected_counts.items():
            if int(counts.get(key, -1)) != expected:
                raise ReanalysisError(
                    f"{name}: expected {key}={expected}, found {counts.get(key)!r}"
                )
        if run.get("warnings"):
            raise ReanalysisError(f"{name}: pipeline warnings: {run['warnings']}")
        results[name] = LineageRun(
            name=name,
            profile=profile,
            manifest_path=manifest,
            config_path=config,
            output_path=output,
            run=run,
            numerical_library_warnings=library_warnings,
        )
    _validate_resolved_lambdas(results)
    cutoff_locks = _fft_cutoff_locks(repository)
    for name in (CONTROLLED_NAME, REFERENCE_NAME):
        _validate_resolved_fft_locks(
            results[name].output_path, cutoff_locks[name], label=name
        )
    return results


def _validate_historical_replay(
    repository: Path, temporary_root: Path
) -> dict[str, object]:
    """Freshly prove that the current legacy profile reproduces the snapshot.

    This guard makes the later historical-versus-controlled comparison a true
    blank-only comparison. If the legacy implementation drifts, generation and
    ``--check`` stop before publishing or accepting new comparison products.
    """
    source_manifest = repository / "metadata" / "raw_processing_manifest.csv"
    fieldnames, all_rows = _read_csv_rows(source_manifest)
    rows = [
        dict(row)
        for row in all_rows
        if row.get("record_group", "").strip() == SOURCE_RECORD_GROUP
    ]
    rows.sort(key=lambda row: (row["file"].casefold(), row["file"]))
    cutoff_locks = _fft_cutoff_locks(repository)[HISTORICAL_NAME]
    used_locks: set[tuple[str, str]] = set()
    for row in rows:
        file = row["file"].replace("\\", "/")
        lock_key = (file, "1")
        if lock_key not in cutoff_locks:
            raise ReanalysisError(
                f"Historical replay has no FFT cutoff lock for {lock_key}."
            )
        lock = cutoff_locks[lock_key]
        if lock["sample_type"].casefold() != row.get("sample_type", "").casefold():
            raise ReanalysisError(
                f"Historical FFT cutoff lock sample type differs for {file}."
            )
        row["intensity_column"] = "1"
        row["filter_fft_peak_index"] = lock["filter_fft_peak_index"]
        used_locks.add(lock_key)
    if used_locks != set(cutoff_locks):
        unused = sorted(set(cutoff_locks) - used_locks)
        raise ReanalysisError(
            f"Historical FFT cutoff lock has selectors absent from replay: {unused[:5]}"
        )
    for field in ("intensity_column", "filter_fft_peak_index"):
        if field not in fieldnames:
            fieldnames.append(field)
    samples = [row for row in rows if row.get("sample_type", "").casefold() == "4atp"]
    blanks = [row for row in rows if row.get("sample_type", "").casefold() == "blank"]
    if len(rows) != 210 or len(samples) != 195 or len(blanks) != 15:
        raise ReanalysisError(
            "Historical replay requires 195 sample rows and the preserved "
            f"15-row mixed blank; found {len(samples)} and {len(blanks)}."
        )
    if {row.get("instrument") for row in rows} != {"portable_raman"} or {
        row.get("acquisition") for row in rows
    } != {"750_5_5_H"}:
        raise ReanalysisError(
            "Historical replay rows must all be portable_raman acquisition 750_5_5_H."
        )
    selectors = [(row.get("file"), row.get("intensity_column", "")) for row in rows]
    if len(set(selectors)) != len(selectors):
        raise ReanalysisError("Historical replay manifest contains duplicate selectors.")

    expected_design = {
        (concentration, str(replicate), str(accumulation))
        for concentration in CONCENTRATION_LABELS
        for replicate in range(1, 4)
        for accumulation in range(1, 6)
    }
    observed_design = {
        (
            _decimal(row["concentration_molar"], context=row["file"]),
            row.get("replicate", ""),
            row.get("accumulation", ""),
        )
        for row in samples
    }
    if observed_design != expected_design:
        raise ReanalysisError(
            "Historical replay samples do not contain the complete 13 x 3 x 5 design."
        )

    temporary_root.mkdir(parents=True, exist_ok=True)
    manifest_path = temporary_root / "historical_composite_manifest.csv"
    manifest_path.write_bytes(_csv_bytes(fieldnames, rows))
    output_path = temporary_root / "run"
    run = process_job(
        manifest_path,
        output_root=output_path,
        input_root=repository,
        profile_name="legacy_individual",
    )
    if run.get("warnings"):
        raise ReanalysisError(f"Historical replay pipeline warnings: {run['warnings']}")
    expected_counts = {
        "manifest_rows": 210,
        "source_files": 210,
        "scan_spectra": 210,
        "blank_spectra": 15,
    }
    for key, expected in expected_counts.items():
        if int(run.get("counts", {}).get(key, -1)) != expected:
            raise ReanalysisError(
                f"Historical replay expected {key}={expected}, found "
                f"{run.get('counts', {}).get(key)!r}."
            )

    _, resolved_rows = _read_csv_rows(output_path / "resolved_manifest.csv")
    _validate_resolved_fft_locks(
        output_path, cutoff_locks, label=HISTORICAL_NAME
    )
    historical_root = repository / HISTORICAL_PROCESSED_RELATIVE
    expected_names = {Path(row["processed_file"]).name for row in resolved_rows}
    historical_names = {
        path.name
        for path in historical_root.glob("*_blank_subtracted_processed.csv")
    }
    if expected_names != historical_names:
        missing = sorted(expected_names - historical_names)
        extra = sorted(historical_names - expected_names)
        raise ReanalysisError(
            "Historical replay file set differs from the preserved snapshot; "
            f"missing={missing[:5]}, extra={extra[:5]}."
        )

    max_abs_x = 0.0
    max_abs_y = 0.0
    sample_count = 0
    blank_count = 0
    for row in resolved_rows:
        relative = Path(row["processed_file"])
        fresh = _read_arrays(output_path / relative)
        preserved = _read_arrays(historical_root / relative.name)
        if fresh.x.shape != preserved.x.shape or fresh.y.shape != preserved.y.shape:
            raise ReanalysisError(
                f"Historical replay shape differs for {relative.name}."
            )
        delta_x = float(np.max(np.abs(fresh.x - preserved.x)))
        delta_y = float(np.max(np.abs(fresh.y - preserved.y)))
        max_abs_x = max(max_abs_x, delta_x)
        max_abs_y = max(max_abs_y, delta_y)
        if not np.allclose(fresh.x, preserved.x, rtol=0.0, atol=1e-9) or not np.allclose(
            fresh.y, preserved.y, rtol=0.0, atol=1e-9
        ):
            raise ReanalysisError(
                f"Historical replay exceeds 1e-9 absolute tolerance for {relative.name}: "
                f"max |delta x|={delta_x:.6g}, max |delta y|={delta_y:.6g}."
            )
        if row.get("sample_type", "").casefold() == "blank":
            blank_count += 1
        else:
            sample_count += 1

    if sample_count != 195 or blank_count != 15:
        raise ReanalysisError(
            f"Historical replay compared {sample_count} samples and {blank_count} blanks."
        )
    return {
        "profile": "legacy_individual",
        "comparison": "fresh historical-composite replay versus preserved snapshot",
        "absolute_tolerance": 1e-9,
        "spectra_compared": len(resolved_rows),
        "sample_spectra_compared": sample_count,
        "historical_blank_spectra_compared": blank_count,
        "max_abs_raman_shift_difference_cm-1": max_abs_x,
        "max_abs_intensity_difference": max_abs_y,
        "fft_cutoff_lock": {
            "path": _portable(FFT_CUTOFF_LOCK_RELATIVE),
            "sha256": sha256_file(repository / FFT_CUTOFF_LOCK_RELATIVE),
            "records_pinned": len(cutoff_locks),
        },
        "status": "pass",
    }


def _validate_resolved_lambdas(runs: Mapping[str, LineageRun]) -> None:
    for name, expected_sample_source, expected_blank_source in (
        (CONTROLLED_NAME, "manifest", "manifest"),
        (REFERENCE_NAME, "profile", "profile"),
    ):
        _, report_rows = _read_csv_rows(runs[name].output_path / "processing_report.csv")
        if len(report_rows) != 200:
            raise ReanalysisError(f"{name}: processing report does not contain 200 rows")
        for row in report_rows:
            parameters = json.loads(row["resolved_parameters_json"])
            first = parameters["first_baseline"]
            is_blank = row["file"] == _portable(CONFIRMED_BLANK_RELATIVE)
            expected_lambda = 8000.0 if name == CONTROLLED_NAME and is_blank else 3000.0
            if not math.isclose(float(first["lambda"]), expected_lambda):
                raise ReanalysisError(
                    f"{name}: incorrect resolved lambda for {row['record_id']}: {first['lambda']}"
                )
            expected_source = expected_blank_source if is_blank else expected_sample_source
            if first.get("lambda_source") != expected_source:
                raise ReanalysisError(
                    f"{name}: incorrect lambda source for {row['record_id']}: "
                    f"{first.get('lambda_source')!r}"
                )


def _validate_resolved_fft_locks(
    output_path: Path,
    locks: Mapping[tuple[str, str], Mapping[str, str]],
    *,
    label: str,
) -> None:
    """Require every processed record to consume its audited cutoff lock."""
    _, report_rows = _read_csv_rows(output_path / "processing_report.csv")
    by_record = {row["record_id"]: row for row in locks.values()}
    if len(by_record) != len(locks) or len(report_rows) != len(locks):
        raise ReanalysisError(
            f"{label}: processing report and FFT cutoff lock counts differ."
        )
    observed_ids = {row["record_id"] for row in report_rows}
    if observed_ids != set(by_record):
        missing = sorted(set(by_record) - observed_ids)
        extra = sorted(observed_ids - set(by_record))
        raise ReanalysisError(
            f"{label}: FFT cutoff lock record IDs differ; missing={missing[:5]}, extra={extra[:5]}."
        )
    for report in report_rows:
        lock = by_record[report["record_id"]]
        if (
            report["file"] != lock["file"]
            or report["source_intensity_column"]
            != lock["source_intensity_column"]
            or int(report["points"]) != int(lock["spectrum_points"])
        ):
            raise ReanalysisError(
                f"{label}: FFT cutoff lock identity differs for {report['record_id']}."
            )
        resolved = json.loads(report["resolved_parameters_json"])["filter"]
        if (
            int(resolved.get("fft_peak_index", -1))
            != int(lock["filter_fft_peak_index"])
            or not np.isclose(
                float(resolved.get("cutoff", math.nan)),
                float(lock["normalized_cutoff"]),
                rtol=0.0,
                atol=1e-15,
            )
            or float(resolved.get("percentile", math.nan))
            != float(lock["percentile"])
            or int(resolved.get("order", -1)) != int(lock["order"])
            or resolved.get("cutoff_source")
            != "manifest_filter_fft_peak_index"
            or resolved.get("tie_break") != "explicit_peak_index"
        ):
            raise ReanalysisError(
                f"{label}: record {report['record_id']} did not consume its FFT cutoff lock."
            )


def _read_arrays(path: Path) -> SpectrumArrays:
    spectra = read_spectrum_file(path)
    if len(spectra) != 1:
        raise ReanalysisError(f"Expected one intensity column in {path}, found {len(spectra)}")
    return SpectrumArrays(spectra[0].x.copy(), spectra[0].y.copy())


def _clean_xy(arrays: SpectrumArrays) -> SpectrumArrays:
    order = np.argsort(arrays.x, kind="mergesort")
    x = np.asarray(arrays.x[order], dtype=float)
    y = np.asarray(arrays.y[order], dtype=float)
    unique, inverse, counts = np.unique(x, return_inverse=True, return_counts=True)
    if len(unique) != len(x):
        y = np.bincount(inverse, weights=y) / counts
        x = unique
    return SpectrumArrays(x, y)


def _interpolate(arrays: SpectrumArrays, grid: np.ndarray) -> np.ndarray:
    cleaned = _clean_xy(arrays)
    tolerance = 1e-8
    if grid[0] < cleaned.x[0] - tolerance or grid[-1] > cleaned.x[-1] + tolerance:
        raise ReanalysisError(
            "Comparison grid extends outside a spectrum's Raman-shift range: "
            f"grid={grid[0]:.9g}..{grid[-1]:.9g}, "
            f"spectrum={cleaned.x[0]:.9g}..{cleaned.x[-1]:.9g}"
        )
    return np.interp(grid, cleaned.x, cleaned.y)


def _metrics(left: np.ndarray, right: np.ndarray) -> dict[str, float]:
    left = np.asarray(left, dtype=float)
    right = np.asarray(right, dtype=float)
    if left.shape != right.shape or left.ndim != 1 or not len(left):
        raise ReanalysisError("Metric arrays must be non-empty one-dimensional peers")
    difference = right - left
    rmse = float(np.sqrt(np.mean(difference**2)))
    mae = float(np.mean(np.abs(difference)))
    denominator = float(np.ptp(left))
    l2_denominator = float(np.linalg.norm(left))
    if np.std(left) == 0 or np.std(right) == 0:
        pearson = math.nan
    else:
        pearson = float(np.corrcoef(left, right)[0, 1])
    return {
        "rmse": rmse,
        "mae": mae,
        "max_abs": float(np.max(np.abs(difference))),
        "mean_signed_difference": float(np.mean(difference)),
        "pearson_r": pearson,
        "nrmse_percent_of_left_range": (
            100.0 * rmse / denominator if denominator != 0 else math.nan
        ),
        "relative_l2_percent": (
            100.0 * float(np.linalg.norm(difference)) / l2_denominator
            if l2_denominator != 0
            else math.nan
        ),
    }


def _resolved_sample_map(run: LineageRun) -> dict[str, str]:
    _, rows = _read_csv_rows(run.output_path / "resolved_manifest.csv")
    result = {
        row["file"]: row["processed_file"]
        for row in rows
        if row.get("sample_type") == "4atp"
    }
    if len(result) != 195:
        raise ReanalysisError(f"{run.name}: resolved manifest maps {len(result)} samples")
    return result


def _load_sample_records(
    repository: Path, runs: Mapping[str, LineageRun]
) -> list[SampleRecord]:
    controlled_rows = build_manifest_rows(repository, lineage=CONTROLLED_NAME)
    metadata = {
        row["file"]: row for row in controlled_rows if row["sample_type"] == "4atp"
    }
    controlled_map = _resolved_sample_map(runs[CONTROLLED_NAME])
    reference_map = _resolved_sample_map(runs[REFERENCE_NAME])
    records: list[SampleRecord] = []
    for file_value in sorted(metadata, key=lambda value: (value.casefold(), value)):
        row = metadata[file_value]
        raw_path = repository / Path(file_value)
        historical_path = (
            raw_path.parent
            / "Processed Spectra"
            / f"{raw_path.stem}_blank_subtracted_processed.csv"
        )
        if not historical_path.is_file():
            raise ReanalysisError(f"Historical derivative is missing: {historical_path}")
        records.append(
            SampleRecord(
                file=file_value,
                concentration_molar=row["concentration_molar"],
                concentration_label=row["concentration_label"],
                replicate=row["replicate"],
                accumulation=row["accumulation"],
                historical=_read_arrays(historical_path),
                controlled=_read_arrays(
                    runs[CONTROLLED_NAME].output_path / controlled_map[file_value]
                ),
                reference=_read_arrays(
                    runs[REFERENCE_NAME].output_path / reference_map[file_value]
                ),
            )
        )
    if len(records) != 195:
        raise ReanalysisError(f"Expected 195 sample records, found {len(records)}")
    return records


def _arrays_for(record: SampleRecord, name: str) -> SpectrumArrays:
    return getattr(record, name)


def _aligned_pair(
    left: SpectrumArrays, right: SpectrumArrays
) -> tuple[np.ndarray, np.ndarray, np.ndarray, str, float]:
    right_clean = _clean_xy(right)
    left_clean = _clean_xy(left)
    if len(left_clean.x) == len(right_clean.x) and np.allclose(
        left_clean.x, right_clean.x, rtol=1e-12, atol=1e-9
    ):
        axis_difference = float(np.max(np.abs(left_clean.x - right_clean.x)))
        return (
            right_clean.x,
            left_clean.y,
            right_clean.y,
            "shared_native_grid",
            axis_difference,
        )
    grid = right_clean.x
    return (
        grid,
        _interpolate(left_clean, grid),
        right_clean.y,
        "right_lineage_grid_linear_interpolation",
        math.nan,
    )


def _comparison_base(
    comparison_id: str,
    left_lineage: str,
    right_lineage: str,
    interpretation: str,
) -> dict[str, str]:
    return {
        "comparison_id": comparison_id,
        "left_lineage": left_lineage,
        "right_lineage": right_lineage,
        "interpretation": interpretation,
    }


def _scan_metrics(records: Sequence[SampleRecord]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for comparison_id, left_lineage, right_lineage, interpretation, left_name, right_name in COMPARISONS:
        for record in records:
            grid, left_y, right_y, grid_basis, axis_difference = _aligned_pair(
                _arrays_for(record, left_name), _arrays_for(record, right_name)
            )
            rows.append(
                {
                    **_comparison_base(
                        comparison_id, left_lineage, right_lineage, interpretation
                    ),
                    "file": record.file,
                    "concentration_molar": record.concentration_molar,
                    "concentration_label": record.concentration_label,
                    "replicate": record.replicate,
                    "accumulation": record.accumulation,
                    "grid_basis": grid_basis,
                    "n_points": len(grid),
                    "x_min_cm-1": float(grid[0]),
                    "x_max_cm-1": float(grid[-1]),
                    "axis_max_abs_difference_cm-1": axis_difference,
                    **_metrics(left_y, right_y),
                }
            )
    return rows


def _concentration_arrays(
    members: Sequence[SampleRecord], lineage: str, grid: np.ndarray
) -> np.ndarray:
    return np.mean(
        np.vstack([_interpolate(_arrays_for(member, lineage), grid) for member in members]),
        axis=0,
    )


def _concentration_metrics(
    records: Sequence[SampleRecord],
) -> list[dict[str, object]]:
    groups: dict[str, list[SampleRecord]] = defaultdict(list)
    for record in records:
        groups[record.concentration_molar].append(record)
    if len(groups) != 13 or {len(members) for members in groups.values()} != {15}:
        raise ReanalysisError("Concentration comparison requires 13 groups of 15 scans")
    rows: list[dict[str, object]] = []
    for comparison_id, left_lineage, right_lineage, interpretation, left_name, right_name in COMPARISONS:
        for concentration in sorted(groups, key=Decimal, reverse=True):
            members = groups[concentration]
            if right_name == "reference":
                grid = _clean_xy(members[0].reference).x
                grid_basis = "reference_2026_grid_linear_interpolation"
            else:
                grid = _clean_xy(members[0].controlled).x
                grid_basis = "controlled_legacy_native_grid"
            left_y = _concentration_arrays(members, left_name, grid)
            right_y = _concentration_arrays(members, right_name, grid)
            rows.append(
                {
                    **_comparison_base(
                        comparison_id, left_lineage, right_lineage, interpretation
                    ),
                    "concentration_molar": concentration,
                    "concentration_label": members[0].concentration_label,
                    "n_replicates": 3,
                    "n_scans": 15,
                    "grid_basis": grid_basis,
                    "n_points": len(grid),
                    "x_min_cm-1": float(grid[0]),
                    "x_max_cm-1": float(grid[-1]),
                    **_metrics(left_y, right_y),
                }
            )
    return rows


def _peak_row(
    *,
    base: Mapping[str, object],
    level: str,
    grid: np.ndarray,
    left_y: np.ndarray,
    right_y: np.ndarray,
    spec: PeakSpec,
) -> dict[str, object]:
    left_value, left_shift, left_points = peak_value(grid, left_y, spec)
    right_value, right_shift, right_points = peak_value(grid, right_y, spec)
    change = right_value - left_value
    return {
        **base,
        "level": level,
        "band": spec.output_name,
        "center_cm-1": spec.center_cm1,
        "window_cm-1": spec.window_cm1,
        "left_peak_value": left_value,
        "right_peak_value": right_value,
        "absolute_change": change,
        "percent_change_from_left": (
            100.0 * change / left_value if left_value != 0 else math.nan
        ),
        "left_observed_shift_cm-1": left_shift,
        "right_observed_shift_cm-1": right_shift,
        "left_n_points": left_points,
        "right_n_points": right_points,
    }


def _peak_metrics(
    records: Sequence[SampleRecord],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for comparison_id, left_lineage, right_lineage, interpretation, left_name, right_name in COMPARISONS:
        comparison = _comparison_base(
            comparison_id, left_lineage, right_lineage, interpretation
        )
        for record in records:
            grid, left_y, right_y, _, _ = _aligned_pair(
                _arrays_for(record, left_name), _arrays_for(record, right_name)
            )
            base = {
                **comparison,
                "file": record.file,
                "concentration_molar": record.concentration_molar,
                "concentration_label": record.concentration_label,
                "replicate": record.replicate,
                "accumulation": record.accumulation,
            }
            for spec in PEAK_SPECS:
                rows.append(
                    _peak_row(
                        base=base,
                        level="scan",
                        grid=grid,
                        left_y=left_y,
                        right_y=right_y,
                        spec=spec,
                    )
                )
        concentrations = sorted(
            {
                record.concentration_molar
                for record in records
            },
            key=Decimal,
            reverse=True,
        )
        labels = {record.concentration_molar: record.concentration_label for record in records}
        for concentration in concentrations:
            members = [
                record for record in records if record.concentration_molar == concentration
            ]
            base = {
                **comparison,
                "file": "",
                "concentration_molar": concentration,
                "concentration_label": labels[concentration],
                "replicate": "",
                "accumulation": "",
            }
            for spec in PEAK_SPECS:
                def aggregate(lineage: str) -> tuple[float, float, int]:
                    replicate_values: list[float] = []
                    observed_values: list[float] = []
                    point_counts: list[int] = []
                    for replicate in sorted({member.replicate for member in members}):
                        scan_values: list[float] = []
                        scan_observed: list[float] = []
                        for member in members:
                            if member.replicate != replicate:
                                continue
                            arrays = _clean_xy(_arrays_for(member, lineage))
                            value, observed, points = peak_value(
                                arrays.x, arrays.y, spec
                            )
                            scan_values.append(value)
                            scan_observed.append(observed)
                            point_counts.append(points)
                        replicate_values.append(float(np.mean(scan_values)))
                        observed_values.append(float(np.mean(scan_observed)))
                    return (
                        float(np.mean(replicate_values)),
                        float(np.mean(observed_values)),
                        min(point_counts),
                    )

                left_value, left_shift, left_points = aggregate(left_name)
                right_value, right_shift, right_points = aggregate(right_name)
                change = right_value - left_value
                rows.append(
                    {
                        **base,
                        "level": "concentration_mean_of_replicate_peak_means",
                        "band": spec.output_name,
                        "center_cm-1": spec.center_cm1,
                        "window_cm-1": spec.window_cm1,
                        "left_peak_value": left_value,
                        "right_peak_value": right_value,
                        "absolute_change": change,
                        "percent_change_from_left": (
                            100.0 * change / left_value
                            if left_value != 0
                            else math.nan
                        ),
                        "left_observed_shift_cm-1": left_shift,
                        "right_observed_shift_cm-1": right_shift,
                        "left_n_points": left_points,
                        "right_n_points": right_points,
                    }
                )
    return rows


def _historical_blank_paths(repository: Path) -> list[Path]:
    _, rows = _read_csv_rows(repository / "metadata" / "raw_processing_manifest.csv")
    selected = [
        repository / Path(row["file"])
        for row in rows
        if row.get("record_group") == SOURCE_RECORD_GROUP
        and row.get("sample_type", "").casefold() == "blank"
    ]
    selected.sort(key=lambda path: (path.as_posix().casefold(), path.as_posix()))
    if len(selected) != 15:
        raise ReanalysisError(f"Expected 15 historical composite blank files, found {len(selected)}")
    return selected


def _blank_reference_metrics(
    repository: Path, records: Sequence[SampleRecord]
) -> tuple[list[dict[str, object]], dict[str, object]]:
    sample_raw = _read_arrays(repository / Path(records[0].file))
    grid = _clean_xy(sample_raw).x
    def constant_interpolation(arrays: SpectrumArrays) -> np.ndarray:
        cleaned = _clean_xy(arrays)
        return np.interp(grid, cleaned.x, cleaned.y)

    historical_stack = np.vstack(
        [constant_interpolation(_read_arrays(path)) for path in _historical_blank_paths(repository)]
    )
    confirmed_spectra = read_spectrum_file(repository / CONFIRMED_BLANK_RELATIVE)
    if len(confirmed_spectra) != 5:
        raise ReanalysisError(
            f"Confirmed blank must contain five channels, found {len(confirmed_spectra)}"
        )
    confirmed_stack = np.vstack(
        [
            constant_interpolation(SpectrumArrays(item.x, item.y))
            for item in confirmed_spectra
        ]
    )
    historical_mean = np.mean(historical_stack, axis=0)
    confirmed_mean = np.mean(confirmed_stack, axis=0)

    first_confirmed = _clean_xy(
        SpectrumArrays(confirmed_spectra[0].x, confirmed_spectra[0].y)
    )
    sample_clean = _clean_xy(sample_raw)
    if len(first_confirmed.x) == len(sample_clean.x):
        axis_delta = sample_clean.x - first_confirmed.x
        axis_summary = {
            "sample_minus_confirmed_blank_axis_mean_cm-1": float(np.mean(axis_delta)),
            "sample_minus_confirmed_blank_axis_min_cm-1": float(np.min(axis_delta)),
            "sample_minus_confirmed_blank_axis_max_cm-1": float(np.max(axis_delta)),
        }
    else:
        axis_summary = {
            "sample_minus_confirmed_blank_axis_mean_cm-1": None,
            "sample_minus_confirmed_blank_axis_min_cm-1": None,
            "sample_minus_confirmed_blank_axis_max_cm-1": None,
        }

    rows: list[dict[str, object]] = []
    scopes = [("overall", None), *[(spec.output_name, spec) for spec in PEAK_SPECS]]
    for scope, spec in scopes:
        if spec is None:
            mask = np.ones(len(grid), dtype=bool)
            center = math.nan
            window = math.nan
        else:
            mask = (grid >= spec.center_cm1 - spec.window_cm1) & (
                grid <= spec.center_cm1 + spec.window_cm1
            )
            center = spec.center_cm1
            window = spec.window_cm1
        values = _metrics(historical_mean[mask], confirmed_mean[mask])
        rows.append(
            {
                "scope": scope,
                "center_cm-1": center,
                "window_cm-1": window,
                "n_points": int(np.sum(mask)),
                "historical_blank_files": 15,
                "confirmed_blank_exports": 1,
                "confirmed_blank_channels": 5,
                "grid_basis": "prepared_sample_axis_linear_interpolation",
                **values,
            }
        )
    return rows, axis_summary


def _finite_median(rows: Iterable[Mapping[str, object]], field: str) -> float:
    values = [float(row[field]) for row in rows if math.isfinite(float(row[field]))]
    if not values:
        return math.nan
    return float(statistics.median(values))


def _comparison_summary(
    scan_rows: Sequence[Mapping[str, object]],
    concentration_rows: Sequence[Mapping[str, object]],
    peak_rows: Sequence[Mapping[str, object]],
    blank_rows: Sequence[Mapping[str, object]],
    axis_summary: Mapping[str, object],
) -> dict[str, object]:
    comparisons: dict[str, object] = {}
    for comparison_id, _, _, interpretation, _, _ in COMPARISONS:
        comparison_summary: dict[str, object] = {"interpretation": interpretation}
        for level, rows in (
            ("scan", [row for row in scan_rows if row["comparison_id"] == comparison_id]),
            (
                "concentration_mean",
                [row for row in concentration_rows if row["comparison_id"] == comparison_id],
            ),
        ):
            comparison_summary[level] = {
                "count": len(rows),
                "median_rmse": _finite_median(rows, "rmse"),
                "median_mae": _finite_median(rows, "mae"),
                "median_pearson_r": _finite_median(rows, "pearson_r"),
                "median_nrmse_percent_of_left_range": _finite_median(
                    rows, "nrmse_percent_of_left_range"
                ),
            }
        peak_summary: dict[str, object] = {}
        for level in ("scan", "concentration_mean_of_replicate_peak_means"):
            for spec in PEAK_SPECS:
                selected = [
                    row
                    for row in peak_rows
                    if row["comparison_id"] == comparison_id
                    and row["level"] == level
                    and row["band"] == spec.output_name
                ]
                peak_summary[f"{level}:{spec.output_name}"] = {
                    "count": len(selected),
                    "median_percent_change_from_left": _finite_median(
                        selected, "percent_change_from_left"
                    ),
                }
        comparison_summary["peaks"] = peak_summary
        comparisons[comparison_id] = comparison_summary
    overall_blank = next(row for row in blank_rows if row["scope"] == "overall")
    return {
        "schema_version": 1,
        "scope": "portable 4-ATP optimisation 750_5_5_H",
        "counts": {
            "sample_spectra": 195,
            "concentrations": 13,
            "sample_replicates_per_concentration": 3,
            "technical_scans_per_sample_replicate": 5,
            "confirmed_blank_exports": 1,
            "confirmed_blank_channels": 5,
            "historical_composite_blank_files": 15,
        },
        "blank_reference": {
            "rmse": overall_blank["rmse"],
            "mae": overall_blank["mae"],
            "mean_signed_difference_confirmed_minus_historical": overall_blank[
                "mean_signed_difference"
            ],
            "max_abs": overall_blank["max_abs"],
            "pearson_r": overall_blank["pearson_r"],
            **axis_summary,
        },
        "comparisons": comparisons,
        "interpretation_limits": [
            "Historical versus controlled legacy isolates the blank-only effect.",
            "Controlled legacy versus reference_2026 is a workflow effect.",
            "Historical versus reference_2026 combines blank and workflow effects.",
            "The 195 prepared sample spectra remain raw_unverified.",
            "The confirmed blank is one physical export with five technical scans, not independent substrates.",
            "reference_2026 is not automatically more accurate or scientifically preferred.",
        ],
    }


def _write_comparison_package(
    directory: Path,
    scan_rows: Sequence[Mapping[str, object]],
    concentration_rows: Sequence[Mapping[str, object]],
    peak_rows: Sequence[Mapping[str, object]],
    blank_rows: Sequence[Mapping[str, object]],
    summary: Mapping[str, object],
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    scan_fields = (
        "comparison_id",
        "left_lineage",
        "right_lineage",
        "interpretation",
        "file",
        "concentration_molar",
        "concentration_label",
        "replicate",
        "accumulation",
        "grid_basis",
        "n_points",
        "x_min_cm-1",
        "x_max_cm-1",
        "axis_max_abs_difference_cm-1",
        "rmse",
        "mae",
        "max_abs",
        "mean_signed_difference",
        "pearson_r",
        "nrmse_percent_of_left_range",
        "relative_l2_percent",
    )
    concentration_fields = tuple(
        field
        for field in scan_fields
        if field
        not in {"file", "replicate", "accumulation", "axis_max_abs_difference_cm-1"}
    )
    concentration_fields = (
        *concentration_fields[:8],
        "n_replicates",
        "n_scans",
        *concentration_fields[8:],
    )
    peak_fields = (
        "comparison_id",
        "left_lineage",
        "right_lineage",
        "interpretation",
        "level",
        "file",
        "concentration_molar",
        "concentration_label",
        "replicate",
        "accumulation",
        "band",
        "center_cm-1",
        "window_cm-1",
        "left_peak_value",
        "right_peak_value",
        "absolute_change",
        "percent_change_from_left",
        "left_observed_shift_cm-1",
        "right_observed_shift_cm-1",
        "left_n_points",
        "right_n_points",
    )
    blank_fields = (
        "scope",
        "center_cm-1",
        "window_cm-1",
        "n_points",
        "historical_blank_files",
        "confirmed_blank_exports",
        "confirmed_blank_channels",
        "grid_basis",
        "rmse",
        "mae",
        "max_abs",
        "mean_signed_difference",
        "pearson_r",
        "nrmse_percent_of_left_range",
        "relative_l2_percent",
    )
    (directory / "scan_level_comparison_metrics.csv").write_bytes(
        _csv_bytes(scan_fields, scan_rows)
    )
    (directory / "concentration_level_comparison_metrics.csv").write_bytes(
        _csv_bytes(concentration_fields, concentration_rows)
    )
    (directory / "peak_level_comparison_metrics.csv").write_bytes(
        _csv_bytes(peak_fields, peak_rows)
    )
    (directory / "blank_reference_comparison.csv").write_bytes(
        _csv_bytes(blank_fields, blank_rows)
    )
    (directory / "comparison_summary.json").write_bytes(_json_bytes(summary))
    (directory / "README.md").write_text(
        "# High-power 4-ATP comparison tables\n\n"
        "These tables keep blank-only, workflow-only, and combined effects separate. "
        "Positive differences are right lineage minus left lineage. The source samples "
        "remain `raw_unverified`; see `docs/4ATP_HIGH_POWER_REANALYSIS.md`.\n",
        encoding="utf-8",
        newline="\n",
    )


def _gzip_deterministic(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as input_handle, destination.open("wb") as raw_output:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=raw_output, mtime=0, compresslevel=9
        ) as compressed:
            shutil.copyfileobj(input_handle, compressed)


def _zip_processed_spectra(source_directory: Path, destination: Path) -> int:
    paths = sorted(
        source_directory.glob("*.csv"), key=lambda path: (path.name.casefold(), path.name)
    )
    if len(paths) != 200:
        raise ReanalysisError(
            f"Expected 200 processed spectrum files in {source_directory}, found {len(paths)}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for path in paths:
            info = zipfile.ZipInfo(
                filename=(Path("processed_spectra") / path.name).as_posix(),
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return len(paths)


def _package_readme(name: str) -> str:
    if name == CONTROLLED_NAME:
        description = (
            "This controlled package uses the confirmed blank with the recovered "
            "legacy_individual chain. Comparing it with the preserved historical "
            "outputs isolates the blank-only effect."
        )
    else:
        description = (
            "This package uses reference_2026 and the confirmed blank. It is a "
            "separate modern workflow sensitivity analysis, not a paper reproduction "
            "or an automatically preferred result."
        )
    return (
        f"# {name}\n\n{description}\n\n"
        "`spectra_scan.csv.gz` contains every processed scan in long form. "
        "`processed_spectra.zip` contains 200 two-column CSV members. The resolved "
        "manifest paths refer to members inside that ZIP. Aggregates, peaks, the "
        "processing report, and source metadata remain directly readable. "
        "`run.json` is omitted because it contains execution timestamps and an "
        "OS-specific platform string. `package_metadata.json` retains the exact "
        "Python/dependency versions, code-file hashes, deterministic method and "
        "count metadata, run-level warnings, per-record warning counts, and captured "
        "numerical-library warnings. The manifest-visible `filter_fft_peak_index` "
        "values come from the audited cutoff lock and prevent hardware-dependent "
        "midpoint ties from changing a replayed filter.\n"
    )


def _record_warning_counts(report_path: Path) -> dict[str, int]:
    _, rows = _read_csv_rows(report_path)
    counts: Counter[str] = Counter()
    for row in rows:
        for warning_text in (row.get("warnings") or "").split(" | "):
            warning_text = warning_text.strip()
            if warning_text:
                counts[warning_text] += 1
    return dict(sorted(counts.items()))


def _write_lineage_package(
    directory: Path,
    lineage: LineageRun,
    historical_replay: Mapping[str, object],
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for filename in SELECTED_PIPELINE_FILES:
        source = lineage.output_path / filename
        destination = directory / filename
        if source.suffix.casefold() == ".json":
            # Pipeline JSON is written with the host newline convention. Re-emit
            # canonical JSON so persistent package bytes and hashes are identical
            # on Windows and Linux.
            destination.write_bytes(
                _json_bytes(json.loads(source.read_text(encoding="utf-8")))
            )
        else:
            shutil.copy2(source, destination)
    _gzip_deterministic(
        lineage.output_path / "spectra_scan.csv", directory / "spectra_scan.csv.gz"
    )
    member_count = _zip_processed_spectra(
        lineage.output_path / "processed_spectra",
        directory / "processed_spectra.zip",
    )
    run = lineage.run
    repository = lineage.config_path.parents[2]
    software = {
        key: value
        for key, value in run["software"].items()
        if key != "platform"
    }
    software["dependencies"] = dict(software["dependencies"])
    software["dependencies"]["pytest"] = _installed_distribution_version("pytest")
    software["system"] = platform.system()
    software["machine"] = platform.machine()
    metadata = {
        "schema_version": 1,
        "lineage": lineage.name,
        "profile": lineage.profile,
        "run_id": run["run_id"],
        "counts": run["counts"],
        "grid": run["grid"],
        "software_environment": software,
        "environment_constraints": {
            "path": _portable(RELEASE_REQUIREMENTS_RELATIVE),
            "sha256": sha256_file(repository / RELEASE_REQUIREMENTS_RELATIVE),
        },
        "fft_cutoff_lock": {
            "path": _portable(FFT_CUTOFF_LOCK_RELATIVE),
            "sha256": sha256_file(repository / FFT_CUTOFF_LOCK_RELATIVE),
            "lineage": lineage.name,
            "records_pinned": 200,
        },
        "code_identity": _code_identity(repository),
        "run_warnings": run["warnings"],
        "record_warning_counts": _record_warning_counts(
            lineage.output_path / "processing_report.csv"
        ),
        "numerical_library_warnings": list(lineage.numerical_library_warnings),
        "manifest": {
            "path": lineage.manifest_path.relative_to(repository).as_posix(),
            "sha256": sha256_file(lineage.manifest_path),
        },
        "configuration": {
            "path": lineage.config_path.relative_to(repository).as_posix(),
            "sha256": sha256_file(lineage.config_path),
        },
        "confirmed_blank": {
            "path": _portable(CONFIRMED_BLANK_RELATIVE),
            "sha256": CONFIRMED_BLANK_SHA256,
            "physical_exports": 1,
            "technical_scan_channels": 5,
        },
        "processed_spectra_zip_members": member_count,
        "provenance_status": "regenerated_partial_provenance",
        "limitations": [
            "The 195 prepared sample spectra remain raw_unverified.",
            "Prepared sample Raman axes differ from corresponding vendor axes by approximately 0.39937 cm-1.",
            "The confirmed blank provides technical scans from one export, not independent blank substrates.",
            "Per-record FFT cutoff indices are locked to the canonical run because the recovered percentile rule has hardware-sensitive midpoint ties.",
        ],
    }
    if lineage.name == CONTROLLED_NAME:
        metadata["historical_replay_validation"] = dict(historical_replay)
    (directory / "package_metadata.json").write_bytes(_json_bytes(metadata))
    (directory / "README.md").write_text(
        _package_readme(lineage.name), encoding="utf-8", newline="\n"
    )


def _build_staged_release(
    repository: Path,
    staging_root: Path,
    runs: Mapping[str, LineageRun],
    historical_replay: Mapping[str, object],
) -> dict[str, object]:
    records = _load_sample_records(repository, runs)
    scan_rows = _scan_metrics(records)
    concentration_rows = _concentration_metrics(records)
    peak_rows = _peak_metrics(records)
    blank_rows, axis_summary = _blank_reference_metrics(repository, records)
    summary = _comparison_summary(
        scan_rows, concentration_rows, peak_rows, blank_rows, axis_summary
    )
    summary["historical_replay_validation"] = dict(historical_replay)
    release_root = staging_root / RELEASE_ROOT_RELATIVE
    _write_lineage_package(
        release_root / CONTROLLED_NAME,
        runs[CONTROLLED_NAME],
        historical_replay,
    )
    _write_lineage_package(
        release_root / REFERENCE_NAME,
        runs[REFERENCE_NAME],
        historical_replay,
    )
    _write_comparison_package(
        release_root / COMPARISON_NAME,
        scan_rows,
        concentration_rows,
        peak_rows,
        blank_rows,
        summary,
    )
    return summary


def _publish_staged_release(staged_root: Path, destination_root: Path) -> None:
    staged_packages = staged_root / RELEASE_ROOT_RELATIVE
    allowed = {CONTROLLED_NAME, REFERENCE_NAME, COMPARISON_NAME}
    if destination_root.exists():
        if destination_root.is_symlink() or not destination_root.is_dir():
            raise ReanalysisError(
                f"Release destination is not an ordinary directory: {destination_root}"
            )
        unknown = {path.name for path in destination_root.iterdir()} - allowed
        if unknown:
            raise ReanalysisError(
                "Refusing to overwrite a release root containing unknown entries: "
                + ", ".join(sorted(unknown))
            )
    destination_root.mkdir(parents=True, exist_ok=True)
    for package in sorted(allowed):
        source = staged_packages / package
        destination = destination_root / package
        if destination.exists():
            expected_files = {
                path.relative_to(source).as_posix()
                for path in source.rglob("*")
                if path.is_file()
            }
            existing_files = {
                path.relative_to(destination).as_posix()
                for path in destination.rglob("*")
                if path.is_file()
            }
            stale = existing_files - expected_files
            if stale:
                raise ReanalysisError(
                    f"Refusing to delete stale files from {destination}: "
                    + ", ".join(sorted(stale))
                )
        shutil.copytree(source, destination, dirs_exist_ok=True)


def _compare_values(
    expected: object,
    actual: object,
    *,
    path: str,
    errors: list[str],
    rtol: float = 1e-7,
    atol: float = 1e-6,
) -> None:
    if path.endswith("package_metadata.json.software_environment.python"):
        # The committed release records its generation patch (3.12.13), while
        # GitHub's latest official Windows binary for this series is 3.12.10.
        # Both are explicitly allowed for checking; all numerical products,
        # dependency versions, platform fields, and other metadata still compare.
        return
    if isinstance(expected, dict) and isinstance(actual, dict):
        if set(expected) != set(actual):
            errors.append(f"{path}: JSON object keys differ")
            return
        for key in sorted(expected):
            _compare_values(
                expected[key], actual[key], path=f"{path}.{key}", errors=errors, rtol=rtol, atol=atol
            )
        return
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            errors.append(f"{path}: JSON list lengths differ")
            return
        for index, (left, right) in enumerate(zip(expected, actual)):
            _compare_values(
                left, right, path=f"{path}[{index}]", errors=errors, rtol=rtol, atol=atol
            )
        return
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if isinstance(expected, bool) or isinstance(actual, bool):
            if expected != actual:
                errors.append(f"{path}: values differ")
            return
        if not np.isclose(float(expected), float(actual), rtol=rtol, atol=atol, equal_nan=True):
            errors.append(f"{path}: numeric values differ ({expected!r} != {actual!r})")
        return
    if expected != actual:
        errors.append(f"{path}: values differ ({expected!r} != {actual!r})")


def _compare_frames(expected: pd.DataFrame, actual: pd.DataFrame, label: str) -> list[str]:
    errors: list[str] = []
    if list(expected.columns) != list(actual.columns):
        return [f"{label}: columns differ"]
    if expected.shape != actual.shape:
        return [f"{label}: shapes differ ({expected.shape} != {actual.shape})"]
    for column in expected.columns:
        left = expected[column]
        right = actual[column]
        left_numeric = pd.to_numeric(left, errors="coerce")
        right_numeric = pd.to_numeric(right, errors="coerce")
        left_nonempty = left.astype("string").fillna("").str.len() > 0
        right_nonempty = right.astype("string").fillna("").str.len() > 0
        numeric_mask = left_numeric.notna() | right_numeric.notna()
        if numeric_mask.any() and (numeric_mask == (left_nonempty | right_nonempty)).all():
            if not np.allclose(
                left_numeric.to_numpy(dtype=float),
                right_numeric.to_numpy(dtype=float),
                rtol=1e-7,
                atol=1e-6,
                equal_nan=True,
            ):
                errors.append(f"{label}: numeric column {column!r} differs")
        else:
            left_text = left.astype("string").fillna("").tolist()
            right_text = right.astype("string").fillna("").tolist()
            if left_text != right_text:
                errors.append(f"{label}: text column {column!r} differs")
    return errors


def _read_csv_from_bytes(data: bytes, *, compressed: bool = False) -> pd.DataFrame:
    if compressed:
        data = gzip.decompress(data)
    return pd.read_csv(io.BytesIO(data), encoding="utf-8", dtype=object, keep_default_na=False)


def _compare_release_directories(expected: Path, actual: Path) -> list[str]:
    errors: list[str] = []
    if not actual.is_dir():
        return [f"Missing release directory: {actual}"]
    expected_files = {
        path.relative_to(expected).as_posix(): path
        for path in expected.rglob("*")
        if path.is_file()
    }
    actual_files = {
        path.relative_to(actual).as_posix(): path
        for path in actual.rglob("*")
        if path.is_file()
    }
    if set(expected_files) != set(actual_files):
        missing = sorted(set(expected_files) - set(actual_files))
        extra = sorted(set(actual_files) - set(expected_files))
        if missing:
            errors.append("Release files missing: " + ", ".join(missing))
        if extra:
            errors.append("Unexpected release files: " + ", ".join(extra))
        return errors
    for relative in sorted(expected_files):
        expected_path = expected_files[relative]
        actual_path = actual_files[relative]
        suffix = expected_path.suffix.casefold()
        if relative.endswith(".csv.gz"):
            errors.extend(
                _compare_frames(
                    _read_csv_from_bytes(expected_path.read_bytes(), compressed=True),
                    _read_csv_from_bytes(actual_path.read_bytes(), compressed=True),
                    relative,
                )
            )
        elif suffix == ".csv":
            errors.extend(
                _compare_frames(
                    _read_csv_from_bytes(expected_path.read_bytes()),
                    _read_csv_from_bytes(actual_path.read_bytes()),
                    relative,
                )
            )
        elif suffix == ".json":
            try:
                expected_json = json.loads(expected_path.read_text(encoding="utf-8"))
                actual_json = json.loads(actual_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"{relative}: invalid JSON: {exc}")
            else:
                _compare_values(expected_json, actual_json, path=relative, errors=errors)
        elif suffix == ".zip":
            with zipfile.ZipFile(expected_path) as expected_zip, zipfile.ZipFile(actual_path) as actual_zip:
                expected_names = sorted(expected_zip.namelist())
                actual_names = sorted(actual_zip.namelist())
                if expected_names != actual_names:
                    errors.append(f"{relative}: ZIP member lists differ")
                    continue
                for member in expected_names:
                    errors.extend(
                        _compare_frames(
                            _read_csv_from_bytes(expected_zip.read(member)),
                            _read_csv_from_bytes(actual_zip.read(member)),
                            f"{relative}:{member}",
                        )
                    )
        elif expected_path.read_bytes() != actual_path.read_bytes():
            errors.append(f"{relative}: bytes differ")
        if len(errors) >= 50:
            return errors
    return errors


def _refresh_release_metadata(repository: Path) -> dict[str, object]:
    from scripts.prepare_repository_data import (
        refresh_confirmed_4atp_reanalysis_metadata,
    )

    return refresh_confirmed_4atp_reanalysis_metadata(repository)


def _temporary_parent(repository: Path) -> Path:
    """Keep scratch outputs on the repository volume for portable provenance."""
    parent = repository / ".workbench"
    if parent.exists() and (parent.is_symlink() or not parent.is_dir()):
        raise ReanalysisError(
            f"Temporary work root is not an ordinary directory: {parent}"
        )
    parent.mkdir(parents=True, exist_ok=True)
    return parent


def generate_release(repository: Path) -> dict[str, object]:
    _validate_canonical_release_environment(repository)
    write_configuration_files(repository)
    with tempfile.TemporaryDirectory(
        prefix="auagbc-750h-reanalysis-", dir=_temporary_parent(repository)
    ) as temporary:
        temporary_root = Path(temporary)
        historical_replay = _validate_historical_replay(
            repository, temporary_root / "historical_replay"
        )
        runs = _run_profiles(repository, temporary_root / "runs")
        summary = _build_staged_release(
            repository,
            temporary_root / "staged",
            runs,
            historical_replay,
        )
        _publish_staged_release(
            temporary_root / "staged", repository / RELEASE_ROOT_RELATIVE
        )
    metadata_report = _refresh_release_metadata(repository)
    return {"comparison_summary": summary, "release_metadata": metadata_report}


def check_release(repository: Path) -> list[str]:
    _validate_canonical_release_environment(repository, allow_check_patch=True)
    errors = check_configuration_files(repository)
    if errors:
        return errors
    with tempfile.TemporaryDirectory(
        prefix="auagbc-750h-check-", dir=_temporary_parent(repository)
    ) as temporary:
        temporary_root = Path(temporary)
        historical_replay = _validate_historical_replay(
            repository, temporary_root / "historical_replay"
        )
        runs = _run_profiles(repository, temporary_root / "runs")
        _build_staged_release(
            repository,
            temporary_root / "staged",
            runs,
            historical_replay,
        )
        errors.extend(
            _compare_release_directories(
                temporary_root / "staged" / RELEASE_ROOT_RELATIVE,
                repository / RELEASE_ROOT_RELATIVE,
            )
        )
    if errors:
        return errors
    manifest_rows = _read_csv_rows(repository / "metadata" / "dataset_manifest.csv")[1]
    by_path = {row["repository_path"]: row for row in manifest_rows}
    for path in sorted((repository / RELEASE_ROOT_RELATIVE).rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(repository).as_posix()
        row = by_path.get(relative)
        if row is None:
            errors.append(f"Release file is not in dataset_manifest.csv: {relative}")
            continue
        if row.get("repository_sha256") != sha256_file(path):
            errors.append(f"Dataset-manifest SHA-256 is stale: {relative}")
    return errors


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=REPOSITORY_ROOT,
        help="Repository root; defaults to the parent of this script directory.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Freshly rerun both profiles and fail if committed configs or compact products differ.",
    )
    parser.add_argument(
        "--manifests-only",
        action="store_true",
        help="Write and validate only the two manifests and JSON job configurations.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    repository = args.repository_root.expanduser().resolve()
    if args.check and args.manifests_only:
        print("ERROR: --check and --manifests-only cannot be combined.", file=sys.stderr)
        return 2
    try:
        if args.check:
            errors = check_release(repository)
            if errors:
                for error in errors[:50]:
                    print(f"ERROR: {error}", file=sys.stderr)
                if len(errors) > 50:
                    print(f"ERROR: {len(errors) - 50} additional errors omitted.", file=sys.stderr)
                return 1
            print("PASS: confirmed-blank 750_5_5_H reanalysis is current and reproducible.")
            return 0
        if args.manifests_only:
            written = write_configuration_files(repository)
            for path in sorted(written):
                print(f"Wrote {path.relative_to(repository).as_posix()}")
            return 0
        report = generate_release(repository)
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, ReanalysisError, RamanPipelineError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
