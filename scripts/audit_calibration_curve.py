#!/usr/bin/env python3
"""Audit and replay the calibration-curve data used for Figures 3 and 4A.

This module deliberately separates three questions:

1. Where did every prepared calibration scan come from?
2. Can the preserved October 2025 processed tables be regenerated?
3. Do the regenerated data support the manuscript's quantitative model claims?

The historical publication snapshot is never overwritten.  The replay retains
the recovered October 2025 numerical chain, including its mixed high-power
blank, solely to establish computational lineage.  Blank alternatives in this
audit are labelled counterfactual sensitivity analyses; none is presented as a
scientifically valid replacement for the missing low-power AuAgBC blank.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import platform
import re
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from pybaselines import whittaker
from scipy.fft import fft, fftfreq
from scipy.optimize import curve_fit
from scipy.signal import butter, filtfilt, find_peaks


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

SOURCE_MATCHES = REPOSITORY_ROOT / "metadata/provenance/raw_to_master_best_matches.csv"
RAW_MANIFEST = REPOSITORY_ROOT / "metadata/raw_processing_manifest.csv"
LEGACY_SCRIPT_INVENTORY = REPOSITORY_ROOT / "metadata/legacy_script_inventory.csv"
LEGACY_CALIBRATION_ROOT = (
    REPOSITORY_ROOT / "data/quarantine/legacy_snapshot/Calibration curve"
)
LEGACY_ORIGINAL_ROOT = LEGACY_CALIBRATION_ROOT / "Original spectra"
PUBLISHED_ROOT = REPOSITORY_ROOT / "data/published_snapshot/calibration_curve"
PUBLISHED_WIDE = PUBLISHED_ROOT / "final_spectra_by_accumulation_wide.csv"
PUBLISHED_REPLICATE = PUBLISHED_ROOT / "replicate_mean_sd_by_shift.csv"
PUBLISHED_SUMMARY = PUBLISHED_ROOT / "summary_by_concentration.csv"
PUBLISHED_SELECTED = PUBLISHED_ROOT / "calibration_at_selected_shifts.csv"
PAPER_PARAMETERS = (
    REPOSITORY_ROOT / "data/published_snapshot/paper_tables/calibration_parameters.csv"
)

LINEAGE_OUTPUT = REPOSITORY_ROOT / "metadata/provenance/calibration_scan_lineage.csv"
REUSE_OUTPUT = REPOSITORY_ROOT / "metadata/provenance/calibration_source_reuse.csv"
FFT_LOCK_OUTPUT = (
    REPOSITORY_ROOT
    / "metadata/processing_locks/calibration_curve_historical_replay_fft_cutoffs.csv"
)
REPLAY_METRICS_OUTPUT = (
    REPOSITORY_ROOT / "metadata/validation/calibration_replay_metrics.csv"
)
TABLE_METRICS_OUTPUT = (
    REPOSITORY_ROOT / "metadata/validation/calibration_table_replay_metrics.csv"
)
MODEL_SENSITIVITY_OUTPUT = (
    REPOSITORY_ROOT / "metadata/validation/calibration_model_sensitivity.csv"
)
PARAMETER_COMPARISON_OUTPUT = (
    REPOSITORY_ROOT / "metadata/validation/calibration_parameter_comparison.csv"
)
CLAIM_ASSESSMENT_OUTPUT = (
    REPOSITORY_ROOT / "metadata/validation/calibration_claim_assessment.csv"
)
SUMMARY_OUTPUT = (
    REPOSITORY_ROOT / "metadata/validation/calibration_audit_summary.json"
)
REPLAY_MANIFEST_OUTPUT = (
    REPOSITORY_ROOT
    / "configs/reanalysis/calibration_curve_historical_replay_manifest.csv"
)
REPLAY_CONFIG_OUTPUT = (
    REPOSITORY_ROOT
    / "configs/reanalysis/calibration_curve_historical_replay.json"
)

EXPECTED_DATE = "03-07-24"
EXPECTED_SETTING = "750_5_5_L"
EXPECTED_ROWS = 210
EXPECTED_SAMPLE_ROWS = 195
EXPECTED_BLANK_ROWS = 15
EXPECTED_GRID_POINTS = 416
EXPECTED_UNIQUE_SOURCE_SCANS = 204
HISTORICAL_GENERATOR_PATH = (
    "Scripts/Latest/4-ATP/Raman Portatil/"
    "raman_sers_pipeline_merged_spyder_UPDATED2.py"
)
HISTORICAL_GENERATOR_SHA256 = (
    "ec6583400df1615d808f07299d6e2e1f8eeb4ae7f7340f796da2c45610443892"
)

X_MIN_CM1 = 341.6070517
BASELINE_LAMBDA = 3000.0
FILTER_PERCENTILE = 60.0
FILTER_ORDER = 2
SECOND_BASELINE_LAMBDA = 600.0
POST_BASELINE_LAMBDA = 5_000_000.0
POST_BASELINE_P = 0.001

REPLAY_ABSOLUTE_TOLERANCE = 2.0e-4
AXIS_ABSOLUTE_TOLERANCE = 6.0e-6
CHECK_NUMERIC_ABSOLUTE_TOLERANCE = 2.0e-4
CHECK_NUMERIC_RELATIVE_TOLERANCE = 2.0e-6
DIAGNOSTIC_FIT_RELATIVE_TOLERANCE = 2.0e-4
MODEL_DIAGNOSTIC_RELATIVE_COLUMNS = (
    "Y0",
    "k",
    "R2",
    "Y0_formal_local_relative_standard_error",
    "k_formal_local_relative_standard_error",
    "historical_initializer_rss_ratio_to_best",
    "LOD_mean_plus_3sd_M",
    "LOQ_mean_plus_10sd_M",
    "LOD_legacy_3sd_only_M",
    "LOQ_legacy_10sd_only_M",
)
MODEL_EXACT_NUMERIC_COLUMNS = (
    "peak_cm-1",
    "n_scan_records",
    "n_nominal_prepared_replicate_groups",
    "n_concentrations",
    "concentration_min_M",
    "concentration_max_M",
    "concentration_span_decades",
    "n_blank_scans",
)
PARAMETER_DIAGNOSTIC_RELATIVE_COLUMNS = (
    "replayed_Y0",
    "Y0_ratio_replayed_to_paper",
    "replayed_k",
    "k_difference",
    "replayed_R2",
    "R2_difference",
    "diagnostic_inverted_blank_mean_plus_3sd_M",
    "diagnostic_inverted_blank_mean_plus_10sd_M",
)
PARAMETER_EXACT_NUMERIC_COLUMNS = (
    "paper_shift_cm-1",
    "replayed_peak_cm-1",
    "paper_Y0",
    "paper_k",
    "paper_R2",
    "paper_LOD_M",
    "paper_LOQ_M",
    "diagnostic_blank_scan_count",
)

PEAKS = (
    (392.32, 10.0),
    (1078.50, 7.0),
    (1589.62, 8.0),
)

CONCENTRATION_LABELS = {
    1e-3: "1mM",
    1e-4: "100uM",
    1e-5: "10uM",
    1e-6: "1uM",
    1e-7: "100nM",
    1e-8: "10nM",
    1e-9: "1nM",
    1e-10: "100pM",
    1e-11: "10pM",
    1e-12: "1pM",
    1e-13: "100fM",
    1e-14: "10fM",
    1e-15: "1fM",
}


class CalibrationAuditError(RuntimeError):
    """Raised when the calibration audit's evidence contract is violated."""


@dataclass(frozen=True)
class Replay:
    x: np.ndarray
    preprocessed: np.ndarray
    final_by_blank_strategy: Mapping[str, np.ndarray]
    blank_indices_by_strategy: Mapping[str, np.ndarray]
    fft_locks: pd.DataFrame
    fft_lock_current_peak_count: int
    records: pd.DataFrame


