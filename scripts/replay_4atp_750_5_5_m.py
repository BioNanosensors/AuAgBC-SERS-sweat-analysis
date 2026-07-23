#!/usr/bin/env python3
"""Reproduce the legacy 4-ATP 750_5_5_M computational lineage.

This program intentionally reproduces the historical arithmetic, including the
use of an assembled high-power blank whose scientific context conflicts with a
medium-power interpretation. Passing verification establishes computational
lineage only; it does not validate that blank or the experimental labels.

Default mode generates the deterministic five-file audit package. ``--check``
requires a byte-exact rebuild in the generation environment.
``--cross-environment-check`` independently verifies the committed hashes and
structure while requiring a fresh numerical replay to pass every mapped-channel
acceptance bound in the declared compatible environment.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import io
import json
import math
import os
import platform
import shutil
import sys
import uuid
import zipfile
import zlib
from collections import Counter, defaultdict
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Iterable, Iterator, Mapping, Sequence

import numpy as np
import pandas as pd
import pybaselines
import scipy
from pybaselines.whittaker import iarpls
from scipy.fft import fft, fftfreq
from scipy.signal import butter, filtfilt, find_peaks


CONFIG_PATH = PurePosixPath(
    "configs/reanalysis/optimisation_750_5_5_m_historical_replay.json"
)
RELEASE_REQUIREMENTS_PATH = PurePosixPath("requirements-release.txt")
EXPECTED_PACKAGE_FILES = (
    "README.md",
    "package_metadata.json",
    "resolved_manifest.csv",
    "replay_metrics.csv",
    "replayed_spectra.zip",
)
DATASET_MANIFEST_REQUIRED_COLUMNS = {
    "repository_path",
    "repository_sha256",
    "repository_bytes",
    "status",
    "role",
}

INVENTORY_COLUMNS = (
    "source_id",
    "source_path",
    "source_filename",
    "source_sha256",
    "source_bytes",
    "lineage_role",
    "substrate",
    "embedded_name",
    "embedded_date",
    "embedded_tag",
    "integration_ms",
    "averaging",
    "measure_data_count",
    "full_instrument_rows",
    "replay_rows",
    "intensity_channels",
    "instrument",
    "acquisition_code",
    "source_provenance_status",
    "scientific_blank_status",
    "historical_reference_path",
    "historical_reference_sha256",
    "release_classification",
    "note",
)

MANIFEST_COLUMNS = (
    "record_id",
    "source_id",
    "source_file",
    "source_path",
    "source_sha256",
    "source_intensity_column",
    "source_intensity_column_index",
    "historical_reference_file",
    "historical_reference_path",
    "historical_reference_sha256",
    "historical_intensity_column",
    "output_zip_member",
    "output_intensity_column",
    "sample_type",
    "substrate",
    "analyte",
    "concentration_molar",
    "concentration_label",
    "replicate",
    "accumulation",
    "instrument",
    "acquisition",
    "measurement_date",
    "baseline_lambda",
    "blank_reference_record_id",
    "source_provenance_status",
    "historical_reference_status",
    "blank_context_match",
    "release_classification",
)

LOCK_COLUMNS = (
    "lineage",
    "record_id",
    "source_file",
    "source_path",
    "source_sha256",
    "source_intensity_column",
    "source_intensity_column_index",
    "sample_type",
    "substrate",
    "spectrum_points",
    "baseline_lambda",
    "percentile",
    "butterworth_order",
    "positive_frequency_max_index",
    "filter_fft_peak_index",
    "normalized_cutoff",
    "tie_candidate_count",
    "tie_candidate_fft_peak_indices",
    "numpy_argmin_fft_peak_index",
    "forensic_override",
    "lock_basis",
)

RESOLVED_COLUMNS = MANIFEST_COLUMNS + (
    "source_hash_verified",
    "historical_reference_hash_verified",
    "output_member_sha256",
    "points",
    "axis_array_equal",
    "intensity_within_tolerance",
    "resolution_status",
)

METRIC_COLUMNS = (
    "record_id",
    "historical_reference_file",
    "historical_intensity_column",
    "replayed_zip_member",
    "replayed_intensity_column",
    "points",
    "axis_array_equal",
    "axis_max_abs_cm-1",
    "intensity_array_equal",
    "intensity_rmse",
    "intensity_mae",
    "intensity_max_abs",
    "intensity_rtol",
    "intensity_rmse_max",
    "intensity_max_abs_max",
    "within_tolerance",
    "filter_fft_peak_index",
    "tie_candidate_count",
    "forensic_override",
)


class ReplayError(RuntimeError):
    """Raised when the declared computational-lineage contract is violated."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv_contract(path: Path, expected_columns: Sequence[str]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != tuple(expected_columns):
            raise ReplayError(
                f"Unexpected columns in {path.name}: {reader.fieldnames!r}"
            )
        return list(reader)


def read_csv_bytes_contract(
    content: bytes,
    expected_columns: Sequence[str],
    label: str,
) -> list[dict[str, str]]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ReplayError(f"{label} is not valid UTF-8") from error
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if tuple(reader.fieldnames or ()) != tuple(expected_columns):
        raise ReplayError(f"Unexpected columns in {label}: {reader.fieldnames!r}")
    return list(reader)