def _portable(path: Path) -> str:
    return path.as_posix()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _package_version(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def _local_path_from_curated(curated_path: str) -> Path:
    prefix = "Raman_spectra_data/"
    if not str(curated_path).startswith(prefix):
        raise CalibrationAuditError(f"Unexpected curated path: {curated_path}")
    relative = str(curated_path)[len(prefix) :]
    return REPOSITORY_ROOT / "data/quarantine/legacy_snapshot" / Path(relative)


def _parse_prepared_name(path: str) -> tuple[str, str, float, int, int]:
    name = Path(path).name
    blank = re.fullmatch(r"blank_rep(\d+)_acc(\d+)\.csv", name, flags=re.I)
    if blank:
        return "blank", "Blank", 0.0, int(blank.group(1)), int(blank.group(2))
    sample = re.fullmatch(
        r"4ATP_(1mM|100uM|10uM|1uM|100nM|10nM|1nM|100pM|10pM|1pM|100fM|10fM|1fM)"
        r"_rep(\d+)_acc(\d+)\.csv",
        name,
        flags=re.I,
    )
    if not sample:
        raise CalibrationAuditError(f"Could not parse calibration filename: {name}")
    label_lookup = {value.casefold(): (key, value) for key, value in CONCENTRATION_LABELS.items()}
    concentration, canonical_label = label_lookup[sample.group(1).casefold()]
    return (
        "sample",
        canonical_label,
        float(concentration),
        int(sample.group(2)),
        int(sample.group(3)),
    )


def build_lineage() -> pd.DataFrame:
    matches = pd.read_csv(SOURCE_MATCHES)
    matches = matches[matches["curated_group"].eq("Calibration curve")].copy()
    if len(matches) != EXPECTED_ROWS:
        raise CalibrationAuditError(
            f"Expected {EXPECTED_ROWS} calibration matches; found {len(matches)}."
        )
    if not np.allclose(
        pd.to_numeric(matches["intensity_max_abs_difference"], errors="raise"),
        0.0,
        rtol=0.0,
        atol=0.0,
    ):
        raise CalibrationAuditError("A calibration source match is not intensity-exact.")
    if not matches["concentration_agrees"].astype(bool).all():
        raise CalibrationAuditError("A calibration source match has a concentration conflict.")

    manifest = pd.read_csv(RAW_MANIFEST)
    manifest = manifest[manifest["record_group"].eq("calibration_curve")].copy()
    if len(manifest) != EXPECTED_ROWS:
        raise CalibrationAuditError(
            f"Expected {EXPECTED_ROWS} calibration manifest rows; found {len(manifest)}."
        )
    ordered_files = {
        _portable(Path(value)): index for index, value in enumerate(manifest["file"], start=1)
    }

    rows: list[dict[str, Any]] = []
    for match in matches.to_dict(orient="records"):
        local_path = _local_path_from_curated(str(match["curated_path"]))
        if not local_path.is_file():
            raise CalibrationAuditError(f"Missing prepared calibration file: {local_path}")
        relative = _portable(local_path.relative_to(REPOSITORY_ROOT))
        if relative not in ordered_files:
            raise CalibrationAuditError(
                f"Source-match row is absent from raw_processing_manifest.csv: {relative}"
            )
        sample_type, label, concentration, replicate, accumulation = _parse_prepared_name(
            relative
        )
        source_path = str(match["master_path"])
        source_column_index = int(match["master_column_index"])
        source_scan_id = f"{source_path}#{source_column_index}"
        source_replicate_match = re.search(r"_S(\d+)\.csv$", source_path, flags=re.I)
        source_replicate = (
            int(source_replicate_match.group(1)) if source_replicate_match else ""
        )
        setting_matches = str(match["master_setting"]) == EXPECTED_SETTING
        date_matches = str(match["master_date"]) == EXPECTED_DATE
        axis_matches = bool(match["axis_match_1e-5"])
        if sample_type == "blank":
            lineage_class = (
                "exact_intensity_blank_wrong_context_axis_match"
                if axis_matches
                else "exact_intensity_blank_wrong_context_axis_conflict"
            )
            scientific_status = (
                "publication_snapshot_only_missing_context_matched_blank"
            )
        elif setting_matches and date_matches and axis_matches:
            lineage_class = "exact_intensity_axis_context_consistent_sample"
            scientific_status = (
                "source_intensity_exact_axis_within_1e-5_context_consistent"
            )
        elif not axis_matches:
            lineage_class = (
                "exact_intensity_acquisition_context_and_axis_conflict"
            )
            scientific_status = (
                "publication_snapshot_only_mixed_acquisition_and_axis"
            )
        else:
            lineage_class = "exact_intensity_acquisition_context_conflict"
            scientific_status = "publication_snapshot_only_mixed_acquisition"
        rows.append(
            {
                "manifest_order": ordered_files[relative],
                "prepared_file": relative,
                "prepared_sha256": _sha256(local_path),
                "sample_type": sample_type,
                "concentration_M": concentration,
                "concentration_label": label,
                "prepared_replicate": replicate,
                "prepared_accumulation": accumulation,
                "source_collection": str(match["master_source"]),
                "source_master_path": source_path,
                "source_master_column_index": source_column_index,
                "source_master_column_name": str(match["master_column_name"]),
                "source_scan_id": source_scan_id,
                "source_date": str(match["master_date"]),
                "source_setting": str(match["master_setting"]),
                "source_replicate": source_replicate,
                "intensity_max_abs_difference": float(
                    match["intensity_max_abs_difference"]
                ),
                "axis_max_abs_difference": float(match["axis_max_abs_difference"]),
                "axis_match_1e-5": bool(match["axis_match_1e-5"]),
                "concentration_agrees": bool(match["concentration_agrees"]),
                "expected_calibration_date": EXPECTED_DATE,
                "expected_calibration_setting": EXPECTED_SETTING,
                "date_matches_expected": date_matches,
                "setting_matches_expected": setting_matches,
                "lineage_class": lineage_class,
                "scientific_status": scientific_status,
            }
        )

    lineage = pd.DataFrame(rows).sort_values("manifest_order").reset_index(drop=True)
    reuse_counts = lineage["source_scan_id"].value_counts()
    first_prepared = (
        lineage.sort_values("manifest_order")
        .drop_duplicates("source_scan_id")
        .set_index("source_scan_id")["prepared_file"]
    )
    lineage["source_reuse_count"] = lineage["source_scan_id"].map(reuse_counts).astype(int)
    lineage["source_scan_first_prepared_file"] = lineage["source_scan_id"].map(
        first_prepared
    )
    lineage["source_scan_is_reused"] = lineage["source_reuse_count"].gt(1)
    lineage["statistical_independence_status"] = np.where(
        lineage["source_scan_is_reused"],
        "not_independent_exact_source_scan_reused",
        "no_exact_reuse_detected_within_prepared_set",
    )

    sample_count = int(lineage["sample_type"].eq("sample").sum())
    blank_count = int(lineage["sample_type"].eq("blank").sum())
    if (sample_count, blank_count) != (EXPECTED_SAMPLE_ROWS, EXPECTED_BLANK_ROWS):
        raise CalibrationAuditError(
            f"Expected {EXPECTED_SAMPLE_ROWS} samples and {EXPECTED_BLANK_ROWS} blanks; "
            f"found {sample_count} and {blank_count}."
        )
    if lineage["source_scan_id"].nunique() != EXPECTED_UNIQUE_SOURCE_SCANS:
        raise CalibrationAuditError(
            "The number of unique master source scans changed; the prepared-set reuse "
            "assessment must be reviewed."
        )
    return lineage


def build_reuse_table(lineage: pd.DataFrame) -> pd.DataFrame:
    reused = lineage[lineage["source_scan_is_reused"]].copy()
    columns = [
        "source_scan_id",
        "source_master_path",
        "source_master_column_index",
        "source_date",
        "source_setting",
        "concentration_M",
        "concentration_label",
        "source_reuse_count",
        "prepared_file",
        "prepared_replicate",
        "prepared_accumulation",
        "source_scan_first_prepared_file",
        "statistical_independence_status",
    ]
    return reused[columns].sort_values(
        ["source_scan_id", "prepared_file"], kind="stable"
    ).reset_index(drop=True)


def build_replay_manifest(lineage: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "file": lineage["prepared_file"],
            "record_group": "calibration_curve_historical_replay",
            "sample_type": lineage["sample_type"],
            "concentration_molar": lineage["concentration_M"],
            "concentration_label": lineage["concentration_label"],
            "replicate": lineage["prepared_replicate"],
            "accumulation": lineage["prepared_accumulation"],
            "instrument": "portable_raman",
            "acquisition": lineage["source_setting"],
            "analyte": "4atp",
            "matrix": "dry_4atp_calibration",
            "provenance_status": lineage["scientific_status"],
            "source_master_path": lineage["source_master_path"],
            "source_master_column_index": lineage["source_master_column_index"],
            "source_date": lineage["source_date"],
            "source_setting": lineage["source_setting"],
            "source_scan_id": lineage["source_scan_id"],
            "source_reuse_count": lineage["source_reuse_count"],
        }
    )


def _historical_generator_contract() -> dict[str, Any]:
    inventory = pd.read_csv(LEGACY_SCRIPT_INVENTORY)
    selected = inventory[
        inventory["relative_path"].eq(HISTORICAL_GENERATOR_PATH)
    ]
    if len(selected) != 1:
        raise CalibrationAuditError(
            "Historical calibration generator is absent or duplicated in "
            "legacy_script_inventory.csv."
        )
    row = selected.iloc[0]
    if str(row["sha256"]) != HISTORICAL_GENERATOR_SHA256:
        raise CalibrationAuditError(
            "Historical calibration generator hash differs from the forensic "
            "audit contract."
        )
    return {
        "inventory": "../../metadata/legacy_script_inventory.csv",
        "archive_relative_path": HISTORICAL_GENERATOR_PATH,
        "sha256": HISTORICAL_GENERATOR_SHA256,
        "repository_status": str(row["status"]),
        "distribution_note": (
            "The historical script is inventoried but not distributed because "
            "it contains private absolute paths. The recovered portable recipe "
            "is implemented by scripts/audit_calibration_curve.py."
        ),
    }


def build_replay_config() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "analysis_id": "calibration_curve_historical_replay",
        "purpose": (
            "Computational replay and sensitivity audit only; not a corrected "
            "low-power calibration."
        ),
        "manifest": "calibration_curve_historical_replay_manifest.csv",
        "publication_snapshot": (
            "../../data/published_snapshot/calibration_curve/"
            "final_spectra_by_accumulation_wide.csv"
        ),
        "historical_generator": _historical_generator_contract(),
        "expected_scientific_context": {
            "date": EXPECTED_DATE,
            "setting": EXPECTED_SETTING,
            "blank_material": "AuAgBC without 4-ATP",
        },
        "recovered_historical_processing": {
            "grid_order": "align_all_then_crop",
            "grid_mode": "intersection",
            "grid_step": "median_of_native_median_steps",
            "crop_min_cm-1": X_MIN_CM1,
            "baseline": {
                "method": "iarpls",
                "lambda": BASELINE_LAMBDA,
                "diff_order": 2,
                "max_iter": 50,
                "tol": 0.001,
            },
            "filter": {
                "method": "fft_selected_butterworth",
                "percentile": FILTER_PERCENTILE,
                "order": FILTER_ORDER,
                "selection": (
                    "legacy_argmin_with_hash_bound_committed_fft_index_and_"
                    "normalized_cutoff_lock; fresh_peak_membership_is_diagnostic_only"
                ),
            },
            "second_baseline": {
                "method": "iarpls",
                "lambda": SECOND_BASELINE_LAMBDA,
                "diff_order": 2,
                "max_iter": 50,
                "tol": 0.001,
            },
            "blank": {
                "stage": "after_second_baseline",
                "historical_strategy": "mean_of_all_15_prepared_blank_scans",
                "warning": (
                    "All 15 historical blank scans are high-power, later-session "
                    "measurements and are not a valid low-power calibration blank."
                ),
            },
            "post_blank_baseline": {
                "method": "asls",
                "lambda": POST_BASELINE_LAMBDA,
                "p": POST_BASELINE_P,
                "diff_order": 2,
                "max_iter": 50,
                "tol": 0.001,
            },
            "peaks": [
                {"center_cm-1": center, "half_window_cm-1": window, "method": "height"}
                for center, window in PEAKS
            ],
        },
        "recovered_historical_models": {
            "aggregation": (
                "mean of five accumulation peak heights within each prepared "
                "replicate, followed by mean and sample SD (ddof=1) across the "
                "three prepared replicate means"
            ),
            "linear": {
                "equation": "Y = slope * log10(C_M) + intercept",
                "fit": "unweighted ordinary least squares",
            },
            "exponential": {
                "equation": "Y = Y0 * exp(k * log10(C_M))",
                "fit": "unweighted nonlinear least squares with Y0 >= 0",
                "historical_optimizer": (
                    "single recovered initializer; audit sensitivities use "
                    "deterministic multistart and report when the historical "
                    "initializer enters a poorer local solution"
                ),
            },
            "blank_sigma": (
                "sample SD (ddof=1) of 15 pooled scan/accumulation-level "
                "processed blank peak heights from three later, non-context-"
                "matched exports; not independent blank preparations"
            ),
            "historical_thresholds": {
                "LOD": "3 * blank_sigma",
                "LOQ": "10 * blank_sigma",
                "warning": (
                    "The recovered script omits blank mean; the manuscript "
                    "describes blank mean plus 3 or 10 SD. Samples undergo "
                    "blank subtraction before the final baseline, while blank "
                    "threshold spectra do not, so the inversion is diagnostic "
                    "rather than an analytical LOD/LOQ."
                ),
            },
        },
        "verification_tolerances": {
            "processed_intensity_max_abs": REPLAY_ABSOLUTE_TOLERANCE,
            "rounded_table_axis_max_abs_cm-1": AXIS_ABSOLUTE_TOLERANCE,
            "diagnostic_fit_relative": DIAGNOSTIC_FIT_RELATIVE_TOLERANCE,
            "diagnostic_fit_absolute": CHECK_NUMERIC_ABSOLUTE_TOLERANCE,
            "diagnostic_fit_relative_columns": {
                "calibration_model_sensitivity.csv": list(
                    MODEL_DIAGNOSTIC_RELATIVE_COLUMNS
                ),
                "calibration_parameter_comparison.csv": list(
                    PARAMETER_DIAGNOSTIC_RELATIVE_COLUMNS
                ),
            },
            "exact_numeric_columns": {
                "calibration_model_sensitivity.csv": list(
                    MODEL_EXACT_NUMERIC_COLUMNS
                ),
                "calibration_parameter_comparison.csv": list(
                    PARAMETER_EXACT_NUMERIC_COLUMNS
                ),
            },
        },
    }