def read_json_object(content: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReplayError(f"{label} is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ReplayError(f"{label} must contain a JSON object")
    return value


def csv_bytes(
    fieldnames: Sequence[str], rows: Iterable[Mapping[str, object]]
) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=fieldnames,
        lineterminator="\n",
        extrasaction="raise",
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def require_relative_posix(value: str, label: str) -> PurePosixPath:
    if not value or "\\" in value:
        raise ReplayError(f"{label} must be a nonempty POSIX relative path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or any(":" in part for part in path.parts):
        raise ReplayError(f"{label} escapes the repository: {value!r}")
    if any(part in ("", ".") for part in path.parts):
        raise ReplayError(f"{label} is not normalized: {value!r}")
    return path


def repository_file(root: Path, value: str, label: str) -> Path:
    relative = require_relative_posix(value, label)
    candidate = (root / Path(*relative.parts)).resolve()
    root_resolved = root.resolve()
    if not candidate.is_relative_to(root_resolved):
        raise ReplayError(f"{label} resolves outside the repository: {value!r}")
    return candidate


def parse_bool(value: str, label: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise ReplayError(f"{label} must be true or false, got {value!r}")


def validate_declared_semantics(config: Mapping[str, object]) -> None:
    """Pin descriptive fields to the arithmetic this program actually runs."""
    required_top_level = {
        "schema_version",
        "lineage",
        "claim_scope",
        "release_classification",
        "scientific_blank_status",
        "paths",
        "expected_composition",
        "vendor_csv_reader",
        "blank_operation",
        "processing",
        "acceptance",
        "deterministic_package",
        "verification_modes",
        "validated_environment",
        "interpretation_limit",
    }
    if set(config) != required_top_level:
        raise ReplayError("Replay-config top-level fields changed")

    expected_sections: dict[str, object] = {
        "paths": {
            "source_inventory": (
                "configs/reanalysis/"
                "optimisation_750_5_5_m_historical_replay_sources.csv"
            ),
            "channel_manifest": (
                "configs/reanalysis/"
                "optimisation_750_5_5_m_historical_replay_manifest.csv"
            ),
            "fft_locks": (
                "metadata/processing_locks/"
                "optimisation_750_5_5_m_historical_replay_fft_cutoffs.csv"
            ),
            "output_directory": (
                "data/processed/4atp/optimisation/750_5_5_M/"
                "historical_computational_replay"
            ),
        },
        "expected_composition": {
            "source_files": 43,
            "AAB_sample_exports": 39,
            "BC_sample_exports": 3,
            "assembled_blank_exports": 1,
            "channels": 225,
            "AAB_sample_channels": 195,
            "BC_sample_channels": 15,
            "assembled_blank_channels": 15,
            "processed_files": 43,
            "points_per_channel": 432,
        },
        "vendor_csv_reader": {
            "header_row_index": 99,
            "note": (
                "Recovered historical parser quirk: pandas header index 99 "
                "treats physical line 100, the 80th spectral row, as the header "
                "and retains data lines 101-532, the final 432 of 512 spectral "
                "points. Intensity channels are then addressed by position."
            ),
        },
        "blank_operation": {
            "source_record_id": "M750-CH-211",
            "source_channel_index": 1,
            "operation": "rowwise_subtraction_by_position",
            "axis_alignment": "none",
            "interpolation": "none",
            "status": "provenance_conflict",
            "warning": (
                "The assembled blank is embedded-labelled AAB_Blank_750_5_5_H "
                "and is not a confirmed 750_5_5_M blank. This replay preserves "
                "historical arithmetic only."
            ),
        },
        "processing": {
            "first_iarpls": {
                "lambda_by_role": {
                    "AAB_sample": 3000.0,
                    "BC_sample": 1000.0,
                    "assembled_blank": 700.0,
                },
                "diff_order": 2,
                "max_iter": 50,
                "tolerance": 0.001,
            },
            "fft_filter": {
                "percentile_by_role": {
                    "AAB_sample": 10.0,
                    "BC_sample": 10.0,
                    "assembled_blank": 5.0,
                },
                "peak_rule": "closest_magnitude_to_percentile",
                "tie_atol_epsilon_multiplier": 32,
                "expected_tie_channels": 13,
                "expected_forensic_overrides": 5,
                "butterworth_order": 3,
                "filter": "scipy.signal.filtfilt",
                "locks": (
                    "Source-hash-bound forensic FFT bins; locks reproduce "
                    "preserved history and are not recommended scientific "
                    "parameters."
                ),
            },
            "second_iarpls": {
                "lambda": 80.0,
                "diff_order": 2,
                "max_iter": 50,
                "tolerance": 0.001,
            },
            "savgol": "not_applied",
        },
        "acceptance": {
            "axis_array_equal": True,
            "axis_max_abs_cm-1": 0.0,
            "intensity_rtol": 0.0,
            "intensity_rmse_max": 1e-7,
            "intensity_max_abs_max": 1e-6,
        },
        "deterministic_package": {
            "files": list(EXPECTED_PACKAGE_FILES),
            "zip_member_prefix": "spectra/",
            "zip_timestamp": [1980, 1, 1, 0, 0, 0],
            "zip_permissions_octal": "100644",
            "zip_compression": "deflate",
            "zip_compresslevel": 9,
            "csv_float_format": ".17g",
            "text_encoding": "utf-8",
            "line_ending": "LF",
        },
        "verification_modes": {
            "exact_package_check": {
                "cli": "--check",
                "runtime": "generation_python",
                "regenerated_package_bytes_must_match": True,
            },
            "cross_environment_check": {
                "cli": "--cross-environment-check",
                "regenerated_package_bytes_must_match": False,
                "fresh_numerical_target": "mapped_historical_references",
                "runtime_package_byte_identity_claimed": False,
                "committed_package_hashes_must_match": True,
                "resolved_mapping_fields_must_match": True,
                "raman_axes_must_match": True,
                "numerical_acceptance_must_pass": True,
            },
        },
    }
    for section, expected in expected_sections.items():
        if config.get(section) != expected:
            raise ReplayError(
                f"Replay-config {section!r} no longer describes the "
                "implemented historical computation"
            )

    interpretation_limit = (
        "The replay proves how the stored numbers were computed. It does not "
        "prove that the inputs, labels, replicates, or mixed high-power blank "
        "were scientifically valid for the medium-power experiment."
    )
    if config.get("interpretation_limit") != interpretation_limit:
        raise ReplayError("The interpretation limit cannot be weakened")


def format_float(value: float, specification: str = ".17g") -> str:
    if not math.isfinite(value):
        raise ReplayError(f"Non-finite number cannot be serialized: {value!r}")
    return format(float(value), specification)


def release_requirement_pins(root: Path) -> dict[str, str]:
    requirements = repository_file(
        root,
        RELEASE_REQUIREMENTS_PATH.as_posix(),
        "release requirements path",
    )
    pins: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        requirements.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.count("==") != 1:
            raise ReplayError(
                f"{requirements.name} line {line_number} must use name==version"
            )
        name, version = (part.strip() for part in line.split("==", 1))
        if not name or not version or name in pins:
            raise ReplayError(
                f"Invalid or duplicate release pin on line {line_number}"
            )
        pins[name] = version
    if not pins:
        raise ReplayError("Release requirements contain no exact pins")
    return pins


def verify_runtime(
    root: Path,
    config: Mapping[str, object],
    *,
    allow_cross_environment_python: bool,
) -> dict[str, object]:
    expected = config["validated_environment"]
    if set(expected) != {
        "generation_python",
        "cross_environment_check_python",
        "system",
        "machine",
        "zlib_compile",
        "zlib_runtime",
        "packages",
    }:
        raise ReplayError("Validated-environment fields changed")
    expected_packages = expected["packages"]
    pins = release_requirement_pins(root)
    if pins != expected_packages:
        raise ReplayError(
            "Validated package versions do not match requirements-release.txt"
        )

    python_version = platform.python_version()
    allowed_python = (
        tuple(expected["cross_environment_check_python"])
        if allow_cross_environment_python
        else (expected["generation_python"],)
    )
    actual_packages = {
        name: importlib.metadata.version(name) for name in expected_packages
    }
    actual = {
        "python": python_version,
        "system": platform.system(),
        "machine": platform.machine(),
        "zlib_compile": zlib.ZLIB_VERSION,
        "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION,
        "packages": actual_packages,
    }
    mismatches: list[str] = []
    if python_version not in allowed_python:
        mismatches.append(
            f"Python {python_version} (expected {' or '.join(allowed_python)})"
        )
    for key in ("system", "machine", "zlib_compile", "zlib_runtime"):
        if str(actual[key]).casefold() != str(expected[key]).casefold():
            mismatches.append(
                f"{key} {actual[key]} (expected {expected[key]})"
            )
    for distribution, expected_version in expected_packages.items():
        actual_version = actual_packages[distribution]
        if actual_version != expected_version:
            mismatches.append(
                f"{distribution} {actual_version} "
                f"(expected {expected_version})"
            )
    if mismatches:
        raise ReplayError(
            "The selected replay verification mode requires its declared "
            "release environment: "
            + "; ".join(mismatches)
            + '. Install it with: python -m pip install -e ".[test]" '
            "-c requirements-release.txt"
        )
    return actual


def load_contract(
    root: Path,
    *,
    allow_cross_environment_python: bool,
) -> tuple[
    dict[str, object],
    bytes,
    list[dict[str, str]],
    bytes,
    list[dict[str, str]],
    bytes,
    list[dict[str, str]],
    bytes,
    dict[str, object],
]:
    config_file = repository_file(root, CONFIG_PATH.as_posix(), "config path")
    config_raw = config_file.read_bytes()
    config = json.loads(config_raw.decode("utf-8"))
    if config.get("schema_version") != "1.1":
        raise ReplayError("Unsupported replay-config schema")
    if (
        config.get("lineage")
        != "optimisation_750_5_5_M_historical_computational_replay"
    ):
        raise ReplayError("The recovered lineage identifier changed")
    if config.get("claim_scope") != "computational_lineage_only":
        raise ReplayError("The replay claim scope must remain computational_lineage_only")
    if config.get("release_classification") != "audit_evidence_only":
        raise ReplayError("The replay classification must remain audit_evidence_only")
    if config.get("scientific_blank_status") != "no_confirmed_medium_power_blank":
        raise ReplayError("The blank conflict cannot be upgraded")
    validate_declared_semantics(config)
    runtime = verify_runtime(
        root,
        config,
        allow_cross_environment_python=allow_cross_environment_python,
    )

    paths = config["paths"]
    inventory_file = repository_file(
        root, paths["source_inventory"], "source inventory path"
    )
    manifest_file = repository_file(
        root, paths["channel_manifest"], "channel manifest path"
    )
    lock_file = repository_file(root, paths["fft_locks"], "FFT lock path")

    inventory_raw = inventory_file.read_bytes()
    manifest_raw = manifest_file.read_bytes()
    locks_raw = lock_file.read_bytes()
    inventory = read_csv_contract(inventory_file, INVENTORY_COLUMNS)
    manifest = read_csv_contract(manifest_file, MANIFEST_COLUMNS)
    locks = read_csv_contract(lock_file, LOCK_COLUMNS)
    return (
        config,
        config_raw,
        inventory,
        inventory_raw,
        manifest,
        manifest_raw,
        locks,
        locks_raw,
        runtime,
    )


def ensure_unique(rows: Sequence[Mapping[str, str]], key: str, label: str) -> None:
    values = [row[key] for row in rows]
    duplicates = sorted(value for value, count in Counter(values).items() if count > 1)
    if duplicates:
        raise ReplayError(f"Duplicate {label}: {duplicates[:5]!r}")


def validate_contract(
    root: Path,
    config: Mapping[str, object],
    inventory: list[dict[str, str]],
    manifest: list[dict[str, str]],
    locks: list[dict[str, str]],
) -> tuple[
    dict[str, dict[str, str]],
    dict[str, dict[str, str]],
    dict[str, dict[str, str]],
]:
    expected = config["expected_composition"]
    if len(inventory) != int(expected["source_files"]):
        raise ReplayError("Source-inventory count is not 43")
    if len(manifest) != int(expected["channels"]):
        raise ReplayError("Channel-manifest count is not 225")
    if len(locks) != int(expected["channels"]):
        raise ReplayError("FFT-lock count is not 225")

    ensure_unique(inventory, "source_id", "source IDs")
    ensure_unique(inventory, "source_path", "source paths")
    ensure_unique(inventory, "source_sha256", "source hashes")
    ensure_unique(manifest, "record_id", "record IDs")
    ensure_unique(locks, "record_id", "FFT-lock record IDs")

    inventory_by_id = {row["source_id"]: row for row in inventory}
    manifest_by_id = {row["record_id"]: row for row in manifest}
    locks_by_id = {row["record_id"]: row for row in locks}
    if set(manifest_by_id) != set(locks_by_id):
        raise ReplayError("FFT locks do not cover the channel manifest exactly")

    role_counts = Counter(row["lineage_role"] for row in inventory)
    required_role_counts = {
        "AAB_sample": int(expected["AAB_sample_exports"]),
        "BC_sample": int(expected["BC_sample_exports"]),
        "assembled_blank": int(expected["assembled_blank_exports"]),
    }
    if role_counts != Counter(required_role_counts):
        raise ReplayError(
            f"Unexpected source composition: {dict(role_counts)!r}"
        )

    channel_role_counts: Counter[str] = Counter()
    records_by_source: dict[str, list[dict[str, str]]] = defaultdict(list)
    for record in manifest:
        source = inventory_by_id.get(record["source_id"])
        if source is None:
            raise ReplayError(f"Unknown source ID in {record['record_id']}")
        for key_source, key_record in (
            ("source_path", "source_path"),
            ("source_filename", "source_file"),
            ("source_sha256", "source_sha256"),
        ):
            if source[key_source] != record[key_record]:
                raise ReplayError(
                    f"Source mapping mismatch for {record['record_id']}: "
                    f"{key_source}"
                )
        if record["historical_reference_path"] != source[
            "historical_reference_path"
        ]:
            raise ReplayError(
                f"Reference path mismatch for {record['record_id']}"
            )
        if record["historical_reference_sha256"] != source[
            "historical_reference_sha256"
        ]:
            raise ReplayError(
                f"Reference hash mismatch for {record['record_id']}"
            )
        if record["release_classification"] != "audit_evidence_only":
            raise ReplayError("A record was promoted beyond audit_evidence_only")
        if record["historical_reference_status"] != "provenance_conflict":
            raise ReplayError("Historical references must remain provenance_conflict")
        channel_index = int(record["source_intensity_column_index"])
        if record["source_intensity_column"] != f"intensity_{channel_index}":
            raise ReplayError(
                f"Logical source-column mismatch for {record['record_id']}"
            )
        reference_relative = require_relative_posix(
            record["historical_reference_path"], "historical reference path"
        )
        if record["historical_reference_file"] != reference_relative.name:
            raise ReplayError(
                f"Historical reference filename mismatch for {record['record_id']}"
            )
        if record["output_zip_member"] != (
            f"spectra/{record['historical_reference_file']}"
        ):
            raise ReplayError(f"Unexpected output member for {record['record_id']}")
        if record["output_intensity_column"] != record[
            "historical_intensity_column"
        ]:
            raise ReplayError(f"Output-column mismatch for {record['record_id']}")
        role = source["lineage_role"]
        expected_record_metadata = {
            "AAB_sample": (
                "AAB_4ATP_sample",
                "AAB",
                "4-ATP",
                "raw_unverified",
                "false",
                "750 ms; 5 averages; 5 measurements; M power code",
            ),
            "BC_sample": (
                "BC_4ATP_sample",
                "BC",
                "4-ATP",
                "raw_unverified",
                "false",
                "750 ms; 5 averages; 5 measurements; M power code",
            ),
            "assembled_blank": (
                "historical_blank_composite",
                "AAB",
                "blank",
                "provenance_conflict",
                "not_applicable",
                "750 ms; 5 averages; 5 measurements; embedded H power code",
            ),
        }[role]
        observed_record_metadata = (
            record["sample_type"],
            record["substrate"],
            record["analyte"],
            record["source_provenance_status"],
            record["blank_context_match"],
            record["acquisition"],
        )
        if observed_record_metadata != expected_record_metadata:
            raise ReplayError(
                f"Scientific-status metadata changed for {record['record_id']}"
            )
        channel_role_counts[source["lineage_role"]] += 1
        records_by_source[source["source_id"]].append(record)

    required_channel_counts = {
        "AAB_sample": int(expected["AAB_sample_channels"]),
        "BC_sample": int(expected["BC_sample_channels"]),
        "assembled_blank": int(expected["assembled_blank_channels"]),
    }
    if channel_role_counts != Counter(required_channel_counts):
        raise ReplayError(
            f"Unexpected channel composition: {dict(channel_role_counts)!r}"
        )

    blank_sources = [
        row for row in inventory if row["lineage_role"] == "assembled_blank"
    ]
    if len(blank_sources) != 1:
        raise ReplayError("Exactly one assembled blank source is required")
    blank_source = blank_sources[0]
    if blank_source["source_provenance_status"] != "provenance_conflict":
        raise ReplayError("The assembled blank must remain provenance_conflict")
    blank_record_id = config["blank_operation"]["source_record_id"]
    blank_record = manifest_by_id.get(blank_record_id)
    if (
        blank_record is None
        or blank_record["source_id"] != blank_source["source_id"]
        or int(blank_record["source_intensity_column_index"]) != 1
    ):
        raise ReplayError("The unique subtraction blank must be blank channel 1")

    for source in inventory:
        if source["release_classification"] != "audit_evidence_only":
            raise ReplayError("A source was promoted beyond audit_evidence_only")
        expected_acquisition_code = (
            "750_5_5_H"
            if source["lineage_role"] == "assembled_blank"
            else "750_5_5_M"
        )
        if (
            source["integration_ms"],
            source["averaging"],
            source["measure_data_count"],
            source["full_instrument_rows"],
            source["replay_rows"],
            source["instrument"],
            source["acquisition_code"],
        ) != (
            "750",
            "5",
            "5",
            "512",
            "432",
            "portable_raman",
            expected_acquisition_code,
        ):
            raise ReplayError(
                f"Source acquisition metadata changed: {source['source_id']}"
            )
        if source["lineage_role"] == "assembled_blank":
            if (
                source["source_provenance_status"] != "provenance_conflict"
                or source["scientific_blank_status"]
                != "not_a_confirmed_medium_power_blank"
                or "750_5_5_H" not in source["embedded_name"]
            ):
                raise ReplayError("The assembled-blank conflict metadata changed")
        elif (
            source["source_provenance_status"] != "raw_unverified"
            or source["scientific_blank_status"] != "not_applicable"
        ):
            raise ReplayError(
                f"Unexpected sample provenance status: {source['source_id']}"
            )
        source_records = records_by_source[source["source_id"]]
        expected_channels = int(source["intensity_channels"])
        channel_indices = sorted(
            int(record["source_intensity_column_index"])
            for record in source_records
        )
        if channel_indices != list(range(1, expected_channels + 1)):
            raise ReplayError(
                f"Incomplete channel mapping for {source['source_filename']}"
            )
        for record in source_records:
            if source["lineage_role"] == "assembled_blank":
                if record["blank_reference_record_id"]:
                    raise ReplayError("Blank channels cannot subtract themselves")
            elif record["blank_reference_record_id"] != blank_record_id:
                raise ReplayError(
                    f"Wrong blank mapping for {record['record_id']}"
                )

    source_files_declared = set()
    reference_files_declared = set()
    for source in inventory:
        source_path = repository_file(
            root, source["source_path"], "declared source path"
        )
        if not source_path.is_file():
            raise ReplayError(f"Missing source: {source['source_path']}")
        if source_path.name != source["source_filename"]:
            raise ReplayError(f"Source filename mismatch: {source['source_id']}")
        if source_path.stat().st_size != int(source["source_bytes"]):
            raise ReplayError(f"Source byte count mismatch: {source['source_id']}")
        if sha256_file(source_path) != source["source_sha256"]:
            raise ReplayError(f"Source hash mismatch: {source['source_id']}")
        source_files_declared.add(source_path.resolve())

        reference_path = repository_file(
            root,
            source["historical_reference_path"],
            "historical reference path",
        )
        if not reference_path.is_file():
            raise ReplayError(
                f"Missing historical reference: {source['historical_reference_path']}"
            )
        if sha256_file(reference_path) != source["historical_reference_sha256"]:
            raise ReplayError(
                f"Historical reference hash mismatch: {source['source_id']}"
            )
        reference_files_declared.add(reference_path.resolve())

    public_source_root = repository_file(
        root,
        "data/quarantine/computational_lineage_sources/4atp/"
        "optimisation/750_5_5_M",
        "computational-lineage source root",
    )
    actual_sources = {
        path.resolve() for path in public_source_root.rglob("*.csv") if path.is_file()
    }
    if actual_sources != source_files_declared:
        raise ReplayError("Source directory contains missing or unexpected CSV files")

    if len(reference_files_declared) != int(expected["processed_files"]):
        raise ReplayError("Historical reference set is not exactly 43 files")
    reference_parents = {path.parent for path in reference_files_declared}
    if len(reference_parents) != 1:
        raise ReplayError("Historical references do not share one declared directory")
    actual_references = {
        path.resolve()
        for path in next(iter(reference_parents)).glob("*.csv")
        if path.is_file()
    }
    if actual_references != reference_files_declared:
        raise ReplayError(
            "Historical reference directory contains missing or unexpected CSV files"
        )

    fft_config = config["processing"]["fft_filter"]
    tie_count = sum(int(row["tie_candidate_count"]) > 1 for row in locks)
    override_count = sum(parse_bool(row["forensic_override"], "forensic_override") for row in locks)
    if tie_count != int(fft_config["expected_tie_channels"]):
        raise ReplayError("Declared FFT tie count is not 13")
    if override_count != int(fft_config["expected_forensic_overrides"]):
        raise ReplayError("Declared forensic-override count is not 5")

    for record_id, lock in locks_by_id.items():
        record = manifest_by_id[record_id]
        source = inventory_by_id[record["source_id"]]
        for key in (
            "source_file",
            "source_path",
            "source_sha256",
            "source_intensity_column",
            "source_intensity_column_index",
            "sample_type",
            "substrate",
            "baseline_lambda",
        ):
            if lock[key] != record[key]:
                raise ReplayError(f"FFT lock mismatch for {record_id}: {key}")
        expected_percentile = float(
            fft_config["percentile_by_role"][source["lineage_role"]]
        )
        if float(lock["percentile"]) != expected_percentile:
            raise ReplayError(f"Wrong FFT percentile for {record_id}")
        if int(lock["butterworth_order"]) != int(fft_config["butterworth_order"]):
            raise ReplayError(f"Wrong filter order for {record_id}")
        if int(lock["spectrum_points"]) != int(expected["points_per_channel"]):
            raise ReplayError(f"Wrong lock point count for {record_id}")
        if lock["lineage"] != config["lineage"]:
            raise ReplayError(f"Wrong FFT-lock lineage for {record_id}")
        selected_bin = int(lock["filter_fft_peak_index"])
        positive_max = int(lock["positive_frequency_max_index"])
        candidate_bins = [
            int(value)
            for value in lock["tie_candidate_fft_peak_indices"].split(";")
            if value
        ]
        candidate_count = int(lock["tie_candidate_count"])
        override = parse_bool(lock["forensic_override"], "forensic_override")
        if (
            positive_max != int(expected["points_per_channel"]) // 2 - 1
            or not (0 < selected_bin <= positive_max)
            or candidate_count != len(candidate_bins)
            or selected_bin not in candidate_bins
            or int(lock["numpy_argmin_fft_peak_index"]) not in candidate_bins
            or not (0.0 < float(lock["normalized_cutoff"]) < 1.0)
        ):
            raise ReplayError(f"Invalid FFT-lock values for {record_id}")
        expected_basis = (
            "preserved_output_minimum_rmse_within_ulp_tie"
            if override
            else "recovered_closest_percentile_rule"
        )
        if lock["lock_basis"] != expected_basis:
            raise ReplayError(f"Wrong FFT-lock basis for {record_id}")

    output_members = [record["output_zip_member"] for record in manifest]
    for member in output_members:
        member_path = require_relative_posix(member, "output ZIP member")
        if member_path.parts[0] != "spectra":
            raise ReplayError(f"Unexpected ZIP-member prefix: {member!r}")
    member_counts = Counter(output_members)
    if set(member_counts.values()) != {
        int(source["intensity_channels"]) for source in inventory
    }:
        # AAB/BC members occur five times; the blank member occurs fifteen times.
        if sorted(member_counts.values()) != [5] * 42 + [15]:
            raise ReplayError("ZIP-member/channel composition is not 42x5 + 1x15")
    if len(member_counts) != int(expected["processed_files"]):
        raise ReplayError("Output ZIP does not resolve to 43 spectra files")

    return inventory_by_id, manifest_by_id, locks_by_id


def read_vendor(path: Path, header_row_index: int) -> pd.DataFrame:
    return pd.read_csv(path, header=header_row_index)


def fft_diagnostics(
    y_corrected: np.ndarray,
    percentile: float,
    epsilon_multiplier: int,
) -> dict[str, object]:
    magnitude = np.abs(fft(y_corrected, len(y_corrected))[: len(y_corrected) // 2])
    peaks, _ = find_peaks(magnitude)
    if len(peaks) == 0:
        raise ReplayError("No FFT peaks were detected")
    threshold = float(np.percentile(magnitude[peaks], percentile))
    distances = np.abs(magnitude[peaks] - threshold)
    minimum_distance = float(np.min(distances))
    tie_atol = (
        epsilon_multiplier
        * np.finfo(float).eps
        * max(1.0, abs(threshold), float(np.max(np.abs(magnitude[peaks]))))
    )
    tie_ordinals = np.flatnonzero(
        np.isclose(distances, minimum_distance, rtol=0.0, atol=tie_atol)
    )
    return {
        "peaks": peaks,
        "numpy_argmin_bin": int(peaks[int(np.argmin(distances))]),
        "tie_bins": [int(peaks[int(index)]) for index in tie_ordinals],
    }


def validate_fft_lock_branch(
    *,
    record_id: str,
    computed_ties: Sequence[int],
    runtime_argmin: int,
    declared_ties: Sequence[int],
    declared_argmin: int,
    selected_bin: int,
    declared_tie_count: int,
    forensic_override: bool,
    allow_runtime_argmin_tie_drift: bool,
) -> None:
    """Validate a locked FFT branch without ordering an epsilon-scale tie.

    The exact candidate set must be stable. During cross-patch checking only,
    NumPy's unpinned ``argmin`` winner may differ within that set. Generation
    remains strict, and the selected forensic bin and override meaning remain
    bound to the generation record.
    """
    computed = list(computed_ties)
    declared = list(declared_ties)
    if computed != declared:
        raise ReplayError(f"FFT tie candidates changed for {record_id}")
    if len(declared) != declared_tie_count:
        raise ReplayError(f"FFT tie-count mismatch for {record_id}")
    if declared_argmin not in declared:
        raise ReplayError(f"Declared FFT argmin is not a valid candidate: {record_id}")
    if runtime_argmin not in declared:
        raise ReplayError(
            f"FFT argmin escaped the declared epsilon-scale tie set: {record_id}"
        )
    if runtime_argmin != declared_argmin and not allow_runtime_argmin_tie_drift:
        raise ReplayError(f"FFT argmin changed for {record_id}")
    if selected_bin not in declared:
        raise ReplayError(f"Locked FFT bin is not a valid candidate: {record_id}")
    if forensic_override != (selected_bin != declared_argmin):
        raise ReplayError(f"Forensic override flag mismatch: {record_id}")


def replay_with_lock(
    source_y: np.ndarray,
    wavelength: np.ndarray,
    blank_y: np.ndarray,
    subtract_blank: bool,
    baseline_lambda: float,
    percentile: float,
    lock: Mapping[str, str],
    config: Mapping[str, object],
    allow_runtime_argmin_tie_drift: bool,
) -> np.ndarray:
    first = config["processing"]["first_iarpls"]
    second = config["processing"]["second_iarpls"]
    fft_config = config["processing"]["fft_filter"]

    input_y = source_y - blank_y if subtract_blank else source_y.copy()
    baseline_1, _ = iarpls(
        input_y,
        lam=baseline_lambda,
        diff_order=int(first["diff_order"]),
        max_iter=int(first["max_iter"]),
        tol=float(first["tolerance"]),
    )
    y_corrected = input_y - baseline_1

    diagnostics = fft_diagnostics(
        y_corrected,
        percentile=percentile,
        epsilon_multiplier=int(fft_config["tie_atol_epsilon_multiplier"]),
    )
    selected_bin = int(lock["filter_fft_peak_index"])
    declared_ties = [
        int(value)
        for value in lock["tie_candidate_fft_peak_indices"].split(";")
        if value
    ]
    override = parse_bool(lock["forensic_override"], "forensic_override")
    validate_fft_lock_branch(
        record_id=lock["record_id"],
        computed_ties=diagnostics["tie_bins"],
        runtime_argmin=diagnostics["numpy_argmin_bin"],
        declared_ties=declared_ties,
        declared_argmin=int(lock["numpy_argmin_fft_peak_index"]),
        selected_bin=selected_bin,
        declared_tie_count=int(lock["tie_candidate_count"]),
        forensic_override=override,
        allow_runtime_argmin_tie_drift=allow_runtime_argmin_tie_drift,
    )

    n = len(y_corrected)
    positive_frequencies = np.abs(
        fftfreq(n, d=(wavelength[1] - wavelength[0]) * 1e-2)[: n // 2]
    )
    if int(lock["positive_frequency_max_index"]) != n // 2 - 1:
        raise ReplayError(f"Positive-frequency lock mismatch: {lock['record_id']}")
    normalized_cutoff = float(positive_frequencies[selected_bin]) / float(
        np.max(positive_frequencies)
    )
    if not math.isclose(
        normalized_cutoff,
        float(lock["normalized_cutoff"]),
        rel_tol=0.0,
        abs_tol=5e-16,
    ):
        raise ReplayError(f"Normalized cutoff changed for {lock['record_id']}")

    b, a = butter(
        N=int(lock["butterworth_order"]),
        Wn=normalized_cutoff,
        btype="low",
    )
    filtered = filtfilt(b, a, y_corrected)
    baseline_2, _ = iarpls(
        filtered,
        lam=float(second["lambda"]),
        diff_order=int(second["diff_order"]),
        max_iter=int(second["max_iter"]),
        tol=float(second["tolerance"]),
        weights=None,
        x_data=None,
    )
    return filtered - baseline_2


def spectra_csv_bytes(
    columns: Sequence[str], arrays: Sequence[np.ndarray], float_spec: str
) -> bytes:
    if not arrays:
        raise ReplayError("Cannot serialize an empty spectrum")
    point_count = len(arrays[0])
    if any(len(array) != point_count for array in arrays):
        raise ReplayError("Spectrum columns have inconsistent lengths")
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for point_index in range(point_count):
        writer.writerow(
            format_float(float(array[point_index]), float_spec) for array in arrays
        )
    return buffer.getvalue().encode("utf-8")


def deterministic_zip(
    members: Mapping[str, bytes], config: Mapping[str, object]
) -> bytes:
    package = config["deterministic_package"]
    timestamp = tuple(int(value) for value in package["zip_timestamp"])
    permissions = int(package["zip_permissions_octal"], 8)
    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=int(package["zip_compresslevel"]),
    ) as archive:
        for member_name in sorted(members):
            require_relative_posix(member_name, "ZIP member")
            info = zipfile.ZipInfo(member_name, date_time=timestamp)
            info.create_system = 3
            info.external_attr = permissions << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(
                info,
                members[member_name],
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=int(package["zip_compresslevel"]),
            )
    return buffer.getvalue()


def readme_bytes(
    source_count: int,
    channel_count: int,
    file_count: int,
    worst_rmse: float,
    worst_max_abs: float,
) -> bytes:
    text = f"""# 4-ATP 750_5_5_M historical computational replay

Status: **audit evidence only**.

This package reproduces the arithmetic that generated the preserved legacy
medium-power outputs. It covers {source_count} exact source files,
{channel_count} spectral channels, {file_count} replayed CSV files, and 432
points per channel.

The replay is not a scientifically corrected reanalysis. The historical
calculation subtracted the first channel of an assembled blank embedded-labelled
`AAB_Blank_750_5_5_H`. That blank is not a confirmed `750_5_5_M` blank and its
context remains a provenance conflict.

The replay uses the recovered positional CSV crop, row-wise blank subtraction,
two iARPLS stages, a third-order Butterworth low-pass filter, and source-bound
FFT-bin locks. Those locks document computational history; they are not
recommended scientific processing parameters.

Verification contract:

- During validated cross-patch checking, a runtime FFT argmin may vary only
  within the exact declared epsilon-scale tie set; the selected source-bound
  bin remains unchanged.
- Raman axes must be exactly equal to the historical references.
- Intensity RMSE must be no greater than `1e-7`.
- Maximum absolute intensity difference must be no greater than `1e-6`.
- Relative tolerance is zero.

Verification modes:

- `--check` runs only in the generation environment and requires every
  regenerated package byte to equal the committed package.
- `--cross-environment-check` independently verifies the exact committed
  hashes, file set, ZIP structure, mappings, headers, and axes, then requires
  every freshly replayed channel to pass the same historical-reference bounds.
  It does not claim that environment-sensitive regenerated intensities or
  compressed bytes are identical.

Observed in the validated package:

- Worst RMSE: `{format_float(worst_rmse)}`.
- Worst maximum absolute difference: `{format_float(worst_max_abs)}`.

The replay proves how the stored numbers were computed. It does not prove that
the inputs, labels, replicates, or mixed high-power blank were scientifically
valid for the medium-power experiment.
"""
    return text.encode("utf-8")


def build_package(
    root: Path,
    config: dict[str, object],
    config_raw: bytes,
    inventory: list[dict[str, str]],
    inventory_raw: bytes,
    manifest: list[dict[str, str]],
    manifest_raw: bytes,
    locks: list[dict[str, str]],
    locks_raw: bytes,
    script_hash: str,
    allow_runtime_argmin_tie_drift: bool,
) -> tuple[dict[str, bytes], dict[str, object]]:
    inventory_by_id, _, locks_by_id = validate_contract(
        root, config, inventory, manifest, locks
    )
    header_row_index = int(config["vendor_csv_reader"]["header_row_index"])
    points_expected = int(config["expected_composition"]["points_per_channel"])
    fft_config = config["processing"]["fft_filter"]
    first_config = config["processing"]["first_iarpls"]
    acceptance = config["acceptance"]
    float_spec = config["deterministic_package"]["csv_float_format"]

    blank_source = next(
        source
        for source in inventory
        if source["lineage_role"] == "assembled_blank"
    )
    blank_path = repository_file(
        root, blank_source["source_path"], "assembled blank source"
    )
    blank_df = read_vendor(blank_path, header_row_index)
    if blank_df.shape != (
        points_expected,
        int(blank_source["intensity_channels"]) + 1,
    ):
        raise ReplayError("Assembled blank does not parse as 432 x 16")
    blank_y = blank_df.iloc[:, 1].to_numpy(dtype=float)

    records_by_source: dict[str, list[dict[str, str]]] = defaultdict(list)
    for record in manifest:
        records_by_source[record["source_id"]].append(record)
    for records in records_by_source.values():
        records.sort(key=lambda row: int(row["source_intensity_column_index"]))

    metric_rows: list[dict[str, object]] = []
    resolved_rows: list[dict[str, object]] = []
    spectra_members: dict[str, bytes] = {}
    member_hash_by_record: dict[str, str] = {}

    for source in inventory:
        source_path = repository_file(
            root, source["source_path"], "source path during replay"
        )
        source_df = read_vendor(source_path, header_row_index)
        expected_shape = (
            points_expected,
            int(source["intensity_channels"]) + 1,
        )
        if source_df.shape != expected_shape:
            raise ReplayError(
                f"Unexpected parsed source shape for {source['source_filename']}: "
                f"{source_df.shape!r}"
            )
        wavelength = source_df.iloc[:, 0].to_numpy(dtype=float)

        reference_path = repository_file(
            root,
            source["historical_reference_path"],
            "historical reference during replay",
        )
        reference_df = pd.read_csv(reference_path)
        if reference_df.shape != expected_shape:
            raise ReplayError(
                f"Unexpected historical shape for {source['source_filename']}"
            )
        reference_x = reference_df.iloc[:, 0].to_numpy(dtype=float)
        axis_equal = bool(np.array_equal(wavelength, reference_x))
        axis_max_abs = float(np.max(np.abs(wavelength - reference_x)))
        if not axis_equal or axis_max_abs != float(acceptance["axis_max_abs_cm-1"]):
            raise ReplayError(
                f"Raman axis mismatch for {source['source_filename']}"
            )

        source_records = records_by_source[source["source_id"]]
        replayed_columns: list[np.ndarray] = []
        output_columns = [str(reference_df.columns[0])]
        source_role = source["lineage_role"]
        expected_lambda = float(first_config["lambda_by_role"][source_role])
        percentile = float(fft_config["percentile_by_role"][source_role])

        for record in source_records:
            channel_index = int(record["source_intensity_column_index"])
            if float(record["baseline_lambda"]) != expected_lambda:
                raise ReplayError(f"Baseline lambda changed for {record['record_id']}")
            if str(reference_df.columns[channel_index]) != record[
                "historical_intensity_column"
            ]:
                raise ReplayError(
                    f"Historical column changed for {record['record_id']}"
                )
            if record["output_intensity_column"] != record[
                "historical_intensity_column"
            ]:
                raise ReplayError(f"Output column changed for {record['record_id']}")

            source_y = source_df.iloc[:, channel_index].to_numpy(dtype=float)
            expected_y = reference_df.iloc[:, channel_index].to_numpy(dtype=float)
            lock = locks_by_id[record["record_id"]]
            replayed_y = replay_with_lock(
                source_y=source_y,
                wavelength=wavelength,
                blank_y=blank_y,
                subtract_blank=source_role != "assembled_blank",
                baseline_lambda=expected_lambda,
                percentile=percentile,
                lock=lock,
                config=config,
                allow_runtime_argmin_tie_drift=allow_runtime_argmin_tie_drift,
            )
            residual = replayed_y - expected_y
            rmse = float(np.sqrt(np.mean(residual**2)))
            mae = float(np.mean(np.abs(residual)))
            max_abs = float(np.max(np.abs(residual)))
            intensity_equal = bool(np.array_equal(replayed_y, expected_y))
            within_tolerance = (
                rmse <= float(acceptance["intensity_rmse_max"])
                and max_abs <= float(acceptance["intensity_max_abs_max"])
                and axis_equal
            )
            if not within_tolerance:
                raise ReplayError(
                    f"Replay tolerance failed for {record['record_id']}: "
                    f"RMSE={rmse!r}, max_abs={max_abs!r}"
                )

            replayed_columns.append(replayed_y)
            output_columns.append(record["output_intensity_column"])
            metric_rows.append(
                {
                    "record_id": record["record_id"],
                    "historical_reference_file": record[
                        "historical_reference_file"
                    ],
                    "historical_intensity_column": record[
                        "historical_intensity_column"
                    ],
                    "replayed_zip_member": record["output_zip_member"],
                    "replayed_intensity_column": record[
                        "output_intensity_column"
                    ],
                    "points": points_expected,
                    "axis_array_equal": str(axis_equal).lower(),
                    "axis_max_abs_cm-1": format_float(axis_max_abs),
                    "intensity_array_equal": str(intensity_equal).lower(),
                    "intensity_rmse": format_float(rmse),
                    "intensity_mae": format_float(mae),
                    "intensity_max_abs": format_float(max_abs),
                    "intensity_rtol": format_float(
                        float(acceptance["intensity_rtol"])
                    ),
                    "intensity_rmse_max": format_float(
                        float(acceptance["intensity_rmse_max"])
                    ),
                    "intensity_max_abs_max": format_float(
                        float(acceptance["intensity_max_abs_max"])
                    ),
                    "within_tolerance": str(within_tolerance).lower(),
                    "filter_fft_peak_index": lock["filter_fft_peak_index"],
                    "tie_candidate_count": lock["tie_candidate_count"],
                    "forensic_override": lock["forensic_override"],
                }
            )

        member_name = source_records[0]["output_zip_member"]
        if any(record["output_zip_member"] != member_name for record in source_records):
            raise ReplayError(f"Source maps to multiple members: {source['source_id']}")
        member_bytes = spectra_csv_bytes(
            output_columns,
            [wavelength, *replayed_columns],
            float_spec=float_spec,
        )
        if member_name in spectra_members:
            raise ReplayError(f"Duplicate replayed member: {member_name}")
        spectra_members[member_name] = member_bytes
        member_hash = sha256_bytes(member_bytes)
        for record in source_records:
            member_hash_by_record[record["record_id"]] = member_hash

    metrics_by_id = {row["record_id"]: row for row in metric_rows}
    for record in manifest:
        metric = metrics_by_id[record["record_id"]]
        resolved_rows.append(
            {
                **record,
                "source_hash_verified": "true",
                "historical_reference_hash_verified": "true",
                "output_member_sha256": member_hash_by_record[record["record_id"]],
                "points": metric["points"],
                "axis_array_equal": metric["axis_array_equal"],
                "intensity_within_tolerance": metric["within_tolerance"],
                "resolution_status": "computational_mapping_resolved",
            }
        )

    if len(spectra_members) != int(config["expected_composition"]["processed_files"]):
        raise ReplayError("Replayed member count is not 43")
    if len(metric_rows) != int(config["expected_composition"]["channels"]):
        raise ReplayError("Metric count is not 225")
    if not all(row["within_tolerance"] == "true" for row in metric_rows):
        raise ReplayError("At least one metric failed")

    metrics_raw = csv_bytes(METRIC_COLUMNS, metric_rows)
    resolved_raw = csv_bytes(RESOLVED_COLUMNS, resolved_rows)
    replay_zip_raw = deterministic_zip(spectra_members, config)
    worst_rmse = max(float(row["intensity_rmse"]) for row in metric_rows)
    worst_max_abs = max(float(row["intensity_max_abs"]) for row in metric_rows)
    readme_raw = readme_bytes(
        source_count=len(inventory),
        channel_count=len(metric_rows),
        file_count=len(spectra_members),
        worst_rmse=worst_rmse,
        worst_max_abs=worst_max_abs,
    )

    package_metadata = {
        "schema_version": "1.1",
        "package": "4atp_750_5_5_M_historical_computational_replay",
        "claim_scope": "computational_lineage_only",
        "release_classification": "audit_evidence_only",
        "byte_identity_claimed": False,
        "scientific_blank_status": "no_confirmed_medium_power_blank",
        "composition": {
            "source_files": len(inventory),
            "source_roles": dict(
                sorted(Counter(row["lineage_role"] for row in inventory).items())
            ),
            "spectral_channels": len(metric_rows),
            "replayed_spectra_files": len(spectra_members),
            "points_per_channel": points_expected,
        },
        "hash_contract": {
            "config_sha256": sha256_bytes(config_raw),
            "source_inventory_sha256": sha256_bytes(inventory_raw),
            "channel_manifest_sha256": sha256_bytes(manifest_raw),
            "fft_locks_sha256": sha256_bytes(locks_raw),
            "replay_script_sha256": script_hash,
        },
        "package_file_hashes": {
            "README.md": sha256_bytes(readme_raw),
            "resolved_manifest.csv": sha256_bytes(resolved_raw),
            "replay_metrics.csv": sha256_bytes(metrics_raw),
            "replayed_spectra.zip": sha256_bytes(replay_zip_raw),
        },
        "acceptance": config["acceptance"],
        "observed": {
            "passing_channels": len(metric_rows),
            "failing_channels": 0,
            "exact_axis_channels": sum(
                row["axis_array_equal"] == "true" for row in metric_rows
            ),
            "exact_intensity_channels": sum(
                row["intensity_array_equal"] == "true" for row in metric_rows
            ),
            "worst_intensity_rmse": worst_rmse,
            "worst_intensity_max_abs": worst_max_abs,
            "fft_tie_channels": sum(
                int(row["tie_candidate_count"]) > 1 for row in metric_rows
            ),
            "forensic_fft_overrides": sum(
                row["forensic_override"] == "true" for row in metric_rows
            ),
        },
        "historical_blank": {
            "source_record_id": config["blank_operation"]["source_record_id"],
            "operation": config["blank_operation"]["operation"],
            "status": config["blank_operation"]["status"],
            "warning": config["blank_operation"]["warning"],
        },
        "processing_summary": config["processing"],
        "validated_environment": config["validated_environment"],
        "verification_modes": config["verification_modes"],
        "deterministic_serialization": config["deterministic_package"],
        "interpretation_limit": config["interpretation_limit"],
    }
    metadata_raw = json_bytes(package_metadata)
    package_files = {
        "README.md": readme_raw,
        "package_metadata.json": metadata_raw,
        "resolved_manifest.csv": resolved_raw,
        "replay_metrics.csv": metrics_raw,
        "replayed_spectra.zip": replay_zip_raw,
    }
    if tuple(package_files) != EXPECTED_PACKAGE_FILES:
        raise ReplayError("Internal package-file ordering changed")

    result = {
        "classification": "audit_evidence_only",
        "claim_scope": "computational_lineage_only",
        "sources": len(inventory),
        "channels": len(metric_rows),
        "spectra_files": len(spectra_members),
        "points_per_channel": points_expected,
        "passing_channels": len(metric_rows),
        "worst_rmse": worst_rmse,
        "worst_max_abs": worst_max_abs,
        "package_hashes": {
            name: sha256_bytes(content) for name, content in package_files.items()
        },
    }
    return package_files, result


def output_directory(root: Path, config: Mapping[str, object]) -> Path:
    return repository_file(
        root, config["paths"]["output_directory"], "output directory"
    )


@contextmanager
def published_release_transaction(
    output: Path,
    package_files: Mapping[str, bytes],
) -> Iterator[None]:
    """Publish one validated directory and restore the previous one on error."""
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        raise ReplayError("Output path exists and is not an ordinary directory")
    if output.exists():
        unexpected = sorted(
            path.name
            for path in output.iterdir()
            if path.name not in EXPECTED_PACKAGE_FILES
        )
        if unexpected:
            raise ReplayError(
                f"Refusing to modify output with unexpected files: {unexpected!r}"
            )

    transaction = output.parent / (
        f".750_5_5_m_replay-{uuid.uuid4().hex}"
    )
    transaction.mkdir()
    try:
        staged = transaction / "staged"
        staged.mkdir()
        for name in EXPECTED_PACKAGE_FILES:
            (staged / name).write_bytes(package_files[name])
        check_release(staged, package_files)

        previous = transaction / "previous"
        failed = transaction / "failed"
        if output.exists():
            os.replace(output, previous)
        try:
            os.replace(staged, output)
        except BaseException:
            if previous.exists():
                os.replace(previous, output)
            raise

        try:
            yield
        except BaseException:
            if output.exists():
                os.replace(output, failed)
            if previous.exists():
                os.replace(previous, output)
            raise
    finally:
        shutil.rmtree(transaction, ignore_errors=True)


def restore_file_bytes(path: Path, content: bytes) -> None:
    """Atomically restore one small repository metadata file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.restore-{uuid.uuid4().hex}"
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def check_release_structure(output: Path) -> dict[str, bytes]:
    if output.is_symlink() or not output.is_dir():
        raise ReplayError("Generated replay package is missing")
    actual_names = sorted(path.name for path in output.iterdir())
    if actual_names != sorted(EXPECTED_PACKAGE_FILES):
        raise ReplayError(
            f"Output file set changed: expected {EXPECTED_PACKAGE_FILES!r}, "
            f"got {actual_names!r}"
        )
    contents: dict[str, bytes] = {}
    for name in EXPECTED_PACKAGE_FILES:
        path = output / name
        if path.is_symlink() or not path.is_file():
            raise ReplayError(f"Replay-package member is not an ordinary file: {name}")
        contents[name] = path.read_bytes()

    with zipfile.ZipFile(output / "replayed_spectra.zip") as archive:
        members = archive.infolist()
        if [member.filename for member in members] != sorted(
            member.filename for member in members
        ):
            raise ReplayError("ZIP member order is not deterministic")
        if len(members) != 43:
            raise ReplayError("ZIP member count is not 43")
        for member in members:
            if member.date_time != (1980, 1, 1, 0, 0, 0):
                raise ReplayError(f"Non-deterministic ZIP timestamp: {member.filename}")
            if (member.external_attr >> 16) != 0o100644:
                raise ReplayError(
                    f"Non-deterministic ZIP permissions: {member.filename}"
                )
            if member.compress_type != zipfile.ZIP_DEFLATED:
                raise ReplayError(
                    f"Unexpected ZIP compression: {member.filename}"
                )
    return contents


def check_release(output: Path, package_files: Mapping[str, bytes]) -> None:
    contents = check_release_structure(output)
    mismatches = [
        name
        for name in EXPECTED_PACKAGE_FILES
        if contents[name] != package_files[name]
    ]
    if mismatches:
        raise ReplayError(
            f"Generated package is not deterministic/current: {mismatches!r}"
        )


def metric_observed_contract(
    rows: Sequence[Mapping[str, str]],
    config: Mapping[str, object],
    label: str,
) -> dict[str, object]:
    expected = config["expected_composition"]
    acceptance = config["acceptance"]
    fft_config = config["processing"]["fft_filter"]
    expected_channels = int(expected["channels"])
    if len(rows) != expected_channels:
        raise ReplayError(f"{label} metric count is not {expected_channels}")
    record_ids = [row["record_id"] for row in rows]
    if len(set(record_ids)) != len(record_ids):
        raise ReplayError(f"{label} contains duplicate metric record IDs")

    passing = 0
    exact_axes = 0
    exact_intensities = 0
    tie_channels = 0
    overrides = 0
    rmse_values: list[float] = []
    max_abs_values: list[float] = []
    for row in rows:
        record_id = row["record_id"]
        try:
            points = int(row["points"])
            axis_max_abs = float(row["axis_max_abs_cm-1"])
            rmse = float(row["intensity_rmse"])
            mae = float(row["intensity_mae"])
            max_abs = float(row["intensity_max_abs"])
            rtol = float(row["intensity_rtol"])
            rmse_max = float(row["intensity_rmse_max"])
            max_abs_max = float(row["intensity_max_abs_max"])
            tie_count = int(row["tie_candidate_count"])
        except ValueError as error:
            raise ReplayError(
                f"{label} contains an invalid numeric metric for {record_id}"
            ) from error
        numeric_values = (
            axis_max_abs,
            rmse,
            mae,
            max_abs,
            rtol,
            rmse_max,
            max_abs_max,
        )
        if not all(math.isfinite(value) for value in numeric_values):
            raise ReplayError(f"{label} contains a non-finite metric for {record_id}")
        axis_equal = parse_bool(row["axis_array_equal"], "axis_array_equal")
        intensity_equal = parse_bool(
            row["intensity_array_equal"], "intensity_array_equal"
        )
        within_tolerance = parse_bool(row["within_tolerance"], "within_tolerance")
        override = parse_bool(row["forensic_override"], "forensic_override")
        if (
            points != int(expected["points_per_channel"])
            or axis_equal is not bool(acceptance["axis_array_equal"])
            or axis_max_abs != float(acceptance["axis_max_abs_cm-1"])
            or rtol != float(acceptance["intensity_rtol"])
            or rmse_max != float(acceptance["intensity_rmse_max"])
            or max_abs_max != float(acceptance["intensity_max_abs_max"])
            or min(rmse, mae, max_abs) < 0.0
            or rmse > rmse_max
            or max_abs > max_abs_max
            or mae > max_abs
            or not within_tolerance
        ):
            raise ReplayError(
                f"{label} violates the numerical acceptance contract for {record_id}"
            )
        passing += int(within_tolerance)
        exact_axes += int(axis_equal)
        exact_intensities += int(intensity_equal)
        tie_channels += int(tie_count > 1)
        overrides += int(override)
        rmse_values.append(rmse)
        max_abs_values.append(max_abs)

    observed = {
        "passing_channels": passing,
        "failing_channels": expected_channels - passing,
        "exact_axis_channels": exact_axes,
        "exact_intensity_channels": exact_intensities,
        "worst_intensity_rmse": max(rmse_values),
        "worst_intensity_max_abs": max(max_abs_values),
        "fft_tie_channels": tie_channels,
        "forensic_fft_overrides": overrides,
    }
    if tie_channels != int(fft_config["expected_tie_channels"]):
        raise ReplayError(f"{label} FFT tie count changed")
    if overrides != int(fft_config["expected_forensic_overrides"]):
        raise ReplayError(f"{label} forensic-override count changed")
    return observed


def check_declared_payload_hashes(
    metadata: Mapping[str, object],
    package_files: Mapping[str, bytes],
    label: str,
) -> None:
    declared = metadata.get("package_file_hashes")
    payload_names = set(EXPECTED_PACKAGE_FILES) - {"package_metadata.json"}
    if not isinstance(declared, dict) or set(declared) != payload_names:
        raise ReplayError(f"{label} package-file hash declaration changed")
    for name in sorted(payload_names):
        if declared[name] != sha256_bytes(package_files[name]):
            raise ReplayError(f"{label} package hash mismatch: {name}")


def compare_stable_rows(
    committed: Sequence[Mapping[str, str]],
    regenerated: Sequence[Mapping[str, str]],
    stable_fields: Sequence[str],
    label: str,
) -> None:
    if len(committed) != len(regenerated):
        raise ReplayError(f"{label} row count changed across environments")
    for index, (committed_row, regenerated_row) in enumerate(
        zip(committed, regenerated, strict=True),
        start=1,
    ):
        for field in stable_fields:
            if committed_row[field] != regenerated_row[field]:
                raise ReplayError(
                    f"{label} stable field changed at row {index}: {field}"
                )


def zip_member_payloads(content: bytes, label: str) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            return {
                member.filename: archive.read(member)
                for member in archive.infolist()
            }
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        raise ReplayError(f"{label} is not a readable ZIP archive") from error


def validate_resolved_member_hashes(
    rows: Sequence[Mapping[str, str]],
    members: Mapping[str, bytes],
    label: str,
) -> None:
    hashes_by_member: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        hashes_by_member[row["output_zip_member"]].add(
            row["output_member_sha256"]
        )
    if set(hashes_by_member) != set(members):
        raise ReplayError(f"{label} resolved manifest does not cover its ZIP exactly")
    for name, declared_hashes in hashes_by_member.items():
        if declared_hashes != {sha256_bytes(members[name])}:
            raise ReplayError(f"{label} resolved ZIP-member hash mismatch: {name}")


def spectra_header_and_axis(
    content: bytes,
    expected_points: int,
    label: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    try:
        rows = list(
            csv.reader(
                io.StringIO(content.decode("utf-8"), newline=""),
            )
        )
    except UnicodeDecodeError as error:
        raise ReplayError(f"{label} is not valid UTF-8 CSV") from error
    if len(rows) != expected_points + 1 or not rows or len(rows[0]) < 2:
        raise ReplayError(f"{label} has an unexpected spectral table shape")
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ReplayError(f"{label} has inconsistent CSV row widths")
    return tuple(rows[0]), tuple(row[0] for row in rows[1:])


def spectra_csv_arrays(
    content: bytes,
    expected_points: int,
    label: str,
) -> tuple[tuple[str, ...], np.ndarray]:
    try:
        rows = list(
            csv.reader(
                io.StringIO(content.decode("utf-8"), newline=""),
            )
        )
    except UnicodeDecodeError as error:
        raise ReplayError(f"{label} is not valid UTF-8 CSV") from error
    if len(rows) != expected_points + 1 or not rows or len(rows[0]) < 2:
        raise ReplayError(f"{label} has an unexpected spectral table shape")
    header = tuple(rows[0])
    if len(set(header)) != len(header):
        raise ReplayError(f"{label} contains duplicate column names")
    if any(len(row) != len(header) for row in rows):
        raise ReplayError(f"{label} has inconsistent CSV row widths")
    try:
        values = np.asarray(
            [[float(value) for value in row] for row in rows[1:]],
            dtype=float,
        )
    except ValueError as error:
        raise ReplayError(f"{label} contains a non-numeric spectral value") from error
    if not np.all(np.isfinite(values)):
        raise ReplayError(f"{label} contains a non-finite spectral value")
    return header, values


def validate_committed_package_against_historical(
    root: Path,
    config: Mapping[str, object],
    resolved_rows: Sequence[Mapping[str, str]],
    metric_rows: Sequence[Mapping[str, str]],
    members: Mapping[str, bytes],
) -> int:
    """Recompute every committed ZIP metric against its historical reference."""
    metrics_by_id = {row["record_id"]: row for row in metric_rows}
    resolved_by_id = {row["record_id"]: row for row in resolved_rows}
    if (
        len(metrics_by_id) != len(metric_rows)
        or len(resolved_by_id) != len(resolved_rows)
        or set(metrics_by_id) != set(resolved_by_id)
    ):
        raise ReplayError("Committed metric/resolved record coverage changed")

    rows_by_member: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in resolved_rows:
        rows_by_member[row["output_zip_member"]].append(row)
    if set(rows_by_member) != set(members):
        raise ReplayError("Committed ZIP mapping does not cover every member")

    acceptance = config["acceptance"]
    expected_points = int(config["expected_composition"]["points_per_channel"])
    verified = 0
    for member_name, member_rows in sorted(rows_by_member.items()):
        reference_paths = {
            row["historical_reference_path"] for row in member_rows
        }
        if len(reference_paths) != 1:
            raise ReplayError(
                f"Committed ZIP member maps to multiple references: {member_name}"
            )
        reference_path = repository_file(
            root,
            next(iter(reference_paths)),
            "committed historical reference",
        )
        reference_df = pd.read_csv(reference_path)
        member_header, member_values = spectra_csv_arrays(
            members[member_name],
            expected_points,
            f"committed ZIP member {member_name}",
        )
        reference_header = tuple(str(column) for column in reference_df.columns)
        if member_header != reference_header:
            raise ReplayError(
                f"Committed ZIP header differs from historical reference: {member_name}"
            )
        reference_values = reference_df.to_numpy(dtype=float)
        if member_values.shape != reference_values.shape:
            raise ReplayError(
                f"Committed ZIP shape differs from historical reference: {member_name}"
            )
        axis_equal = bool(
            np.array_equal(member_values[:, 0], reference_values[:, 0])
        )
        axis_max_abs = float(
            np.max(np.abs(member_values[:, 0] - reference_values[:, 0]))
        )
        if (
            not axis_equal
            or axis_max_abs != float(acceptance["axis_max_abs_cm-1"])
        ):
            raise ReplayError(
                f"Committed ZIP Raman axis differs from historical reference: "
                f"{member_name}"
            )
        mapped_columns = {
            row["output_intensity_column"] for row in member_rows
        }
        if mapped_columns != set(member_header[1:]):
            raise ReplayError(
                f"Committed ZIP channel mapping changed: {member_name}"
            )

        column_indices = {
            column: index for index, column in enumerate(member_header)
        }
        for row in member_rows:
            record_id = row["record_id"]
            output_column = row["output_intensity_column"]
            historical_column = row["historical_intensity_column"]
            if output_column != historical_column:
                raise ReplayError(
                    f"Committed output/reference column changed for {record_id}"
                )
            column_index = column_indices[output_column]
            residual = (
                member_values[:, column_index]
                - reference_values[:, column_index]
            )
            rmse = float(np.sqrt(np.mean(residual**2)))
            mae = float(np.mean(np.abs(residual)))
            max_abs = float(np.max(np.abs(residual)))
            intensity_equal = bool(
                np.array_equal(
                    member_values[:, column_index],
                    reference_values[:, column_index],
                )
            )
            within_tolerance = (
                rmse <= float(acceptance["intensity_rmse_max"])
                and max_abs <= float(acceptance["intensity_max_abs_max"])
                and axis_equal
            )
            stored = metrics_by_id[record_id]
            if (
                float(stored["axis_max_abs_cm-1"]) != axis_max_abs
                or parse_bool(
                    stored["axis_array_equal"], "axis_array_equal"
                )
                != axis_equal
                or float(stored["intensity_rmse"]) != rmse
                or float(stored["intensity_mae"]) != mae
                or float(stored["intensity_max_abs"]) != max_abs
                or parse_bool(
                    stored["intensity_array_equal"], "intensity_array_equal"
                )
                != intensity_equal
                or parse_bool(stored["within_tolerance"], "within_tolerance")
                != within_tolerance
                or not within_tolerance
            ):
                raise ReplayError(
                    f"Committed ZIP metric is stale for {record_id}"
                )
            verified += 1
    return verified


def check_cross_environment_release(
    root: Path,
    output: Path,
    regenerated_package: Mapping[str, bytes],
    config: Mapping[str, object],
) -> dict[str, int]:
    """Verify numerical replay plus immutable committed-release integrity."""
    committed_package = check_release_structure(output)
    if set(regenerated_package) != set(EXPECTED_PACKAGE_FILES):
        raise ReplayError("Regenerated package file set changed")

    committed_metadata = read_json_object(
        committed_package["package_metadata.json"],
        "committed package_metadata.json",
    )
    regenerated_metadata = read_json_object(
        regenerated_package["package_metadata.json"],
        "regenerated package_metadata.json",
    )
    if set(committed_metadata) != set(regenerated_metadata):
        raise ReplayError("Package-metadata fields changed across environments")
    dynamic_metadata_fields = {"observed", "package_file_hashes"}
    for field in sorted(set(committed_metadata) - dynamic_metadata_fields):
        if committed_metadata[field] != regenerated_metadata[field]:
            raise ReplayError(
                f"Package-metadata contract changed across environments: {field}"
            )
    check_declared_payload_hashes(
        committed_metadata,
        committed_package,
        "committed",
    )
    check_declared_payload_hashes(
        regenerated_metadata,
        regenerated_package,
        "regenerated",
    )

    committed_resolved = read_csv_bytes_contract(
        committed_package["resolved_manifest.csv"],
        RESOLVED_COLUMNS,
        "committed resolved_manifest.csv",
    )
    regenerated_resolved = read_csv_bytes_contract(
        regenerated_package["resolved_manifest.csv"],
        RESOLVED_COLUMNS,
        "regenerated resolved_manifest.csv",
    )
    compare_stable_rows(
        committed_resolved,
        regenerated_resolved,
        [field for field in RESOLVED_COLUMNS if field != "output_member_sha256"],
        "resolved manifest",
    )

    committed_metrics = read_csv_bytes_contract(
        committed_package["replay_metrics.csv"],
        METRIC_COLUMNS,
        "committed replay_metrics.csv",
    )
    regenerated_metrics = read_csv_bytes_contract(
        regenerated_package["replay_metrics.csv"],
        METRIC_COLUMNS,
        "regenerated replay_metrics.csv",
    )
    environment_sensitive_metric_fields = {
        "intensity_array_equal",
        "intensity_rmse",
        "intensity_mae",
        "intensity_max_abs",
    }
    compare_stable_rows(
        committed_metrics,
        regenerated_metrics,
        [
            field
            for field in METRIC_COLUMNS
            if field not in environment_sensitive_metric_fields
        ],
        "replay metrics",
    )
    committed_observed = metric_observed_contract(
        committed_metrics,
        config,
        "committed",
    )
    regenerated_observed = metric_observed_contract(
        regenerated_metrics,
        config,
        "regenerated",
    )
    if committed_metadata["observed"] != committed_observed:
        raise ReplayError("Committed package observed summary is stale")
    if regenerated_metadata["observed"] != regenerated_observed:
        raise ReplayError("Regenerated package observed summary is inconsistent")

    committed_members = zip_member_payloads(
        committed_package["replayed_spectra.zip"],
        "committed replayed_spectra.zip",
    )
    regenerated_members = zip_member_payloads(
        regenerated_package["replayed_spectra.zip"],
        "regenerated replayed_spectra.zip",
    )
    if set(committed_members) != set(regenerated_members):
        raise ReplayError("Replayed ZIP member set changed across environments")
    validate_resolved_member_hashes(
        committed_resolved,
        committed_members,
        "committed",
    )
    validate_resolved_member_hashes(
        regenerated_resolved,
        regenerated_members,
        "regenerated",
    )
    committed_channels_verified = (
        validate_committed_package_against_historical(
            root,
            config,
            committed_resolved,
            committed_metrics,
            committed_members,
        )
    )
    expected_points = int(config["expected_composition"]["points_per_channel"])
    for name in sorted(committed_members):
        committed_table = spectra_header_and_axis(
            committed_members[name],
            expected_points,
            f"committed ZIP member {name}",
        )
        regenerated_table = spectra_header_and_axis(
            regenerated_members[name],
            expected_points,
            f"regenerated ZIP member {name}",
        )
        if committed_table != regenerated_table:
            raise ReplayError(
                f"Replayed ZIP header or Raman axis changed across environments: {name}"
            )

    composition = committed_metadata.get("composition")
    if not isinstance(composition, dict):
        raise ReplayError("Committed package composition is invalid")
    expected_readme = readme_bytes(
        source_count=int(composition["source_files"]),
        channel_count=int(composition["spectral_channels"]),
        file_count=int(composition["replayed_spectra_files"]),
        worst_rmse=float(committed_observed["worst_intensity_rmse"]),
        worst_max_abs=float(committed_observed["worst_intensity_max_abs"]),
    )
    if committed_package["README.md"] != expected_readme:
        raise ReplayError("Committed replay-package README is stale")

    return {
        "committed_payload_hashes_verified": len(EXPECTED_PACKAGE_FILES) - 1,
        "stable_mapping_rows_verified": len(committed_resolved),
        "numerical_metric_rows_verified": len(regenerated_metrics),
        "committed_channels_historical_reference_verified": (
            committed_channels_verified
        ),
        "zip_members_structurally_verified": len(committed_members),
    }


def check_dataset_manifest(
    root: Path,
    config: Mapping[str, object],
    inventory: Sequence[Mapping[str, str]],
) -> int:
    """Require every replay input/support/output to have a conservative row."""
    manifest_path = repository_file(
        root, "metadata/dataset_manifest.csv", "dataset manifest path"
    )
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or ())
        missing = sorted(DATASET_MANIFEST_REQUIRED_COLUMNS - fieldnames)
        if missing:
            raise ReplayError(
                "Dataset manifest is missing required columns: "
                + ", ".join(missing)
            )
        rows = list(reader)

    rows_by_path: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        rows_by_path[row["repository_path"]].append(row)

    expected: dict[str, tuple[str, str]] = {}
    for source in inventory:
        role = (
            "historical_blank_composite_source"
            if source["lineage_role"] == "assembled_blank"
            else "historical_computational_replay_source"
        )
        expected[source["source_path"]] = (
            source["source_provenance_status"],
            role,
        )
        expected[source["historical_reference_path"]] = (
            "provenance_conflict",
            "processed_spectrum",
        )

    lock_path = config["paths"]["fft_locks"]
    expected[lock_path] = ("audit_evidence", "processing_parameter_lock")
    output_path = require_relative_posix(
        config["paths"]["output_directory"], "output directory"
    )
    for name in EXPECTED_PACKAGE_FILES:
        expected[(output_path / name).as_posix()] = (
            "audit_evidence",
            "historical_computational_replay",
        )

    if len(expected) != 92:
        raise ReplayError(
            f"Internal dataset-manifest expectation changed: {len(expected)}"
        )
    for repository_path, (status, role) in expected.items():
        matching_rows = rows_by_path.get(repository_path, [])
        if len(matching_rows) != 1:
            raise ReplayError(
                "Dataset manifest must contain exactly one row for "
                f"{repository_path!r}; found {len(matching_rows)}"
            )
        row = matching_rows[0]
        if (row["status"], row["role"]) != (status, role):
            raise ReplayError(
                f"Dataset manifest classification changed for {repository_path!r}"
            )
        file_path = repository_file(root, repository_path, "manifested replay file")
        if file_path.is_symlink() or not file_path.is_file():
            raise ReplayError(
                f"Manifested replay file is missing or unsafe: {repository_path!r}"
            )
        if row["repository_sha256"] != sha256_file(file_path):
            raise ReplayError(
                f"Dataset manifest hash is stale for {repository_path!r}"
            )
        if row["repository_bytes"] != str(file_path.stat().st_size):
            raise ReplayError(
                f"Dataset manifest byte count is stale for {repository_path!r}"
            )
    return len(expected)


def refresh_repository_manifest(root: Path) -> dict[str, object]:
    """Refresh the stable 4-ATP manifest suffix after publishing new bytes."""
    try:
        from scripts.prepare_repository_data import (
            refresh_confirmed_4atp_reanalysis_metadata,
        )
    except ModuleNotFoundError as error:
        if error.name != "scripts":
            raise
        from prepare_repository_data import (  # type: ignore[no-redef]
            refresh_confirmed_4atp_reanalysis_metadata,
        )

    return refresh_confirmed_4atp_reanalysis_metadata(root)


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    verification = parser.add_mutually_exclusive_group()
    verification.add_argument(
        "--check",
        action="store_true",
        help=(
            "Rebuild in memory and require the released five-file package and "
            "its conservative dataset-manifest coverage to match."
        ),
    )
    verification.add_argument(
        "--cross-environment-check",
        action="store_true",
        help=(
            "Replay in the declared compatible environment, enforce every "
            "scientific tolerance and stable mapping, and independently verify "
            "the exact hashes and structure of the committed package."
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    root = (
        arguments.repo_root.resolve()
        if arguments.repo_root is not None
        else Path(__file__).resolve().parents[1]
    )
    try:
        (
            config,
            config_raw,
            inventory,
            inventory_raw,
            manifest,
            manifest_raw,
            locks,
            locks_raw,
            runtime,
        ) = load_contract(
            root,
            allow_cross_environment_python=arguments.cross_environment_check,
        )
        package_files, result = build_package(
            root=root,
            config=config,
            config_raw=config_raw,
            inventory=inventory,
            inventory_raw=inventory_raw,
            manifest=manifest,
            manifest_raw=manifest_raw,
            locks=locks,
            locks_raw=locks_raw,
            script_hash=sha256_file(Path(__file__)),
            allow_runtime_argmin_tie_drift=arguments.cross_environment_check,
        )
        result["verified_runtime"] = runtime
        output = output_directory(root, config)
        if arguments.check:
            check_release(output, package_files)
            result["dataset_manifest_files_verified"] = check_dataset_manifest(
                root,
                config,
                inventory,
            )
            result["mode"] = "check"
            result["status"] = "exact_package_verified"
        elif arguments.cross_environment_check:
            result["release_integrity"] = check_cross_environment_release(
                root,
                output,
                package_files,
                config,
            )
            result["dataset_manifest_files_verified"] = check_dataset_manifest(
                root,
                config,
                inventory,
            )
            result["mode"] = "cross_environment_check"
            result["status"] = (
                "numerical_replay_and_committed_release_integrity_verified"
            )
        else:
            metadata_paths = (
                root / "metadata" / "dataset_manifest.csv",
                root / "metadata" / "curation_summary.json",
            )
            metadata_snapshots: dict[Path, bytes] = {}
            for path in metadata_paths:
                if path.is_symlink() or not path.is_file():
                    raise ReplayError(
                        f"Release metadata is missing or unsafe: {path}"
                    )
                metadata_snapshots[path] = path.read_bytes()
            try:
                with published_release_transaction(output, package_files):
                    result["release_metadata"] = refresh_repository_manifest(root)
                    result["dataset_manifest_files_verified"] = (
                        check_dataset_manifest(
                            root,
                            config,
                            inventory,
                        )
                    )
            except BaseException:
                for path, content in metadata_snapshots.items():
                    restore_file_bytes(path, content)
                raise
            result["mode"] = "generate"
            result["status"] = "generated_and_verified"
        result["output_directory"] = config["paths"]["output_directory"]
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (RuntimeError, OSError, KeyError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