def _read_single_scan(path: Path) -> tuple[np.ndarray, np.ndarray]:
    frame = pd.read_csv(path)
    if frame.shape[1] < 2:
        raise CalibrationAuditError(f"Spectrum has fewer than two columns: {path}")
    x = pd.to_numeric(frame.iloc[:, 0], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(frame.iloc[:, 1], errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    x, y = x[valid], y[valid]
    if len(x) < 10:
        raise CalibrationAuditError(f"Spectrum has too few numerical rows: {path}")
    if x[1] < x[0]:
        x, y = x[::-1], y[::-1]
    return x, y


def _legacy_common_grid(records: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    axes: list[np.ndarray] = []
    signals: list[np.ndarray] = []
    steps: list[float] = []
    for relative in records["prepared_file"]:
        x, y = _read_single_scan(REPOSITORY_ROOT / Path(str(relative)))
        axes.append(x)
        signals.append(y)
        if len(x) > 2:
            steps.append(float(np.median(np.diff(x))))
    lower = max(float(x.min()) for x in axes)
    upper = min(float(x.max()) for x in axes)
    if lower >= upper:
        raise CalibrationAuditError("Calibration spectra have no common Raman-shift range.")
    step = float(np.median(np.asarray(steps, dtype=float)))
    points = int((upper - lower) / step) + 1
    x_common = np.linspace(lower, upper, points)
    aligned = np.vstack(
        [np.interp(x_common, x, y) for x, y in zip(axes, signals)]
    )
    keep = x_common >= X_MIN_CM1
    x_common = x_common[keep]
    aligned = aligned[:, keep]
    if len(x_common) != EXPECTED_GRID_POINTS:
        raise CalibrationAuditError(
            f"Expected {EXPECTED_GRID_POINTS} replay grid points; found {len(x_common)}."
        )
    return x_common, aligned


def _load_fft_locks() -> pd.DataFrame | None:
    if not FFT_LOCK_OUTPUT.is_file():
        return None
    locks = pd.read_csv(FFT_LOCK_OUTPUT)
    required = {
        "prepared_file",
        "prepared_sha256",
        "spectrum_points_after_alignment",
        "positive_frequency_max_index",
        "fft_peak_index",
        "normalized_cutoff",
    }
    missing = sorted(required.difference(locks.columns))
    if missing:
        raise CalibrationAuditError(
            f"FFT lock is missing columns: {', '.join(missing)}."
        )
    if locks["prepared_file"].duplicated().any():
        duplicate = str(
            locks.loc[locks["prepared_file"].duplicated(), "prepared_file"].iloc[0]
        )
        raise CalibrationAuditError(f"FFT lock contains duplicate row: {duplicate}.")
    return locks


def _preprocess_one(
    x: np.ndarray,
    y: np.ndarray,
    *,
    locked_fft_index: int | None,
    locked_normalized_cutoff: float | None,
) -> tuple[np.ndarray, int, float, int, bool]:
    baseline, _ = whittaker.iarpls(
        y,
        lam=BASELINE_LAMBDA,
        diff_order=2,
        max_iter=50,
        tol=0.001,
    )
    first_corrected = y - baseline
    count = len(first_corrected)
    spectrum_fft = fft(first_corrected, count)
    frequencies = np.abs(
        fftfreq(count, d=(x[1] - x[0]) * 1e-2)[: count // 2]
    )
    magnitude = np.abs(spectrum_fft[: count // 2])
    peak_indices, _ = find_peaks(magnitude)
    current_peaks = set(int(value) for value in peak_indices)
    if locked_fft_index is not None:
        if locked_normalized_cutoff is None:
            raise CalibrationAuditError("Locked FFT index has no locked cutoff.")
        selected_fft_index = int(locked_fft_index)
        positive_frequency_max_index = len(frequencies) - 1
        if not 0 < selected_fft_index < positive_frequency_max_index:
            raise CalibrationAuditError(
                "Locked FFT index is outside the strict positive-frequency "
                f"interior: {selected_fft_index}."
            )
        cutoff = float(locked_normalized_cutoff)
        if not math.isfinite(cutoff) or not 0.0 < cutoff < 1.0:
            raise CalibrationAuditError(
                f"Locked FFT cutoff must be finite and strictly between 0 and 1: {cutoff}."
            )
        expected_cutoff = float(
            np.clip(
                selected_fft_index / positive_frequency_max_index,
                1e-4,
                0.999,
            )
        )
        if not math.isclose(
            cutoff,
            expected_cutoff,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise CalibrationAuditError(
                "Locked FFT index and cutoff are inconsistent: "
                f"index={selected_fft_index}, cutoff={cutoff}, "
                f"expected={expected_cutoff}."
            )
        locked_index_is_current_peak = selected_fft_index in current_peaks
    elif peak_indices.size == 0:
        filtered = first_corrected
        selected_fft_index = -1
        cutoff = math.nan
        locked_index_is_current_peak = False
    else:
        threshold = np.percentile(magnitude[peak_indices], FILTER_PERCENTILE)
        selected_position = int(
            np.argmin(np.abs(magnitude[peak_indices] - threshold))
        )
        selected_fft_index = int(peak_indices[selected_position])
        maximum_frequency = float(np.max(frequencies))
        cutoff = (
            float(frequencies[selected_fft_index]) / maximum_frequency
            if maximum_frequency > 0
            else 0.1
        )
        cutoff = float(np.clip(cutoff, 1e-4, 0.999))
        locked_index_is_current_peak = True

    if selected_fft_index >= 0:
        numerator, denominator = butter(
            N=FILTER_ORDER,
            Wn=cutoff,
            btype="low",
        )
        filtered = filtfilt(numerator, denominator, first_corrected)
    second_baseline, _ = whittaker.iarpls(
        filtered,
        lam=SECOND_BASELINE_LAMBDA,
        diff_order=2,
        max_iter=50,
        tol=0.001,
    )
    return (
        filtered - second_baseline,
        selected_fft_index,
        cutoff,
        count,
        locked_index_is_current_peak,
    )


def _post_baseline(y: np.ndarray) -> np.ndarray:
    baseline, _ = whittaker.asls(
        y,
        lam=POST_BASELINE_LAMBDA,
        p=POST_BASELINE_P,
        diff_order=2,
        max_iter=50,
        tol=0.001,
    )
    return y - baseline


def replay_calibration(
    lineage: pd.DataFrame,
    *,
    require_lock: bool,
) -> Replay:
    x, aligned = _legacy_common_grid(lineage)
    existing_locks = _load_fft_locks()
    if require_lock and existing_locks is None:
        raise CalibrationAuditError(
            "The committed calibration FFT lock is required for --check."
        )
    lock_by_file: dict[str, Mapping[str, Any]] = {}
    if existing_locks is not None:
        lock_by_file = {
            str(row["prepared_file"]): row
            for row in existing_locks.to_dict(orient="records")
        }

    preprocessed: list[np.ndarray] = []
    lock_rows: list[dict[str, Any]] = []
    locked_fft_indices_currently_detected = 0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for index, row in lineage.iterrows():
            prepared_file = str(row["prepared_file"])
            locked = lock_by_file.get(prepared_file)
            if existing_locks is not None and locked is None:
                raise CalibrationAuditError(f"FFT lock is missing {prepared_file}.")
            if locked is not None and str(locked["prepared_sha256"]) != str(
                row["prepared_sha256"]
            ):
                raise CalibrationAuditError(
                    f"FFT lock source hash changed for {prepared_file}."
                )
            if locked is not None and int(
                locked["spectrum_points_after_alignment"]
            ) != len(x):
                raise CalibrationAuditError(
                    f"FFT lock grid-point count changed for {prepared_file}."
                )
            if locked is not None and int(
                locked["positive_frequency_max_index"]
            ) != len(x) // 2 - 1:
                raise CalibrationAuditError(
                    f"FFT lock positive-frequency bound changed for {prepared_file}."
                )
            result, fft_index, cutoff, points, current_peak = _preprocess_one(
                x,
                aligned[index],
                locked_fft_index=(
                    int(locked["fft_peak_index"]) if locked is not None else None
                ),
                locked_normalized_cutoff=(
                    float(locked["normalized_cutoff"])
                    if locked is not None
                    else None
                ),
            )
            if locked is not None and current_peak:
                locked_fft_indices_currently_detected += 1
            preprocessed.append(result)
            lock_rows.append(
                {
                    "prepared_file": prepared_file,
                    "prepared_sha256": row["prepared_sha256"],
                    "sample_type": row["sample_type"],
                    "source_setting": row["source_setting"],
                    "spectrum_points_after_alignment": points,
                    "positive_frequency_max_index": points // 2 - 1,
                    "fft_peak_index": fft_index,
                    "normalized_cutoff": cutoff,
                    "percentile": FILTER_PERCENTILE,
                    "butterworth_order": FILTER_ORDER,
                    "lock_basis": (
                        "recovered October 2025 historical calibration replay"
                    ),
                }
            )

    pre = np.vstack(preprocessed)
    blank_mask = lineage["sample_type"].eq("blank").to_numpy()
    sample_mask = ~blank_mask
    blank_groups = {
        "historical_mixed_15_blank_scans": np.where(blank_mask)[0],
        "wrong_context_blank_source_rep1_only": np.where(
            blank_mask & lineage["prepared_replicate"].eq(1).to_numpy()
        )[0],
        "wrong_context_blank_source_rep2_only": np.where(
            blank_mask & lineage["prepared_replicate"].eq(2).to_numpy()
        )[0],
        "wrong_context_blank_source_rep3_only": np.where(
            blank_mask & lineage["prepared_replicate"].eq(3).to_numpy()
        )[0],
        "no_blank_subtraction_counterfactual": np.asarray([], dtype=int),
    }
    final_by_strategy: dict[str, np.ndarray] = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        blank_final = np.vstack([_post_baseline(row) for row in pre[blank_mask]])
        for strategy, indices in blank_groups.items():
            if len(indices):
                blank_reference = np.mean(pre[indices], axis=0)
            else:
                blank_reference = np.zeros(pre.shape[1], dtype=float)
            final = np.empty_like(pre)
            sample_inputs = pre[sample_mask] - blank_reference
            final[sample_mask] = np.vstack(
                [_post_baseline(row) for row in sample_inputs]
            )
            final[blank_mask] = blank_final
            final_by_strategy[strategy] = final

    if (
        existing_locks is not None
        and locked_fft_indices_currently_detected != len(lineage)
    ):
        warnings.warn(
            "Fresh peak detection rediscovered "
            f"{locked_fft_indices_currently_detected}/{len(lineage)} locked FFT "
            "indices. This is diagnostic only; validated committed cutoffs remain "
            "authoritative.",
            RuntimeWarning,
            stacklevel=2,
        )

    return Replay(
        x=x,
        preprocessed=pre,
        final_by_blank_strategy=final_by_strategy,
        blank_indices_by_strategy=blank_groups,
        fft_locks=pd.DataFrame(lock_rows),
        fft_lock_current_peak_count=locked_fft_indices_currently_detected,
        records=lineage.copy(),
    )


def _peak_values(x: np.ndarray, spectra: np.ndarray) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for spectrum_index, y in enumerate(spectra):
        for center, half_window in PEAKS:
            mask = (x >= center - half_window) & (x <= center + half_window)
            if not np.any(mask):
                value = math.nan
                observed = math.nan
                points = 0
            else:
                local_y = y[mask]
                local_x = x[mask]
                selected = int(np.argmax(local_y))
                value = float(local_y[selected])
                observed = float(local_x[selected])
                points = int(mask.sum())
            rows.append(
                {
                    "spectrum_index": spectrum_index,
                    "peak_cm-1": center,
                    "half_window_cm-1": half_window,
                    "peak_value": value,
                    "observed_shift_cm-1": observed,
                    "window_points": points,
                }
            )
    return pd.DataFrame(rows)


def _scenario_scan_indices(
    lineage: pd.DataFrame,
    scenario: str,
) -> np.ndarray:
    samples = lineage["sample_type"].eq("sample")
    context = (
        lineage["setting_matches_expected"].astype(bool)
        & lineage["date_matches_expected"].astype(bool)
    )
    if scenario == "all_prepared_records":
        return np.where(samples.to_numpy())[0]
    if scenario == "context_uniform_concentrations":
        eligible: list[str] = []
        for label, group in lineage[samples].groupby("concentration_label", sort=False):
            if bool(
                (
                    group["setting_matches_expected"].astype(bool)
                    & group["date_matches_expected"].astype(bool)
                ).all()
            ):
                eligible.append(str(label))
        return np.where(
            (samples & lineage["concentration_label"].isin(eligible)).to_numpy()
        )[0]
    if scenario == "context_consistent_complete_replicates":
        eligible_pairs: set[tuple[str, int]] = set()
        sample_frame = lineage[samples]
        for (label, replicate), group in sample_frame.groupby(
            ["concentration_label", "prepared_replicate"], sort=False
        ):
            if len(group) == 5 and bool(
                (
                    group["setting_matches_expected"].astype(bool)
                    & group["date_matches_expected"].astype(bool)
                ).all()
            ):
                eligible_pairs.add((str(label), int(replicate)))
        selected = [
            index
            for index, row in lineage.iterrows()
            if row["sample_type"] == "sample"
            and (str(row["concentration_label"]), int(row["prepared_replicate"]))
            in eligible_pairs
        ]
        return np.asarray(selected, dtype=int)
    if scenario == "unique_source_scans_only":
        selected = (
            lineage[samples]
            .sort_values("manifest_order")
            .drop_duplicates("source_scan_id", keep="first")
            .index.to_numpy(dtype=int)
        )
        return selected
    raise CalibrationAuditError(f"Unknown sensitivity scenario: {scenario}")


def _aggregate_peak_for_fit(
    lineage: pd.DataFrame,
    peak_table: pd.DataFrame,
    *,
    peak_cm1: float,
    selected_indices: Sequence[int],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    selected = set(int(value) for value in selected_indices)
    peak = peak_table[
        peak_table["peak_cm-1"].eq(peak_cm1)
        & peak_table["spectrum_index"].isin(selected)
    ].copy()
    metadata = lineage[
        [
            "concentration_M",
            "concentration_label",
            "prepared_replicate",
        ]
    ].copy()
    metadata["spectrum_index"] = metadata.index
    peak = peak.merge(metadata, on="spectrum_index", how="left", validate="many_to_one")
    replicate = (
        peak.groupby(
            ["concentration_M", "concentration_label", "prepared_replicate"],
            sort=True,
            dropna=False,
        )["peak_value"]
        .agg(["mean", "std", "count"])
        .reset_index()
        .rename(
            columns={
                "mean": "replicate_peak_mean",
                "std": "replicate_peak_sd",
                "count": "n_scan_records",
            }
        )
    )
    concentration = (
        replicate.groupby(
            ["concentration_M", "concentration_label"],
            sort=True,
            dropna=False,
        )["replicate_peak_mean"]
        .agg(["mean", "std", "count"])
        .reset_index()
        .rename(
            columns={
                "mean": "intensity_mean",
                "std": "intensity_sd",
                "count": "n_replicates",
            }
        )
    )
    return replicate, concentration


def _fit_exponential(concentration: pd.DataFrame) -> dict[str, Any]:
    data = concentration[
        np.isfinite(concentration["concentration_M"])
        & np.isfinite(concentration["intensity_mean"])
        & concentration["concentration_M"].gt(0)
    ].sort_values("concentration_M")
    if len(data) < 3:
        raise CalibrationAuditError("Fewer than three concentration levels remain for fitting.")
    x = np.log10(data["concentration_M"].to_numpy(dtype=float))
    y = data["intensity_mean"].to_numpy(dtype=float)
    design = np.vstack([x, np.ones_like(x)]).T
    slope, _intercept = np.linalg.lstsq(design, y, rcond=None)[0]
    x0 = float(np.median(x))
    y0_at_center = float(np.interp(x0, x, y))
    b0 = slope / max(y0_at_center, 1e-9) if y0_at_center != 0 else 0.5
    a0 = y0_at_center / np.exp(b0 * x0) if np.isfinite(b0) else max(y)

    def model(value: np.ndarray, y0: float, k: float) -> np.ndarray:
        return y0 * np.exp(k * value)

    # Retain the recovered historical initializer as the first candidate, but
    # do not let a sensitivity scenario depend on that single starting point.
    # A context-filtered subset can be highly non-monotonic and the historical
    # initializer is demonstrably able to settle in a much poorer local
    # solution.  The additional deterministic starts all fit the same declared
    # model; the minimum-residual converged solution is retained.
    starting_k = (
        float(b0),
        -1.0,
        -0.5,
        -0.1,
        0.01,
        0.05,
        0.1,
        0.2,
        0.3,
        0.5,
        1.0,
        2.0,
        5.0,
    )
    candidates: list[dict[str, Any]] = []
    for candidate_number, initial_k in enumerate(starting_k):
        if candidate_number == 0:
            # Exact initializer recovered from the October 2025 script.
            initial_y0 = max(float(a0), 1e-9)
        else:
            with np.errstate(over="ignore", under="ignore", invalid="ignore"):
                basis = np.exp(initial_k * x)
            if np.isfinite(basis).all() and float(np.dot(basis, basis)) > 0:
                initial_y0 = max(
                    float(np.dot(y, basis) / np.dot(basis, basis)),
                    1e-9,
                )
            else:
                initial_y0 = max(float(a0), 1e-9)
        try:
            parameters, covariance = curve_fit(
                model,
                x,
                y,
                p0=(initial_y0, initial_k),
                bounds=([0.0, -np.inf], [np.inf, np.inf]),
                maxfev=100_000,
            )
        except (RuntimeError, ValueError, FloatingPointError):
            continue
        fitted_candidate = model(x, *parameters)
        residual_candidate = float(
            np.sum(np.square(y - fitted_candidate))
        )
        if not (
            np.isfinite(parameters).all()
            and np.isfinite(fitted_candidate).all()
            and math.isfinite(residual_candidate)
        ):
            continue
        candidates.append(
            {
                "candidate_number": candidate_number,
                "parameters": parameters,
                "covariance": covariance,
                "residual": residual_candidate,
            }
        )
    if not candidates:
        raise CalibrationAuditError("No exponential-model fit converged.")
    best = min(candidates, key=lambda candidate: candidate["residual"])
    legacy = next(
        (
            candidate
            for candidate in candidates
            if int(candidate["candidate_number"]) == 0
        ),
        None,
    )
    parameters = np.asarray(best["parameters"], dtype=float)
    covariance = np.asarray(best["covariance"], dtype=float)
    fitted = model(x, *parameters)
    residual = float(np.sum(np.square(y - fitted)))
    total = float(np.sum(np.square(y - np.mean(y))))
    r_squared = 1.0 - residual / total if total > 0 else math.nan
    standard_errors = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    y0_relative_se = float(
        standard_errors[0] / max(abs(float(parameters[0])), 1e-300)
    )
    k_relative_se = float(
        standard_errors[1] / max(abs(float(parameters[1])), 1e-300)
    )
    legacy_rss_ratio = (
        float(legacy["residual"]) / residual
        if legacy is not None and residual > 0
        else math.nan
    )
    if not math.isfinite(r_squared):
        fit_quality = "indeterminate_fit_quality"
    elif r_squared < 0.8:
        fit_quality = "poor_fit_r2_below_0_8"
    elif y0_relative_se > 1.0 or k_relative_se > 1.0:
        fit_quality = "high_formal_local_parameter_standard_error"
    else:
        fit_quality = "no_automatic_numerical_fit_warning"
    return {
        "Y0": float(parameters[0]),
        "k": float(parameters[1]),
        "R2": r_squared,
        "n_concentrations": int(len(data)),
        "concentration_min_M": float(data["concentration_M"].min()),
        "concentration_max_M": float(data["concentration_M"].max()),
        "concentration_span_decades": float(np.ptp(x)),
        "observed_intensity_min": float(np.min(y)),
        "observed_intensity_max": float(np.max(y)),
        "Y0_relative_standard_error": y0_relative_se,
        "k_relative_standard_error": k_relative_se,
        "fit_method": "deterministic_multistart_nonlinear_least_squares",
        "fit_status": "numerically_converged",
        "fit_quality_flag": fit_quality,
        "historical_initializer_solution_status": (
            "poorer_local_solution_avoided"
            if math.isfinite(legacy_rss_ratio) and legacy_rss_ratio > 1.01
            else "consistent_with_best_multistart_solution"
        ),
        "historical_initializer_rss_ratio_to_best": legacy_rss_ratio,
    }


def _inverse_exponential(threshold: float, y0: float, k: float) -> float:
    if (
        not math.isfinite(threshold)
        or threshold <= 0
        or not math.isfinite(y0)
        or y0 <= 0
        or not math.isfinite(k)
        or k == 0
    ):
        return math.nan
    exponent = (math.log(threshold) - math.log(y0)) / k
    return float(10.0**exponent)


def build_model_sensitivity(
    replay: Replay,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    historical_strategy = "historical_mixed_15_blank_scans"
    scenarios = (
        "all_prepared_records",
        "context_uniform_concentrations",
        "context_consistent_complete_replicates",
        "unique_source_scans_only",
    )
    rows: list[dict[str, Any]] = []
    blank_statistics_rows: list[dict[str, Any]] = []

    peak_tables = {
        strategy: _peak_values(replay.x, spectra)
        for strategy, spectra in replay.final_by_blank_strategy.items()
    }
    for strategy, peak_table in peak_tables.items():
        blank_indices = replay.blank_indices_by_strategy[strategy]
        for peak_cm1, _window in PEAKS:
            group = peak_table[
                peak_table["spectrum_index"].isin(blank_indices)
                & peak_table["peak_cm-1"].eq(peak_cm1)
            ]
            values = group["peak_value"].to_numpy(dtype=float)
            blank_statistics_rows.append(
                {
                    "blank_strategy": strategy,
                    "peak_cm-1": float(peak_cm1),
                    "blank_peak_mean": (
                        float(np.mean(values)) if len(values) else math.nan
                    ),
                    "blank_peak_sd": (
                        float(np.std(values, ddof=1))
                        if len(values) >= 2
                        else math.nan
                    ),
                    "n_blank_scans": int(len(values)),
                }
            )
    blank_statistics = pd.DataFrame(blank_statistics_rows)

    scenario_strategy_pairs = [
        (scenario, historical_strategy) for scenario in scenarios
    ] + [
        ("all_prepared_records", strategy)
        for strategy in replay.final_by_blank_strategy
        if strategy != historical_strategy
    ]
    for scenario, strategy in scenario_strategy_pairs:
        indices = _scenario_scan_indices(replay.records, scenario)
        peak_table = peak_tables[strategy]
        for peak_cm1, _window in PEAKS:
            replicate, concentration = _aggregate_peak_for_fit(
                replay.records,
                peak_table,
                peak_cm1=peak_cm1,
                selected_indices=indices,
            )
            fit = _fit_exponential(concentration)
            blank_row = blank_statistics[
                blank_statistics["blank_strategy"].eq(strategy)
                & blank_statistics["peak_cm-1"].eq(peak_cm1)
            ].iloc[0]
            blank_mean = float(blank_row["blank_peak_mean"])
            blank_sd = float(blank_row["blank_peak_sd"])
            mean_plus_3sd = blank_mean + 3.0 * blank_sd
            mean_plus_10sd = blank_mean + 10.0 * blank_sd
            lod_mean_plus_3sd = _inverse_exponential(
                mean_plus_3sd, fit["Y0"], fit["k"]
            )
            loq_mean_plus_10sd = _inverse_exponential(
                mean_plus_10sd, fit["Y0"], fit["k"]
            )
            minimum_concentration = float(fit["concentration_min_M"])
            maximum_concentration = float(fit["concentration_max_M"])
            rows.append(
                {
                    "record_selection_scenario": scenario,
                    "blank_strategy": strategy,
                    "peak_cm-1": peak_cm1,
                    "n_scan_records": int(
                        replicate["n_scan_records"].sum()
                    ),
                    "n_nominal_prepared_replicate_groups": int(len(replicate)),
                    "n_concentrations": int(fit["n_concentrations"]),
                    "Y0": fit["Y0"],
                    "k": fit["k"],
                    "R2": fit["R2"],
                    "concentration_min_M": minimum_concentration,
                    "concentration_max_M": maximum_concentration,
                    "concentration_span_decades": fit[
                        "concentration_span_decades"
                    ],
                    "observed_intensity_min": fit["observed_intensity_min"],
                    "observed_intensity_max": fit["observed_intensity_max"],
                    "Y0_formal_local_relative_standard_error": fit[
                        "Y0_relative_standard_error"
                    ],
                    "k_formal_local_relative_standard_error": fit[
                        "k_relative_standard_error"
                    ],
                    "fit_method": fit["fit_method"],
                    "fit_status": fit["fit_status"],
                    "fit_quality_flag": fit["fit_quality_flag"],
                    "fit_interpretation_scope": (
                        "numerical_diagnostic_only_not_experimental_uncertainty_"
                        "or_scientific_validity"
                    ),
                    "historical_initializer_solution_status": fit[
                        "historical_initializer_solution_status"
                    ],
                    "historical_initializer_rss_ratio_to_best": fit[
                        "historical_initializer_rss_ratio_to_best"
                    ],
                    "blank_peak_mean": blank_mean,
                    "blank_peak_sd": blank_sd,
                    "n_blank_scans": int(blank_row["n_blank_scans"]),
                    "LOD_mean_plus_3sd_M": lod_mean_plus_3sd,
                    "LOQ_mean_plus_10sd_M": loq_mean_plus_10sd,
                    "LOD_within_fitted_concentration_range": bool(
                        math.isfinite(lod_mean_plus_3sd)
                        and minimum_concentration
                        <= lod_mean_plus_3sd
                        <= maximum_concentration
                    ),
                    "LOQ_within_fitted_concentration_range": bool(
                        math.isfinite(loq_mean_plus_10sd)
                        and minimum_concentration
                        <= loq_mean_plus_10sd
                        <= maximum_concentration
                    ),
                    "LOD_legacy_3sd_only_M": _inverse_exponential(
                        3.0 * blank_sd, fit["Y0"], fit["k"]
                    ),
                    "LOQ_legacy_10sd_only_M": _inverse_exponential(
                        10.0 * blank_sd, fit["Y0"], fit["k"]
                    ),
                    "lod_loq_reporting_status": (
                        "not_reportable_missing_context_matched_low_power_blank"
                    ),
                    "scientific_interpretation": (
                        "computational sensitivity only; no valid context-matched "
                        "low-power blank is available"
                    ),
                }
            )
    return (
        pd.DataFrame(rows).sort_values(
            ["record_selection_scenario", "blank_strategy", "peak_cm-1"],
            kind="stable",
        ),
        blank_statistics.sort_values(["blank_strategy", "peak_cm-1"], kind="stable"),
    )


def _wide_column(row: Mapping[str, Any]) -> str:
    label = str(row["concentration_label"]).replace("µ", "u").replace("μ", "u")
    label = label.replace(" ", "")
    suffix = "blank" if str(row["sample_type"]) == "blank" else "sample"
    return (
        f"{label}__rep{int(row['prepared_replicate'])}"
        f"__acc{int(row['prepared_accumulation'])}__{suffix}"
    )


def build_replay_metrics(replay: Replay) -> pd.DataFrame:
    historical = pd.read_csv(PUBLISHED_WIDE)
    generated = replay.final_by_blank_strategy["historical_mixed_15_blank_scans"]
    if historical.shape != (EXPECTED_GRID_POINTS, EXPECTED_ROWS + 1):
        raise CalibrationAuditError(
            f"Unexpected publication-wide shape: {historical.shape}."
        )
    axis_difference = np.abs(
        historical.iloc[:, 0].to_numpy(dtype=float) - replay.x
    )
    axis_max = float(np.max(axis_difference))
    rows: list[dict[str, Any]] = []
    for index, record in replay.records.iterrows():
        column = _wide_column(record)
        if column not in historical.columns:
            raise CalibrationAuditError(f"Publication snapshot lacks column {column}.")
        expected = historical[column].to_numpy(dtype=float)
        observed = generated[index]
        difference = observed - expected
        rows.append(
            {
                "publication_column": column,
                "prepared_file": record["prepared_file"],
                "prepared_sha256": record["prepared_sha256"],
                "sample_type": record["sample_type"],
                "concentration_M": record["concentration_M"],
                "concentration_label": record["concentration_label"],
                "replicate": record["prepared_replicate"],
                "accumulation": record["prepared_accumulation"],
                "source_date": record["source_date"],
                "source_setting": record["source_setting"],
                "source_scan_id": record["source_scan_id"],
                "points": len(observed),
                "axis_max_abs_difference_cm-1": axis_max,
                "rmse": float(np.sqrt(np.mean(np.square(difference)))),
                "mean_signed_difference": float(np.mean(difference)),
                "max_abs_difference": float(np.max(np.abs(difference))),
                "pearson_r": float(np.corrcoef(observed, expected)[0, 1]),
                "passes_cross_environment_tolerance": bool(
                    axis_max <= AXIS_ABSOLUTE_TOLERANCE
                    and np.max(np.abs(difference)) <= REPLAY_ABSOLUTE_TOLERANCE
                ),
            }
        )
    metrics = pd.DataFrame(rows)
    if not metrics["passes_cross_environment_tolerance"].all():
        failed = metrics[~metrics["passes_cross_environment_tolerance"]]
        raise CalibrationAuditError(
            f"{len(failed)} replayed spectra exceed the declared tolerance."
        )
    return metrics


def _spectral_aggregates(
    replay: Replay,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    final = replay.final_by_blank_strategy["historical_mixed_15_blank_scans"]
    replicate_rows: list[dict[str, Any]] = []
    concentration_rows: list[dict[str, Any]] = []
    records = replay.records
    for (
        sample_type,
        concentration,
        label,
        replicate,
    ), group in records.groupby(
        [
            "sample_type",
            "concentration_M",
            "concentration_label",
            "prepared_replicate",
        ],
        sort=True,
        dropna=False,
    ):
        indices = group.index.to_numpy(dtype=int)
        stack = final[indices]
        mean = np.mean(stack, axis=0)
        sd = np.std(stack, axis=0, ddof=1)
        for position, x_value in enumerate(replay.x):
            replicate_rows.append(
                {
                    "type": sample_type,
                    "concentration_M": float(concentration),
                    "concentration_label": label,
                    "replicate": int(replicate),
                    "Raman_shift_cm-1": x_value,
                    "intensity_mean": mean[position],
                    "intensity_sd": sd[position],
                    "n_accumulations": len(indices),
                }
            )
    replicate_frame = pd.DataFrame(replicate_rows)
    for (
        sample_type,
        concentration,
        label,
    ), group in replicate_frame.groupby(
        ["type", "concentration_M", "concentration_label"],
        sort=True,
        dropna=False,
    ):
        pivot = group.pivot(
            index="Raman_shift_cm-1",
            columns="replicate",
            values="intensity_mean",
        ).sort_index()
        stack = pivot.to_numpy(dtype=float).T
        mean = np.mean(stack, axis=0)
        sd = np.std(stack, axis=0, ddof=1)
        cv = np.divide(
            100.0 * sd,
            mean,
            out=np.full_like(mean, np.nan),
            where=mean != 0,
        )
        for position, x_value in enumerate(pivot.index.to_numpy(dtype=float)):
            concentration_rows.append(
                {
                    "type": sample_type,
                    "concentration_M": float(concentration),
                    "concentration_label": label,
                    "Raman_shift_cm-1": x_value,
                    "intensity_mean_of_replicate_means": mean[position],
                    "intensity_sd_across_replicates": sd[position],
                    "n_replicates": stack.shape[0],
                    "cv_percent": cv[position],
                }
            )
    return replicate_frame, pd.DataFrame(concentration_rows)


def _numeric_metric(
    dataset: str,
    expected: np.ndarray,
    observed: np.ndarray,
    *,
    tolerance: float,
    note: str,
) -> dict[str, Any]:
    expected = np.asarray(expected, dtype=float)
    observed = np.asarray(observed, dtype=float)
    valid = np.isfinite(expected) & np.isfinite(observed)
    if not np.any(valid):
        raise CalibrationAuditError(f"No comparable numerical values for {dataset}.")
    difference = observed[valid] - expected[valid]
    maximum = float(np.max(np.abs(difference)))
    return {
        "dataset": dataset,
        "compared_numeric_cells": int(valid.sum()),
        "rmse": float(np.sqrt(np.mean(np.square(difference)))),
        "max_abs_difference": maximum,
        "absolute_tolerance": tolerance,
        "passes": bool(maximum <= tolerance),
        "note": note,
    }


def build_table_metrics(replay: Replay) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    replicate, concentration = _spectral_aggregates(replay)

    published_replicate = pd.read_csv(PUBLISHED_REPLICATE)
    # The historical CSV serialises the common axis through pandas, while the
    # replay retains the original float64 values.  Eight decimals are far
    # tighter than the publication table's five-decimal axis and avoid using
    # binary floating-point values as relational keys.
    published_replicate["_axis_key"] = np.round(
        published_replicate["Raman_shift_cm-1"].to_numpy(dtype=float), 8
    )
    replicate["_axis_key"] = np.round(
        replicate["Raman_shift_cm-1"].to_numpy(dtype=float), 8
    )
    keys = ["type", "concentration_M", "replicate", "_axis_key"]
    merged_replicate = published_replicate.merge(
        replicate,
        on=keys,
        how="inner",
        suffixes=("_published", "_replayed"),
        validate="one_to_one",
    )
    if len(merged_replicate) != len(published_replicate):
        raise CalibrationAuditError("Replicate-spectrum replay keys do not fully match.")
    rows.append(
        _numeric_metric(
            "replicate_mean_sd_by_shift.csv",
            merged_replicate[
                ["intensity_mean_published", "intensity_sd_published"]
            ].to_numpy(),
            merged_replicate[
                ["intensity_mean_replayed", "intensity_sd_replayed"]
            ].to_numpy(),
            tolerance=REPLAY_ABSOLUTE_TOLERANCE,
            note="Compares intensity mean and SD; mojibake labels are ignored as historical text.",
        )
    )

    historical_wide = pd.read_csv(PUBLISHED_WIDE)
    generated = replay.final_by_blank_strategy["historical_mixed_15_blank_scans"]
    expected_wide = historical_wide.iloc[:, 1:].to_numpy(dtype=float).T
    rows.append(
        _numeric_metric(
            "final_spectra_by_accumulation_wide.csv",
            expected_wide,
            generated,
            tolerance=REPLAY_ABSOLUTE_TOLERANCE,
            note="All 210 processed scan channels on the recovered 416-point axis.",
        )
    )

    peak_table = _peak_values(replay.x, generated)
    summary_rows: list[dict[str, Any]] = []
    for peak_cm1, _window in PEAKS:
        selected = np.arange(len(replay.records), dtype=int)
        replicate_peak, concentration_peak = _aggregate_peak_for_fit(
            replay.records,
            peak_table,
            peak_cm1=peak_cm1,
            selected_indices=selected,
        )
        del replicate_peak
        for row in concentration_peak.to_dict(orient="records"):
            summary_rows.append(
                {
                    "type": (
                        "blank"
                        if float(row["concentration_M"]) == 0.0
                        else "sample"
                    ),
                    "concentration_M": float(row["concentration_M"]),
                    "peak_cm-1": peak_cm1,
                    "mean": float(row["intensity_mean"]),
                    "std": float(row["intensity_sd"]),
                    "count": int(row["n_replicates"]),
                    "cv_percent": (
                        100.0
                        * float(row["intensity_sd"])
                        / float(row["intensity_mean"])
                        if float(row["intensity_mean"]) != 0
                        else math.nan
                    ),
                }
            )
    replayed_summary = pd.DataFrame(summary_rows)
    published_summary = pd.read_csv(PUBLISHED_SUMMARY)
    expected_values: list[float] = []
    observed_values: list[float] = []
    for published_row in published_summary.to_dict(orient="records"):
        for center, _window in PEAKS:
            matched = replayed_summary[
                replayed_summary["type"].eq(published_row["type"])
                & np.isclose(
                    replayed_summary["concentration_M"],
                    float(published_row["concentration_M"]),
                    rtol=0,
                    atol=1e-30,
                )
                & replayed_summary["peak_cm-1"].eq(center)
            ]
            if len(matched) != 1:
                raise CalibrationAuditError(
                    "Could not match a replayed concentration peak to the published summary."
                )
            replayed = matched.iloc[0]
            prefix = f"peak_{center:g}_height"
            expected_values.extend(
                [
                    float(published_row[f"{prefix}_mean"]),
                    float(published_row[f"{prefix}_std"]),
                    float(published_row[f"{prefix}_cv_percent"]),
                ]
            )
            observed_values.extend(
                [
                    float(replayed["mean"]),
                    float(replayed["std"]),
                    float(replayed["cv_percent"]),
                ]
            )
    rows.append(
        _numeric_metric(
            "summary_by_concentration.csv",
            np.asarray(expected_values),
            np.asarray(observed_values),
            tolerance=REPLAY_ABSOLUTE_TOLERANCE,
            note="Compares peak mean, SD, and CV for all 14 precision entries.",
        )
    )

    selected = pd.read_csv(PUBLISHED_SELECTED, header=None)
    selected_axis = pd.to_numeric(selected.iloc[:, 0], errors="coerce")
    selected = selected[selected_axis.notna()].copy()
    selected_numeric = selected.apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    order = [
        ("sample", value)
        for value in sorted(CONCENTRATION_LABELS, reverse=True)
    ] + [("blank", 0.0)]
    generated_columns: list[np.ndarray] = [replay.x]
    for sample_type, concentration_value in order:
        group = concentration[
            concentration["type"].eq(sample_type)
            & np.isclose(
                concentration["concentration_M"],
                concentration_value,
                rtol=0,
                atol=1e-30,
            )
        ].sort_values("Raman_shift_cm-1")
        if len(group) != EXPECTED_GRID_POINTS:
            raise CalibrationAuditError(
                f"Missing concentration-level spectrum for {sample_type} {concentration_value}."
            )
        generated_columns.extend(
            [
                group["intensity_mean_of_replicate_means"].to_numpy(dtype=float),
                group["intensity_sd_across_replicates"].to_numpy(dtype=float),
                group["cv_percent"].to_numpy(dtype=float),
            ]
        )
    generated_selected = np.column_stack(generated_columns)
    if selected_numeric.shape != generated_selected.shape:
        raise CalibrationAuditError(
            "The selected-shift publication table shape does not match its replay."
        )
    rows.append(
        _numeric_metric(
            "calibration_at_selected_shifts.csv:axis",
            selected_numeric[:, 0],
            generated_selected[:, 0],
            tolerance=AXIS_ABSOLUTE_TOLERANCE,
            note="The historical spreadsheet rounds Raman shift to five decimals.",
        )
    )
    signal_columns = [
        index
        for index in range(1, selected_numeric.shape[1])
        if (index - 1) % 3 in {0, 1}
    ]
    cv_columns = [
        index
        for index in range(1, selected_numeric.shape[1])
        if (index - 1) % 3 == 2
    ]
    rows.append(
        _numeric_metric(
            "calibration_at_selected_shifts.csv:intensity_and_sd",
            selected_numeric[:, signal_columns],
            generated_selected[:, signal_columns],
            tolerance=REPLAY_ABSOLUTE_TOLERANCE,
            note=(
                "Compares concentration-level intensity mean and SD; legacy "
                "header-label errors are outside the numerical check."
            ),
        )
    )
    rows.append(
        _numeric_metric(
            "calibration_at_selected_shifts.csv:cv",
            selected_numeric[:, cv_columns],
            generated_selected[:, cv_columns],
            tolerance=0.05,
            note=(
                "CV is a ratio and amplifies the cross-environment baseline drift "
                "where the replayed mean is near zero."
            ),
        )
    )

    metrics = pd.DataFrame(rows)
    if not metrics["passes"].all():
        failed = metrics[~metrics["passes"]]
        raise CalibrationAuditError(
            f"{len(failed)} publication tables exceed replay tolerance: "
            + "; ".join(
                f"{row['dataset']} max_abs={float(row['max_abs_difference']):.9g}"
                for row in failed.to_dict(orient="records")
            )
        )
    return metrics


def build_parameter_comparison(model_sensitivity: pd.DataFrame) -> pd.DataFrame:
    paper = pd.read_csv(PAPER_PARAMETERS)
    historical = model_sensitivity[
        model_sensitivity["record_selection_scenario"].eq("all_prepared_records")
        & model_sensitivity["blank_strategy"].eq(
            "historical_mixed_15_blank_scans"
        )
    ].copy()
    rows: list[dict[str, Any]] = []
    for paper_row in paper.to_dict(orient="records"):
        shift = float(paper_row["shift_cm-1"])
        recovered = historical.iloc[
            int(
                np.argmin(
                    np.abs(
                        historical["peak_cm-1"].to_numpy(dtype=float) - shift
                    )
                )
            )
        ]
        rows.append(
            {
                "paper_shift_cm-1": shift,
                "replayed_peak_cm-1": float(recovered["peak_cm-1"]),
                "paper_Y0": float(paper_row["Y0"]),
                "replayed_Y0": float(recovered["Y0"]),
                "Y0_ratio_replayed_to_paper": float(recovered["Y0"])
                / float(paper_row["Y0"]),
                "paper_k": float(paper_row["k"]),
                "replayed_k": float(recovered["k"]),
                "k_difference": float(recovered["k"]) - float(paper_row["k"]),
                "paper_R2": float(paper_row["R2"]),
                "replayed_R2": float(recovered["R2"]),
                "R2_difference": float(recovered["R2"]) - float(paper_row["R2"]),
                "paper_LOD_M": float(paper_row["LOD_M"]),
                "diagnostic_inverted_blank_mean_plus_3sd_M": float(
                    recovered["LOD_mean_plus_3sd_M"]
                ),
                "paper_LOQ_M": float(paper_row["LOQ_M"]),
                "diagnostic_inverted_blank_mean_plus_10sd_M": float(
                    recovered["LOQ_mean_plus_10sd_M"]
                ),
                "diagnostic_record_selection_scenario": str(
                    recovered["record_selection_scenario"]
                ),
                "diagnostic_blank_strategy": str(recovered["blank_strategy"]),
                "diagnostic_blank_scan_count": int(
                    recovered["n_blank_scans"]
                ),
                "diagnostic_model": "Y=Y0*exp(k*log10(C_M))",
                "lod_loq_reporting_status": str(
                    recovered["lod_loq_reporting_status"]
                ),
                "parameter_reproduction_status": (
                    "not_reproduced_from_supplied_calibration_summary"
                ),
                "scientific_limitation": (
                    "the diagnostic retains a non-context-matched mixed "
                    "high-power nominal blank and therefore cannot validate a "
                    "low-power analytical LOD/LOQ"
                ),
            }
        )
    return pd.DataFrame(rows)


def build_claim_assessment(
    lineage: pd.DataFrame,
    replay_metrics: pd.DataFrame,
    table_metrics: pd.DataFrame,
) -> pd.DataFrame:
    sample = lineage[lineage["sample_type"].eq("sample")]
    nonmatching_samples = int(
        (
            ~(
                sample["setting_matches_expected"].astype(bool)
                & sample["date_matches_expected"].astype(bool)
            )
        ).sum()
    )
    axis_conflicts_all = int(
        (~lineage["axis_match_1e-5"].astype(bool)).sum()
    )
    axis_conflicts_samples = int(
        (~sample["axis_match_1e-5"].astype(bool)).sum()
    )
    worst_source_axis_difference = float(
        lineage["axis_max_abs_difference"].max()
    )
    reused_records = int(lineage["source_scan_is_reused"].sum())
    passing_scan_channels = int(
        replay_metrics["passes_cross_environment_tolerance"].astype(bool).sum()
    )
    passing_table_checks = int(table_metrics["passes"].astype(bool).sum())
    selected_intensity_tolerance = float(
        table_metrics.loc[
            table_metrics["dataset"].eq(
                "calibration_at_selected_shifts.csv:intensity_and_sd"
            ),
            "absolute_tolerance",
        ].iloc[0]
    )
    selected_cv_tolerance = float(
        table_metrics.loc[
            table_metrics["dataset"].eq(
                "calibration_at_selected_shifts.csv:cv"
            ),
            "absolute_tolerance",
        ].iloc[0]
    )
    claims = [
        {
            "claim_id": "figure_3_4a_computational_lineage",
            "claim": (
                "The preserved Figure 3/4A processed calibration tables can be "
                "regenerated from the supplied prepared scan files."
            ),
            "classification": "supportable_as_computational_lineage",
            "evidence": (
                f"{passing_scan_channels}/{len(replay_metrics)} scan channels "
                f"and {passing_table_checks}/{len(table_metrics)} aggregate "
                "table checks pass their declared cross-environment tolerances; "
                "the selected-shift intensity/SD and CV limits are "
                f"{selected_intensity_tolerance:g} intensity units and "
                f"{selected_cv_tolerance:g} percentage points, respectively."
            ),
            "required_action": "retain publication snapshot and replay audit",
        },
        {
            "claim_id": "uniform_750_5_5_l_calibration",
            "claim": (
                "The calibration series is a uniform 3 July 2024 low-power "
                "750_5_5_L experiment."
            ),
            "classification": "contradicted_by_scan_lineage",
            "evidence": (
                f"{nonmatching_samples}/{EXPECTED_SAMPLE_ROWS} sample scans have "
                "a different date or setting; all 15 blanks are later high-power scans."
            ),
            "required_action": (
                "qualify or withdraw the uniform-setting claim; do not relabel bytes"
            ),
        },
        {
            "claim_id": "prepared_axes_match_master_sources",
            "claim": (
                "Every prepared calibration scan preserves the Raman axis of "
                "its exact-intensity master source."
            ),
            "classification": "contradicted_by_axis_lineage",
            "evidence": (
                f"{axis_conflicts_all}/{EXPECTED_ROWS} prepared axes differ by "
                f"more than 1e-5 cm-1, including {axis_conflicts_samples} "
                f"sample scans; worst max absolute axis difference="
                f"{worst_source_axis_difference:.6g} cm-1."
            ),
            "required_action": (
                "preserve prepared axes as historical evidence and use source "
                "axes for any new source-verified reanalysis"
            ),
        },
        {
            "claim_id": "independent_three_replicates",
            "claim": (
                "Every prepared replicate/accumulation entry represents an "
                "independent source scan."
            ),
            "classification": "contradicted_by_exact_source_reuse",
            "evidence": (
                f"{reused_records} prepared rows participate in exact source-scan "
                f"reuse; {EXPECTED_ROWS - EXPECTED_UNIQUE_SOURCE_SCANS} rows are "
                "duplicates beyond the 204 distinct exact source-scan identities. "
                "Distinct identity alone does not establish experimental "
                "independence."
            ),
            "required_action": (
                "report the reuse and avoid treating duplicated source scans as "
                "independent observations"
            ),
        },
        {
            "claim_id": "low_power_auagbc_blank",
            "claim": (
                "LOD/LOQ use a context-matched 750_5_5_L AuAgBC blank without 4-ATP."
            ),
            "classification": "unsupported_blank_missing",
            "evidence": (
                "The 15 prepared blanks trace exactly to three later 750_5_5_H "
                "exports; the exhaustive search of the supplied measurement "
                "collections found no target-context file."
            ),
            "required_action": (
                "reacquire/recover the correct blank or withdraw quantitative LOD/LOQ"
            ),
        },
        {
            "claim_id": "paper_calibration_parameters",
            "claim": (
                "The paper's Y0, k, and R2 values are generated by the supplied "
                "replicate-mean calibration table using Y=Y0 exp(k log10 C)."
            ),
            "classification": "not_reproduced",
            "evidence": (
                "The recovered October 2025 pipeline yields materially different "
                "fit parameters for all three bands."
            ),
            "required_action": (
                "locate the exact fitting project/input subset or revise the values"
            ),
        },
        {
            "claim_id": "quantitative_blind_predictions",
            "claim": (
                "Blind-sample concentration predictions constitute independently "
                "validated quantitative performance."
            ),
            "classification": "requires_reanalysis",
            "evidence": (
                "Predictions depend on calibration parameters and LOD/LOQ whose "
                "input setting, blank, and exact fit lineage are unresolved."
            ),
            "required_action": (
                "preserve as historical results but do not present as validated "
                "quantification until calibration is corrected"
            ),
        },
        {
            "claim_id": "qualitative_4atp_band_evidence",
            "claim": (
                "The supplied processed spectra show signals near the nominal "
                "characteristic 4-ATP bands at 392, 1078, and 1590 cm-1 in the "
                "labelled prepared samples."
            ),
            "classification": "supportable_with_acquisition_qualification",
            "evidence": (
                "The processed spectral snapshot is numerically reproducible, but "
                "band attribution and any concentration-response trend are "
                "confounded by non-uniform acquisition and exact source reuse."
            ),
            "required_action": (
                "retain only as nominal band-position/apparent prepared-series "
                "evidence with explicit caveats; do not claim a validated trend"
            ),
        },
    ]
    return pd.DataFrame(claims)


def build_summary(
    lineage: pd.DataFrame,
    reuse: pd.DataFrame,
    replay_metrics: pd.DataFrame,
    table_metrics: pd.DataFrame,
    model_sensitivity: pd.DataFrame,
    parameter_comparison: pd.DataFrame,
) -> dict[str, Any]:
    sample = lineage[lineage["sample_type"].eq("sample")]
    blank = lineage[lineage["sample_type"].eq("blank")]
    context_uniform = sum(
        bool(
            (
                group["setting_matches_expected"].astype(bool)
                & group["date_matches_expected"].astype(bool)
            ).all()
        )
        for _label, group in sample.groupby("concentration_label", sort=True)
    )
    return {
        "schema_version": "1.0",
        "analysis_id": "calibration_curve_lineage_and_sensitivity_audit",
        "result": "historical_computation_replayed_quantitative_claims_not_validated",
        "counts": {
            "prepared_rows": int(len(lineage)),
            "sample_rows": int(len(sample)),
            "blank_rows": int(len(blank)),
            "unique_source_scans": int(lineage["source_scan_id"].nunique()),
            "reused_prepared_rows": int(lineage["source_scan_is_reused"].sum()),
            "source_setting_counts_all": {
                str(key): int(value)
                for key, value in lineage["source_setting"].value_counts().items()
            },
            "source_setting_counts_samples": {
                str(key): int(value)
                for key, value in sample["source_setting"].value_counts().items()
            },
            "source_axis_matches_1e-5_all": int(
                lineage["axis_match_1e-5"].astype(bool).sum()
            ),
            "source_axis_conflicts_1e-5_all": int(
                (~lineage["axis_match_1e-5"].astype(bool)).sum()
            ),
            "source_axis_conflicts_1e-5_samples": int(
                (~sample["axis_match_1e-5"].astype(bool)).sum()
            ),
            "source_date_counts_all": {
                str(key): int(value)
                for key, value in lineage["source_date"].value_counts().items()
            },
            "fully_context_uniform_concentrations": int(context_uniform),
            "reused_source_groups": int(reuse["source_scan_id"].nunique()),
        },
        "replay": {
            "grid_points": EXPECTED_GRID_POINTS,
            "scan_channels_passing": int(
                replay_metrics["passes_cross_environment_tolerance"].sum()
            ),
            "scan_channels_total": int(len(replay_metrics)),
            "worst_rmse": float(replay_metrics["rmse"].max()),
            "worst_max_abs_difference": float(
                replay_metrics["max_abs_difference"].max()
            ),
            "table_checks_passing": int(table_metrics["passes"].sum()),
            "table_checks_total": int(len(table_metrics)),
            "cross_environment_intensity_tolerance": REPLAY_ABSOLUTE_TOLERANCE,
        },
        "model_audit": {
            "sensitivity_rows": int(len(model_sensitivity)),
            "paper_parameter_rows_not_reproduced": int(
                parameter_comparison["parameter_reproduction_status"]
                .eq("not_reproduced_from_supplied_calibration_summary")
                .sum()
            ),
            "blank_status": (
                "no context-matched low-power AuAgBC blank is available; every "
                "blank scenario is historical or counterfactual"
            ),
        },
        "environment_used_to_generate_committed_evidence": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "numpy": _package_version("numpy"),
            "pandas": _package_version("pandas"),
            "scipy": _package_version("scipy"),
            "pybaselines": _package_version("pybaselines"),
        },
        "interpretation": (
            "The prepared bytes and historical processing chain explain the "
            "publication snapshot. They do not establish a scientifically valid "
            "uniform low-power calibration, its LOD/LOQ, or downstream quantitative "
            "blind prediction claims."
        ),
    }


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _computed_artifacts(*, require_lock: bool) -> tuple[dict[Path, pd.DataFrame], dict[Path, Any]]:
    lineage = build_lineage()
    reuse = build_reuse_table(lineage)
    replay_manifest = build_replay_manifest(lineage)
    replay_config = build_replay_config()
    replay = replay_calibration(lineage, require_lock=require_lock)
    replay_metrics = build_replay_metrics(replay)
    table_metrics = build_table_metrics(replay)
    model_sensitivity, _blank_statistics = build_model_sensitivity(replay)
    parameter_comparison = build_parameter_comparison(model_sensitivity)
    claim_assessment = build_claim_assessment(
        lineage, replay_metrics, table_metrics
    )
    summary = build_summary(
        lineage,
        reuse,
        replay_metrics,
        table_metrics,
        model_sensitivity,
        parameter_comparison,
    )
    frames = {
        LINEAGE_OUTPUT: lineage,
        REUSE_OUTPUT: reuse,
        FFT_LOCK_OUTPUT: replay.fft_locks,
        REPLAY_METRICS_OUTPUT: replay_metrics,
        TABLE_METRICS_OUTPUT: table_metrics,
        MODEL_SENSITIVITY_OUTPUT: model_sensitivity,
        PARAMETER_COMPARISON_OUTPUT: parameter_comparison,
        CLAIM_ASSESSMENT_OUTPUT: claim_assessment,
        REPLAY_MANIFEST_OUTPUT: replay_manifest,
    }
    json_values = {
        REPLAY_CONFIG_OUTPUT: replay_config,
        SUMMARY_OUTPUT: summary,
    }
    return frames, json_values


def generate() -> None:
    frames, json_values = _computed_artifacts(require_lock=False)
    for path, frame in frames.items():
        _write_csv(path, frame)
    for path, value in json_values.items():
        _write_json(path, value)
    summary = json_values[SUMMARY_OUTPUT]
    print(
        json.dumps(
            {
                "status": "generated",
                "prepared_rows": summary["counts"]["prepared_rows"],
                "unique_source_scans": summary["counts"]["unique_source_scans"],
                "scan_channels_passing": summary["replay"]["scan_channels_passing"],
                "worst_max_abs_difference": summary["replay"][
                    "worst_max_abs_difference"
                ],
                "paper_parameter_rows_not_reproduced": summary["model_audit"][
                    "paper_parameter_rows_not_reproduced"
                ],
            },
            indent=2,
        )
    )


def _compare_frames(
    path: Path,
    computed: pd.DataFrame,
    *,
    absolute_tolerance: float = CHECK_NUMERIC_ABSOLUTE_TOLERANCE,
    relative_tolerance: float = CHECK_NUMERIC_RELATIVE_TOLERANCE,
    column_absolute_tolerances: Mapping[str, float] | None = None,
    column_relative_tolerances: Mapping[str, float] | None = None,
) -> None:
    if not path.is_file():
        raise CalibrationAuditError(f"Missing committed audit artifact: {path}")
    committed = pd.read_csv(path).reset_index(drop=True)
    computed = computed.reset_index(drop=True)
    if list(committed.columns) != list(computed.columns):
        raise CalibrationAuditError(f"Column mismatch in {path}.")
    if committed.shape != computed.shape:
        raise CalibrationAuditError(
            f"Shape mismatch in {path}: {committed.shape} != {computed.shape}."
        )
    absolute_overrides = dict(column_absolute_tolerances or {})
    relative_overrides = dict(column_relative_tolerances or {})
    for column in committed.columns:
        column_absolute_tolerance = absolute_overrides.get(
            column, absolute_tolerance
        )
        column_relative_tolerance = relative_overrides.get(
            column, relative_tolerance
        )
        left_numeric = pd.to_numeric(committed[column], errors="coerce")
        right_numeric = pd.to_numeric(computed[column], errors="coerce")
        numeric_mask = left_numeric.notna() | right_numeric.notna()
        both_numeric = left_numeric.notna() & right_numeric.notna()
        if numeric_mask.any() and not numeric_mask.equals(both_numeric):
            raise CalibrationAuditError(
                f"Numeric/non-numeric cell mismatch in {path}, column {column}."
            )
        if both_numeric.any() and not np.allclose(
            left_numeric[both_numeric].to_numpy(dtype=float),
            right_numeric[both_numeric].to_numpy(dtype=float),
            rtol=column_relative_tolerance,
            atol=column_absolute_tolerance,
            equal_nan=True,
        ):
            difference = np.max(
                np.abs(
                    left_numeric[both_numeric].to_numpy(dtype=float)
                    - right_numeric[both_numeric].to_numpy(dtype=float)
                )
            )
            raise CalibrationAuditError(
                f"Numerical mismatch in {path}, column {column}; max abs={difference}."
            )
        text_mask = ~numeric_mask
        left_text = committed.loc[text_mask, column].fillna("").astype(str)
        right_text = computed.loc[text_mask, column].fillna("").astype(str)
        if not left_text.reset_index(drop=True).equals(
            right_text.reset_index(drop=True)
        ):
            raise CalibrationAuditError(
                f"Text mismatch in {path}, column {column}."
            )


def _compare_table_metrics(path: Path, computed: pd.DataFrame) -> None:
    """Compare stable table contracts while allowing bounded diagnostics to drift.

    RMSE and maximum-difference values summarize a fresh cross-environment
    replay, so their exact values are environment-specific. The stable
    contract is the row identity, number of compared cells, declared
    tolerance, pass result, and explanatory note. Diagnostic values may differ
    by no more than that row's fixed scientific tolerance.
    """
    if not path.is_file():
        raise CalibrationAuditError(f"Missing committed audit artifact: {path}")
    committed = pd.read_csv(path).reset_index(drop=True)
    computed = computed.reset_index(drop=True)
    expected_columns = [
        "dataset",
        "compared_numeric_cells",
        "rmse",
        "max_abs_difference",
        "absolute_tolerance",
        "passes",
        "note",
    ]
    if (
        list(committed.columns) != expected_columns
        or list(computed.columns) != expected_columns
    ):
        raise CalibrationAuditError(f"Column mismatch in {path}.")
    if committed.shape != computed.shape:
        raise CalibrationAuditError(
            f"Shape mismatch in {path}: {committed.shape} != {computed.shape}."
        )

    for column in ("dataset", "note"):
        if not committed[column].astype(str).equals(computed[column].astype(str)):
            raise CalibrationAuditError(
                f"Text mismatch in {path}, column {column}."
            )
    if not np.array_equal(
        committed["compared_numeric_cells"].to_numpy(dtype=int),
        computed["compared_numeric_cells"].to_numpy(dtype=int),
    ):
        raise CalibrationAuditError(
            f"Exact mismatch in {path}, column compared_numeric_cells."
        )
    if not np.allclose(
        committed["absolute_tolerance"].to_numpy(dtype=float),
        computed["absolute_tolerance"].to_numpy(dtype=float),
        rtol=0,
        atol=1e-15,
    ):
        raise CalibrationAuditError(
            f"Exact mismatch in {path}, column absolute_tolerance."
    )
    committed_passes = committed["passes"].astype(str).str.casefold()
    computed_passes = computed["passes"].astype(str).str.casefold()
    if not committed_passes.isin({"true", "false"}).all() or not (
        computed_passes.isin({"true", "false"}).all()
    ):
        raise CalibrationAuditError(f"Invalid boolean in {path}, column passes.")
    if not committed_passes.equals(computed_passes):
        raise CalibrationAuditError(f"Exact mismatch in {path}, column passes.")

    row_tolerances = committed["absolute_tolerance"].to_numpy(dtype=float)
    for label, frame, pass_values in (
        ("committed", committed, committed_passes),
        ("computed", computed, computed_passes),
    ):
        rmse_values = frame["rmse"].to_numpy(dtype=float)
        maximum_values = frame["max_abs_difference"].to_numpy(dtype=float)
        if (
            not np.isfinite(rmse_values).all()
            or not np.isfinite(maximum_values).all()
            or (rmse_values < 0).any()
            or (maximum_values < 0).any()
        ):
            raise CalibrationAuditError(
                f"Invalid {label} numerical diagnostic in {path}."
            )
        if np.any(rmse_values > maximum_values + 1e-15):
            raise CalibrationAuditError(
                f"Inconsistent {label} RMSE in {path}."
            )
        expected_passes = maximum_values <= row_tolerances
        recorded_passes = pass_values.eq("true").to_numpy(dtype=bool)
        if not np.array_equal(recorded_passes, expected_passes):
            raise CalibrationAuditError(
                f"Inconsistent {label} pass result in {path}."
            )

    for column in ("rmse", "max_abs_difference"):
        left = committed[column].to_numpy(dtype=float)
        right = computed[column].to_numpy(dtype=float)
        if (
            not np.isfinite(left).all()
            or not np.isfinite(right).all()
            or (left < 0).any()
            or (right < 0).any()
        ):
            raise CalibrationAuditError(
                f"Invalid numerical diagnostic in {path}, column {column}."
            )
        allowed = row_tolerances + (
            CHECK_NUMERIC_RELATIVE_TOLERANCE * np.abs(left)
        )
        if np.any(np.abs(left - right) > allowed):
            difference = float(np.max(np.abs(left - right)))
            raise CalibrationAuditError(
                f"Numerical mismatch in {path}, column {column}; "
                f"max abs={difference}."
            )


def check() -> None:
    frames, json_values = _computed_artifacts(require_lock=True)
    for path, frame in frames.items():
        if path == TABLE_METRICS_OUTPUT:
            _compare_table_metrics(path, frame)
            continue
        tolerance = (
            1e-15
            if path
            in {
                LINEAGE_OUTPUT,
                REUSE_OUTPUT,
                FFT_LOCK_OUTPUT,
                REPLAY_MANIFEST_OUTPUT,
            }
            else CHECK_NUMERIC_ABSOLUTE_TOLERANCE
        )
        relative_overrides: dict[str, float] = {}
        absolute_overrides: dict[str, float] = {}
        if path == MODEL_SENSITIVITY_OUTPUT:
            relative_overrides = {
                column: DIAGNOSTIC_FIT_RELATIVE_TOLERANCE
                for column in MODEL_DIAGNOSTIC_RELATIVE_COLUMNS
            }
            absolute_overrides = {
                column: 0.0 for column in MODEL_EXACT_NUMERIC_COLUMNS
            }
            relative_overrides.update(
                {column: 0.0 for column in MODEL_EXACT_NUMERIC_COLUMNS}
            )
        elif path == PARAMETER_COMPARISON_OUTPUT:
            relative_overrides = {
                column: DIAGNOSTIC_FIT_RELATIVE_TOLERANCE
                for column in PARAMETER_DIAGNOSTIC_RELATIVE_COLUMNS
            }
            absolute_overrides = {
                column: 0.0 for column in PARAMETER_EXACT_NUMERIC_COLUMNS
            }
            relative_overrides.update(
                {column: 0.0 for column in PARAMETER_EXACT_NUMERIC_COLUMNS}
            )
        _compare_frames(
            path,
            frame,
            absolute_tolerance=tolerance,
            column_absolute_tolerances=absolute_overrides,
            column_relative_tolerances=relative_overrides,
        )

    if not REPLAY_CONFIG_OUTPUT.is_file():
        raise CalibrationAuditError("Missing committed replay configuration.")
    committed_config = json.loads(REPLAY_CONFIG_OUTPUT.read_text(encoding="utf-8"))
    if committed_config != json_values[REPLAY_CONFIG_OUTPUT]:
        raise CalibrationAuditError("Replay configuration differs from the audited recipe.")
    if not SUMMARY_OUTPUT.is_file():
        raise CalibrationAuditError("Missing committed calibration audit summary.")
    committed_summary = json.loads(SUMMARY_OUTPUT.read_text(encoding="utf-8"))
    computed_summary = json_values[SUMMARY_OUTPUT]
    for section in ("analysis_id", "result", "counts", "interpretation"):
        if committed_summary.get(section) != computed_summary.get(section):
            raise CalibrationAuditError(
                f"Calibration audit summary section changed: {section}."
            )
    for key in (
        "grid_points",
        "scan_channels_passing",
        "scan_channels_total",
        "table_checks_passing",
        "table_checks_total",
    ):
        if committed_summary["replay"].get(key) != computed_summary["replay"].get(key):
            raise CalibrationAuditError(f"Calibration replay summary changed: {key}.")
    for key in ("worst_rmse", "worst_max_abs_difference"):
        if not math.isclose(
            float(committed_summary["replay"][key]),
            float(computed_summary["replay"][key]),
            rel_tol=CHECK_NUMERIC_RELATIVE_TOLERANCE,
            abs_tol=CHECK_NUMERIC_ABSOLUTE_TOLERANCE,
        ):
            raise CalibrationAuditError(f"Calibration replay metric changed: {key}.")
    print(
        json.dumps(
            {
                "status": "verified",
                "prepared_rows": computed_summary["counts"]["prepared_rows"],
                "unique_source_scans": computed_summary["counts"][
                    "unique_source_scans"
                ],
                "scan_channels_passing": computed_summary["replay"][
                    "scan_channels_passing"
                ],
                "table_checks_passing": computed_summary["replay"][
                    "table_checks_passing"
                ],
                "paper_parameter_rows_not_reproduced": computed_summary[
                    "model_audit"
                ]["paper_parameter_rows_not_reproduced"],
            },
            indent=2,
        )
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Recompute the audit and compare it with committed evidence.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.check:
            check()
        else:
            generate()
    except (CalibrationAuditError, OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
