"""Manifest-driven orchestration, deterministic exports, and verification."""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

import numpy as np
import pandas as pd

from . import __version__
from .errors import ConfigurationError, ProcessingError, VerificationError
from .io import read_spectrum_file, sha256_file
from .models import ProcessedSpectrum, Spectrum
from .processing import (
    align_spectra,
    apply_post_blank_baseline,
    crop_spectrum,
    ensure_increasing_unique,
    normalize_signal,
    parse_peak_specs,
    peak_value,
    preprocess_signal,
    scale_for_acquisition,
)
from .profiles import PROFILE_NAMES, get_profile


SCHEMA_VERSION = "1.0"
MANIFEST_ALIASES = {
    "type": "sample_type",
    "concentration_M": "concentration_molar",
    "concentration_m": "concentration_molar",
    "scan": "accumulation",
}
REQUIRED_MANIFEST_COLUMNS = (
    "file",
    "sample_type",
    "concentration_molar",
    "replicate",
    "accumulation",
    "instrument",
    "acquisition",
)
PREFERRED_METADATA_COLUMNS = (
    "spectrum_id",
    "study",
    "sample_type",
    "analyte",
    "matrix",
    "concentration_molar",
    "concentration_label",
    "replicate",
    "accumulation",
    "instrument",
    "acquisition",
    "timepoint",
)
KNOWN_OUTPUTS = (
    "spectra_scan.csv",
    "spectra_replicate.csv",
    "spectra_concentration.csv",
    "peaks_scan.csv",
    "peaks_replicate.csv",
    "peaks_concentration.csv",
    "resolved_manifest.csv",
    "processing_report.csv",
    "source_metadata.json",
    "provenance_files.csv",
    "run.json",
)


@dataclass
class Job:
    config_path: Path
    manifest_path: Path
    input_root: Path
    output_root: Path
    profile_name: str
    profile: dict[str, Any]
    manifest: pd.DataFrame
    raw_config: dict[str, Any]


@dataclass
class AggregateSpectrum:
    metadata: dict[str, Any]
    x: np.ndarray
    mean: np.ndarray
    sd: np.ndarray
    count: np.ndarray


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if pd.isna(value) if not isinstance(value, (dict, list, tuple)) else False:
        return None
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _load_structured(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        try:
            loaded = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise ConfigurationError(f"Invalid JSON in {path}: line {exc.lineno}, column {exc.colno}: {exc.msg}.") from exc
    else:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover
            raise ConfigurationError("PyYAML is required to read YAML configurations.") from exc
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
        except yaml.YAMLError as exc:
            raise ConfigurationError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ConfigurationError(f"Configuration {path} must contain a top-level mapping.")
    return loaded


def _resolve_from(base: Path, value: str | Path, description: str) -> Path:
    if value is None or not str(value).strip():
        raise ConfigurationError(f"{description} is required.")
    candidate = Path(str(value)).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate.resolve()


def _read_manifest(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise ConfigurationError(f"Manifest does not exist: {path}")
    try:
        frame = pd.read_csv(path, encoding="utf-8-sig", dtype=object, keep_default_na=False)
    except Exception as exc:
        raise ConfigurationError(f"Could not read manifest {path}: {exc}") from exc
    frame.columns = [str(column).strip() for column in frame.columns]
    for alias, canonical in MANIFEST_ALIASES.items():
        if alias in frame.columns and canonical not in frame.columns:
            frame = frame.rename(columns={alias: canonical})
    missing = [column for column in REQUIRED_MANIFEST_COLUMNS if column not in frame.columns]
    if missing:
        raise ConfigurationError(
            f"Manifest {path} is missing required columns: {', '.join(missing)}. "
            f"Required columns are: {', '.join(REQUIRED_MANIFEST_COLUMNS)}."
        )
    if frame.empty:
        raise ConfigurationError(f"Manifest {path} contains no spectrum rows.")
    frame = frame.copy()
    frame["__manifest_row"] = np.arange(2, len(frame) + 2)
    for index, row in frame.iterrows():
        row_number = int(row["__manifest_row"])
        for column in ("file", "sample_type", "replicate", "accumulation", "instrument"):
            if not str(row[column]).strip():
                raise ConfigurationError(f"Manifest row {row_number} has an empty required value in {column!r}.")
        concentration = str(row["concentration_molar"]).strip()
        if concentration:
            try:
                numeric = float(concentration)
            except ValueError as exc:
                raise ConfigurationError(
                    f"Manifest row {row_number} concentration_molar must be numerical or empty; received {concentration!r}."
                ) from exc
            if not math.isfinite(numeric) or numeric < 0:
                raise ConfigurationError(
                    f"Manifest row {row_number} concentration_molar must be finite and non-negative; received {concentration!r}."
                )
            frame.at[index, "concentration_molar"] = numeric
        else:
            frame.at[index, "concentration_molar"] = None
        frame.at[index, "sample_type"] = str(row["sample_type"]).strip()
        frame.at[index, "instrument"] = str(row["instrument"]).strip()
    return frame


def load_job(
    config_or_manifest: str | Path,
    *,
    output_root: str | Path | None = None,
    input_root: str | Path | None = None,
    profile_name: str | None = None,
) -> Job:
    """Resolve a YAML/JSON job or direct CSV manifest into validated paths."""
    path = Path(config_or_manifest).expanduser().resolve()
    if not path.is_file():
        raise ConfigurationError(f"Configuration or manifest does not exist: {path}")
    if path.suffix.lower() == ".csv":
        if profile_name is None:
            raise ConfigurationError(
                "Direct CSV-manifest processing requires --profile so the numerical method is explicit."
            )
        raw_config: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "profile": profile_name,
            "manifest": path.name,
            "input_root": ".",
            "output_root": None,
            "options": {},
        }
        manifest_path = path
        base = path.parent
    elif path.suffix.lower() in {".yaml", ".yml", ".json"}:
        raw_config = _load_structured(path)
        schema = str(raw_config.get("schema_version", ""))
        if schema != SCHEMA_VERSION:
            raise ConfigurationError(
                f"Configuration schema_version must be {SCHEMA_VERSION!r}; received {schema or '<missing>'!r}."
            )
        manifest_value = raw_config.get("manifest", raw_config.get("manifest_csv"))
        manifest_path = _resolve_from(path.parent, manifest_value, "Top-level manifest")
        base = path.parent
    else:
        raise ConfigurationError("Use a .yaml/.yml/.json job configuration or a .csv manifest.")

    chosen_profile = profile_name or raw_config.get("profile")
    if not chosen_profile:
        raise ConfigurationError(f"Top-level profile is required. Available profiles: {', '.join(PROFILE_NAMES)}.")
    chosen_profile = str(chosen_profile)
    options = raw_config.get("options", {}) or {}
    if not isinstance(options, dict):
        raise ConfigurationError("Top-level options must be a mapping.")
    options = dict(options)
    if "blank" in raw_config:
        if not isinstance(raw_config["blank"], dict):
            raise ConfigurationError("Top-level blank must be a mapping.")
        options["blank"] = raw_config["blank"]
    profile = get_profile(chosen_profile, options)

    input_value = input_root if input_root is not None else raw_config.get("input_root", manifest_path.parent)
    output_value = output_root if output_root is not None else raw_config.get("output_root")
    resolved_input = _resolve_from(Path.cwd() if input_root is not None else base, input_value, "input_root")
    resolved_output = _resolve_from(Path.cwd() if output_root is not None else base, output_value, "output_root")
    if not resolved_input.is_dir():
        raise ConfigurationError(f"input_root is not a directory: {resolved_input}")
    manifest = _read_manifest(manifest_path)
    return Job(
        config_path=path,
        manifest_path=manifest_path,
        input_root=resolved_input,
        output_root=resolved_output,
        profile_name=chosen_profile,
        profile=profile,
        manifest=manifest,
        raw_config=raw_config,
    )


def _relative_source(root: Path, raw_value: Any, row_number: int) -> tuple[Path, str]:
    raw = str(raw_value).strip().replace("\\", "/")
    relative = Path(raw)
    if relative.is_absolute():
        raise ConfigurationError(
            f"Manifest row {row_number} uses an absolute file path ({raw!r}). "
            "Use a path relative to input_root so the repository remains portable."
        )
    resolved = (root / relative).resolve()
    try:
        portable = resolved.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ConfigurationError(
            f"Manifest row {row_number} file {raw!r} escapes input_root. Repository-relative paths may not use '..' to leave it."
        ) from exc
    if not resolved.is_file():
        raise ConfigurationError(f"Manifest row {row_number} points to a missing file: {portable}")
    return resolved, portable


def _clean_manifest_metadata(row: Mapping[str, Any], portable_path: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key, value in row.items():
        if str(key).startswith("__") or key == "intensity_column":
            continue
        if key == "file":
            metadata[key] = portable_path
        elif value is None or (isinstance(value, float) and math.isnan(value)):
            metadata[key] = None
        else:
            metadata[key] = _jsonable(value)
    return metadata


def _safe_stem(value: str, fallback: str = "spectrum") -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", normalized).strip("._-")
    if not safe:
        safe = fallback
    if len(safe) > 140:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]
        safe = f"{safe[:125]}__{digest}"
    return safe


def _load_manifest_spectra(job: Job) -> tuple[list[Spectrum], list[str]]:
    cache: dict[Path, list[Spectrum]] = {}
    records: list[Spectrum] = []
    warnings: list[str] = []
    unselected_counts: dict[str, int] = defaultdict(int)
    for raw_value, selector in zip(job.manifest["file"], job.manifest.get("intensity_column", pd.Series([""] * len(job.manifest)))):
        if not str(selector).strip():
            unselected_counts[str(raw_value).strip().replace("\\", "/")] += 1
    duplicates = sorted(path for path, count in unselected_counts.items() if count > 1)
    if duplicates:
        raise ConfigurationError(
            "Manifest repeats file(s) without intensity_column selectors: " + ", ".join(duplicates) + ". "
            "Use one row to expand all columns, or one row per column with an explicit intensity_column."
        )

    record_ids: set[str] = set()
    for _, series in job.manifest.iterrows():
        raw_row = series.to_dict()
        row_number = int(raw_row["__manifest_row"])
        source_path, portable_path = _relative_source(job.input_root, raw_row["file"], row_number)
        if source_path not in cache:
            cache[source_path] = read_spectrum_file(source_path)
        all_spectra = cache[source_path]
        selector = str(raw_row.get("intensity_column", "")).strip()
        if selector:
            if selector.isdigit():
                selected = [spectrum.copy_with() for spectrum in all_spectra if spectrum.source_column_index == int(selector)]
            else:
                selected = [spectrum.copy_with() for spectrum in all_spectra if spectrum.source_column == selector]
                if not selected:
                    selected = [
                        spectrum.copy_with()
                        for spectrum in all_spectra
                        if spectrum.source_column.casefold() == selector.casefold()
                    ]
            if len(selected) != 1:
                available = ", ".join(
                    f"{spectrum.source_column_index}:{spectrum.source_column}" for spectrum in all_spectra
                )
                raise ConfigurationError(
                    f"Manifest row {row_number} intensity_column {selector!r} does not select exactly one usable column "
                    f"from {portable_path}. Available columns: {available}."
                )
        else:
            selected = [spectrum.copy_with() for spectrum in all_spectra]
        metadata = _clean_manifest_metadata(raw_row, portable_path)
        explicit_id = str(raw_row.get("spectrum_id", "")).strip()
        for column_position, spectrum in enumerate(selected, start=1):
            if explicit_id:
                base_id = explicit_id if len(selected) == 1 else f"{explicit_id}__{spectrum.source_column}"
            else:
                base_id = f"row{row_number:05d}__{Path(portable_path).stem}__{spectrum.source_column}"
            record_id = _safe_stem(base_id, fallback=f"row{row_number:05d}_column{column_position}")
            if record_id in record_ids:
                raise ConfigurationError(
                    f"Technical record id {record_id!r} is duplicated at manifest row {row_number}. "
                    "Provide unique spectrum_id values or intensity_column selectors."
                )
            record_ids.add(record_id)
            spectrum.record_id = record_id
            spectrum.manifest_metadata = dict(metadata)
            spectrum.manifest_metadata["source_intensity_column"] = spectrum.source_column
            spectrum.manifest_metadata["source_intensity_column_index"] = spectrum.source_column_index
            spectrum.manifest_metadata["manifest_row"] = row_number
            records.append(spectrum)
        if len(selected) > 1:
            warnings.append(
                f"Manifest row {row_number} expanded {len(selected)} intensity columns from {portable_path}; "
                "the row's explicit metadata was copied unchanged to each technical spectrum."
            )
    if not records:
        raise ConfigurationError("The manifest produced no spectra.")
    return records, warnings


def _is_blank(spectrum: Spectrum, blank_settings: dict[str, Any]) -> bool:
    declared = str(spectrum.manifest_metadata.get("sample_type", "")).strip().casefold()
    allowed = {str(value).strip().casefold() for value in blank_settings.get("sample_types", ["blank"])}
    return declared in allowed


def _blank_key(spectrum: Spectrum, fields: list[str]) -> tuple[str, ...]:
    missing = [field for field in fields if field not in spectrum.manifest_metadata]
    if missing:
        raise ConfigurationError(
            f"Record {spectrum.record_id!r} lacks blank.group_by field(s): {', '.join(missing)}."
        )
    return tuple(str(spectrum.manifest_metadata.get(field, "")) for field in fields)


def _interpolate_like(
    target_x: np.ndarray,
    source_x: np.ndarray,
    source_y: np.ndarray,
    *,
    legacy_constant_extrapolation: bool,
    method: str = "linear",
) -> np.ndarray:
    if len(target_x) == len(source_x) and np.allclose(target_x, source_x, rtol=1e-12, atol=1e-12):
        return source_y.copy()
    order = np.argsort(source_x, kind="mergesort")
    x_sorted = source_x[order]
    y_sorted = source_y[order]
    unique_x, inverse, counts = np.unique(x_sorted, return_inverse=True, return_counts=True)
    if len(unique_x) != len(x_sorted):
        y_sorted = np.bincount(inverse, weights=y_sorted) / counts
        x_sorted = unique_x
    if not legacy_constant_extrapolation and (
        float(np.min(target_x)) < float(x_sorted[0]) or float(np.max(target_x)) > float(x_sorted[-1])
    ):
        raise ProcessingError(
            "Blank subtraction would extrapolate beyond the blank spectrum range. "
            "Use an intersection grid, crop the data, or provide a compatible blank."
        )
    if method == "linear":
        return np.interp(target_x, x_sorted, y_sorted)
    if method == "nearest":
        right = np.searchsorted(x_sorted, target_x, side="left")
        right = np.clip(right, 0, len(x_sorted) - 1)
        left = np.clip(right - 1, 0, len(x_sorted) - 1)
        indexes = np.where(
            np.abs(x_sorted[right] - target_x) < np.abs(target_x - x_sorted[left]),
            right,
            left,
        )
        return y_sorted[indexes]
    if method == "pchip":
        try:
            from scipy.interpolate import PchipInterpolator
        except ImportError as exc:  # pragma: no cover
            raise ProcessingError("SciPy is required for PCHIP blank interpolation.") from exc
        return np.asarray(PchipInterpolator(x_sorted, y_sorted, extrapolate=False)(target_x), dtype=float)
    raise ConfigurationError("blank.interpolation must be 'linear', 'nearest', or 'pchip'.")


def _blank_reference(
    target: Spectrum,
    candidates: list[Spectrum],
    values: dict[str, np.ndarray],
    settings: dict[str, Any],
    *,
    legacy_constant_extrapolation: bool,
) -> tuple[np.ndarray, list[str]]:
    fields = [str(field) for field in settings.get("group_by", [])]
    target_key = _blank_key(target, fields)
    matches = [candidate for candidate in candidates if _blank_key(candidate, fields) == target_key]
    if not matches:
        label = dict(zip(fields, target_key)) if fields else "the global blank group"
        raise ProcessingError(
            f"No manifest-declared blank matches record {target.record_id!r} for {label}. "
            "Add a blank row or adjust blank.group_by explicitly."
        )
    matches = sorted(matches, key=lambda spectrum: spectrum.record_id)
    strategy = str(settings.get("strategy", "mean")).lower()
    interpolation = str(settings.get("interpolation", "linear")).lower()
    if interpolation not in {"linear", "nearest", "pchip"}:
        raise ConfigurationError("blank.interpolation must be 'linear', 'nearest', or 'pchip'.")
    if strategy == "first":
        matches = matches[:1]
    elif strategy not in {"mean", "median"}:
        raise ConfigurationError("blank.strategy must be 'mean', 'median', or 'first'.")
    if legacy_constant_extrapolation:
        # Bit-for-bit algorithmic order from the portable individual-v2 script,
        # including np.interp's historical treatment of descending axes.
        matches = sorted(matches, key=lambda spectrum: spectrum.source_path.name.casefold())
        reference_x = matches[0].x
        aligned_rows = [values[matches[0].record_id]]
        for match in matches[1:]:
            aligned_rows.append(np.interp(reference_x, match.x, values[match.record_id]))
        aligned = np.vstack(aligned_rows)
        reference = np.median(aligned, axis=0) if strategy == "median" else np.mean(aligned, axis=0)
        if len(target.x) == len(reference_x) and np.allclose(target.x, reference_x):
            return reference, [match.record_id for match in matches]
        return np.interp(target.x, reference_x, reference), [match.record_id for match in matches]
    aligned = np.vstack(
        [
            _interpolate_like(
                target.x,
                match.x,
                values[match.record_id],
                legacy_constant_extrapolation=legacy_constant_extrapolation,
                method=interpolation,
            )
            for match in matches
        ]
    )
    reference = np.median(aligned, axis=0) if strategy == "median" else np.mean(aligned, axis=0)
    return reference, [match.record_id for match in matches]


def _metadata_columns(spectra: Iterable[Spectrum]) -> list[str]:
    available = {
        key
        for spectrum in spectra
        for key in spectrum.manifest_metadata
        if not str(key).startswith("__") and key not in {"source_intensity_column", "source_intensity_column_index"}
    }
    preferred = [column for column in PREFERRED_METADATA_COLUMNS if column in available]
    remaining = sorted(available.difference(preferred), key=str.casefold)
    return preferred + remaining


def _cell(value: Any) -> Any:
    value = _jsonable(value)
    if value is None:
        return ""
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        # Seventeen significant digits round-trip every IEEE-754 float64 while
        # remaining deterministic across supported Python versions.
        return format(value, ".17g")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return _canonical_json(value)
    return str(value)


def _write_csv(path: Path, columns: list[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        for row in rows:
            writer.writerow([_cell(row.get(column)) for column in columns])


def _same_axes(items: list[tuple[np.ndarray, np.ndarray]]) -> bool:
    first_x = items[0][0]
    return all(len(x) == len(first_x) and np.allclose(x, first_x, rtol=1e-12, atol=1e-12) for x, _ in items[1:])


def _stack_common(items: list[tuple[np.ndarray, np.ndarray]]) -> tuple[np.ndarray, np.ndarray]:
    if _same_axes(items):
        return items[0][0].copy(), np.vstack([y for _, y in items])
    cleaned: list[tuple[np.ndarray, np.ndarray]] = []
    for x, y in items:
        order = np.argsort(x, kind="mergesort")
        x_sorted, y_sorted = x[order], y[order]
        unique_x, inverse, counts = np.unique(x_sorted, return_inverse=True, return_counts=True)
        if len(unique_x) != len(x_sorted):
            y_sorted = np.bincount(inverse, weights=y_sorted) / counts
            x_sorted = unique_x
        cleaned.append((x_sorted, y_sorted))
    lo = max(float(x[0]) for x, _ in cleaned)
    hi = min(float(x[-1]) for x, _ in cleaned)
    if lo >= hi:
        raise ProcessingError("Spectra selected for aggregation have no overlapping Raman-shift range.")
    steps = np.concatenate([np.diff(x) for x, _ in cleaned])
    steps = steps[np.isfinite(steps) & (steps > 0)]
    step = float(np.median(steps))
    points = int(math.floor((hi - lo) / step)) + 1
    if points < 5:
        raise ProcessingError("Aggregation overlap contains fewer than five points.")
    common = np.linspace(lo, hi, points)
    return common, np.vstack([np.interp(common, x, y) for x, y in cleaned])


def _group_fields(profile: dict[str, Any], metadata_columns: list[str]) -> tuple[list[str], list[str]]:
    aggregation = profile.get("aggregation", {}) or {}
    extra = [str(field) for field in aggregation.get("group_by", [])]
    absent = [field for field in extra if field not in metadata_columns]
    if absent:
        raise ConfigurationError(f"aggregation.group_by contains absent manifest column(s): {', '.join(absent)}.")
    concentration_base = ["sample_type", "concentration_molar", "concentration_label", "instrument"]
    concentration = []
    for field in extra + concentration_base:
        if field in metadata_columns and field not in concentration:
            concentration.append(field)
    replicate = concentration + (["replicate"] if "replicate" in metadata_columns else [])
    return replicate, concentration


def _key_from_metadata(metadata: Mapping[str, Any], fields: list[str]) -> tuple[str, ...]:
    return tuple(_cell(metadata.get(field)) for field in fields)


def _aggregate_processed(
    processed: list[ProcessedSpectrum],
    replicate_fields: list[str],
    concentration_fields: list[str],
) -> tuple[list[AggregateSpectrum], list[AggregateSpectrum]]:
    grouped: dict[tuple[str, ...], list[ProcessedSpectrum]] = defaultdict(list)
    for item in processed:
        grouped[_key_from_metadata(item.spectrum.manifest_metadata, replicate_fields)].append(item)
    replicate_aggregates: list[AggregateSpectrum] = []
    for key in sorted(grouped):
        members = sorted(grouped[key], key=lambda item: item.spectrum.record_id)
        x, stack = _stack_common([(item.spectrum.x, item.final_y) for item in members])
        metadata = {field: members[0].spectrum.manifest_metadata.get(field) for field in replicate_fields}
        replicate_aggregates.append(
            AggregateSpectrum(
                metadata=metadata,
                x=x,
                mean=np.mean(stack, axis=0),
                sd=np.std(stack, axis=0, ddof=1) if len(stack) > 1 else np.full(stack.shape[1], np.nan),
                count=np.full(stack.shape[1], len(stack), dtype=int),
            )
        )
    concentration_groups: dict[tuple[str, ...], list[AggregateSpectrum]] = defaultdict(list)
    for aggregate in replicate_aggregates:
        concentration_groups[_key_from_metadata(aggregate.metadata, concentration_fields)].append(aggregate)
    concentration_aggregates: list[AggregateSpectrum] = []
    for key in sorted(concentration_groups):
        members = concentration_groups[key]
        x, stack = _stack_common([(item.x, item.mean) for item in members])
        metadata = {field: members[0].metadata.get(field) for field in concentration_fields}
        concentration_aggregates.append(
            AggregateSpectrum(
                metadata=metadata,
                x=x,
                mean=np.mean(stack, axis=0),
                sd=np.std(stack, axis=0, ddof=1) if len(stack) > 1 else np.full(stack.shape[1], np.nan),
                count=np.full(stack.shape[1], len(stack), dtype=int),
            )
        )
    return replicate_aggregates, concentration_aggregates


def _write_spectral_outputs(
    output_root: Path,
    processed: list[ProcessedSpectrum],
    metadata_columns: list[str],
    replicate_fields: list[str],
    concentration_fields: list[str],
    profile_name: str,
) -> tuple[list[AggregateSpectrum], list[AggregateSpectrum], dict[str, str]]:
    per_spectrum_dir = output_root / "processed_spectra"
    per_spectrum_dir.mkdir(parents=True, exist_ok=True)
    filenames: dict[str, str] = {}
    occupied: set[str] = set()
    for item in sorted(processed, key=lambda value: value.spectrum.record_id):
        spectrum = item.spectrum
        if profile_name == "legacy_individual" and len(spectrum.import_metadata.get("intensity_columns", [])) == 1:
            stem = _safe_stem(spectrum.source_path.stem) + "_blank_subtracted_processed"
            intensity_header = f"{spectrum.source_path.stem}_processed_intensity"
        else:
            stem = _safe_stem(spectrum.record_id)
            intensity_header = "intensity_processed"
        filename = stem + ".csv"
        if filename.casefold() in occupied:
            filename = f"{stem}__{hashlib.sha256(spectrum.record_id.encode('utf-8')).hexdigest()[:10]}.csv"
        occupied.add(filename.casefold())
        relative = (Path("processed_spectra") / filename).as_posix()
        filenames[spectrum.record_id] = relative
        _write_csv(
            output_root / relative,
            ["Raman shift cm-1", intensity_header],
            (
                {"Raman shift cm-1": x_value, intensity_header: y_value}
                for x_value, y_value in zip(spectrum.x, item.final_y)
            ),
        )

    scan_columns = [
        "record_id",
        "file",
        "source_sha256",
        "source_intensity_column",
        *[column for column in metadata_columns if column != "file"],
        "raman_shift_cm-1",
        "intensity_processed",
    ]

    def scan_rows() -> Iterator[dict[str, Any]]:
        for item in sorted(processed, key=lambda value: value.spectrum.record_id):
            spectrum = item.spectrum
            base = {
                "record_id": spectrum.record_id,
                "file": spectrum.manifest_metadata.get("file"),
                "source_sha256": spectrum.source_sha256,
                "source_intensity_column": spectrum.source_column,
                **spectrum.manifest_metadata,
            }
            for x_value, y_value in zip(spectrum.x, item.final_y):
                yield {**base, "raman_shift_cm-1": x_value, "intensity_processed": y_value}

    _write_csv(output_root / "spectra_scan.csv", scan_columns, scan_rows())
    replicate_aggregates, concentration_aggregates = _aggregate_processed(
        processed, replicate_fields, concentration_fields
    )

    def aggregate_rows(items: list[AggregateSpectrum], level: str) -> Iterator[dict[str, Any]]:
        for item in items:
            for index, x_value in enumerate(item.x):
                row = {
                    **item.metadata,
                    "raman_shift_cm-1": x_value,
                    "intensity_mean": item.mean[index],
                    "intensity_sd": item.sd[index],
                    "n_scans" if level == "replicate" else "n_replicates": int(item.count[index]),
                }
                if level == "concentration":
                    mean_value = float(item.mean[index])
                    row["cv_percent"] = (
                        100.0 * float(item.sd[index]) / mean_value
                        if math.isfinite(float(item.sd[index])) and mean_value != 0
                        else math.nan
                    )
                yield row

    _write_csv(
        output_root / "spectra_replicate.csv",
        replicate_fields + ["raman_shift_cm-1", "intensity_mean", "intensity_sd", "n_scans"],
        aggregate_rows(replicate_aggregates, "replicate"),
    )
    _write_csv(
        output_root / "spectra_concentration.csv",
        concentration_fields
        + ["raman_shift_cm-1", "intensity_mean", "intensity_sd", "n_replicates", "cv_percent"],
        aggregate_rows(concentration_aggregates, "concentration"),
    )
    return replicate_aggregates, concentration_aggregates, filenames


def _write_peak_outputs(
    output_root: Path,
    processed: list[ProcessedSpectrum],
    replicate_aggregates: list[AggregateSpectrum],
    concentration_aggregates: list[AggregateSpectrum],
    metadata_columns: list[str],
    replicate_fields: list[str],
    concentration_fields: list[str],
    profile: dict[str, Any],
) -> None:
    specs = parse_peak_specs(profile.get("peaks", []))
    band_columns = ["band", "center_cm-1", "window_cm-1", "method"]
    scan_columns = ["record_id", *metadata_columns, *band_columns, "peak_value", "observed_shift_cm-1", "n_points"]
    scan_peak_rows: list[dict[str, Any]] = []
    for item in sorted(processed, key=lambda value: value.spectrum.record_id):
        for spec in specs:
            value, observed, points = peak_value(item.spectrum.x, item.final_y, spec)
            scan_peak_rows.append(
                {
                    "record_id": item.spectrum.record_id,
                    **item.spectrum.manifest_metadata,
                    "band": spec.output_name,
                    "center_cm-1": spec.center_cm1,
                    "window_cm-1": spec.window_cm1,
                    "method": spec.method,
                    "peak_value": value,
                    "observed_shift_cm-1": observed,
                    "n_points": points,
                }
            )
    _write_csv(output_root / "peaks_scan.csv", scan_columns, scan_peak_rows)
    del replicate_aggregates, concentration_aggregates  # peak statistics use extracted scan values, not peak-of-mean.
    replicate_groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in scan_peak_rows:
        key = tuple(_cell(row.get(field)) for field in replicate_fields + band_columns)
        replicate_groups[key].append(row)
    replicate_peak_rows: list[dict[str, Any]] = []
    for key in sorted(replicate_groups):
        members = replicate_groups[key]
        values = np.asarray([float(member["peak_value"]) for member in members], dtype=float)
        values = values[np.isfinite(values)]
        observed = np.asarray([float(member["observed_shift_cm-1"]) for member in members], dtype=float)
        observed = observed[np.isfinite(observed)]
        replicate_peak_rows.append(
            {
                **{field: members[0].get(field) for field in replicate_fields + band_columns},
                "peak_value_mean": float(np.mean(values)) if len(values) else math.nan,
                "peak_value_sd": float(np.std(values, ddof=1)) if len(values) > 1 else math.nan,
                "observed_shift_mean_cm-1": float(np.mean(observed)) if len(observed) else math.nan,
                "n_scans": int(len(values)),
            }
        )
    _write_csv(
        output_root / "peaks_replicate.csv",
        replicate_fields
        + band_columns
        + ["peak_value_mean", "peak_value_sd", "observed_shift_mean_cm-1", "n_scans"],
        replicate_peak_rows,
    )
    concentration_groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in replicate_peak_rows:
        key = tuple(_cell(row.get(field)) for field in concentration_fields + band_columns)
        concentration_groups[key].append(row)
    concentration_peak_rows: list[dict[str, Any]] = []
    for key in sorted(concentration_groups):
        members = concentration_groups[key]
        values = np.asarray([float(member["peak_value_mean"]) for member in members], dtype=float)
        values = values[np.isfinite(values)]
        mean_value = float(np.mean(values)) if len(values) else math.nan
        sd_value = float(np.std(values, ddof=1)) if len(values) > 1 else math.nan
        concentration_peak_rows.append(
            {
                **{field: members[0].get(field) for field in concentration_fields + band_columns},
                "peak_value_mean_of_replicate_means": mean_value,
                "peak_value_sd_across_replicates": sd_value,
                "n_replicates": int(len(values)),
                "cv_percent": 100.0 * sd_value / mean_value
                if math.isfinite(sd_value) and mean_value != 0
                else math.nan,
            }
        )
    _write_csv(
        output_root / "peaks_concentration.csv",
        concentration_fields
        + band_columns
        + [
            "peak_value_mean_of_replicate_means",
            "peak_value_sd_across_replicates",
            "n_replicates",
            "cv_percent",
        ],
        concentration_peak_rows,
    )


def _prepare_output(path: Path, force: bool) -> None:
    if path.exists() and not path.is_dir():
        raise ConfigurationError(f"output_root exists but is not a directory: {path}")
    if path.exists() and any(path.iterdir()) and not force:
        raise ConfigurationError(
            f"output_root is not empty: {path}. Choose a new run folder or pass --force to overwrite named outputs."
        )
    path.mkdir(parents=True, exist_ok=True)


def _package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for distribution in ("numpy", "pandas", "scipy", "pybaselines", "PyYAML"):
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[distribution] = "not-installed"
    return versions


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def process_job(
    config_or_manifest: str | Path,
    *,
    output_root: str | Path | None = None,
    input_root: str | Path | None = None,
    profile_name: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Run the complete manifest-driven pipeline and return its provenance object."""
    started = datetime.now(timezone.utc)
    job = load_job(
        config_or_manifest,
        output_root=output_root,
        input_root=input_root,
        profile_name=profile_name,
    )
    _prepare_output(job.output_root, force)
    spectra, run_warnings = _load_manifest_spectra(job)
    if job.profile_name == "paper_2026":
        run_warnings.append(
            "DEPRECATED PROFILE NAME: paper_2026 is an alias of reference_2026. The manuscript does not report enough "
            "processing detail to claim exact regeneration of every published processed folder."
        )
    blank_settings = dict(job.profile.get("blank", {}))
    blank_stage = str(blank_settings.get("stage", "none")).lower()
    if blank_stage not in {"none", "raw", "processed"}:
        raise ConfigurationError("blank.stage must be 'none', 'raw', or 'processed'.")
    blanks = [spectrum for spectrum in spectra if _is_blank(spectrum, blank_settings)]
    if blank_stage != "none" and not blanks:
        raise ConfigurationError(
            "Blank subtraction is enabled, but no manifest row has a sample_type listed in blank.sample_types. "
            "Blank identity is never inferred from filenames."
        )

    prepared: list[Spectrum] = []
    acquisition_reports: dict[str, dict[str, Any]] = {}
    for spectrum in spectra:
        current = crop_spectrum(spectrum, dict(job.profile.get("crop", {})))
        if str(job.profile.get("axis_order", "increasing")).lower() == "increasing":
            current, axis_warnings = ensure_increasing_unique(current)
            if axis_warnings:
                current.import_metadata = dict(current.import_metadata)
                current.import_metadata.setdefault("processing_warnings", []).extend(axis_warnings)
        current, acquisition_report = scale_for_acquisition(
            current, dict(job.profile.get("effective_acquisition", {}))
        )
        prepared.append(current)
        acquisition_reports[current.record_id] = acquisition_report
    prepared, grid_report = align_spectra(prepared, dict(job.profile.get("grid", {})))
    by_id = {spectrum.record_id: spectrum for spectrum in prepared}
    blank_prepared = [by_id[spectrum.record_id] for spectrum in blanks]
    is_legacy = job.profile_name.startswith("legacy_")

    original_values = {spectrum.record_id: spectrum.y.copy() for spectrum in spectra}
    raw_values = {spectrum.record_id: spectrum.y.copy() for spectrum in prepared}
    blank_sources: dict[str, list[str]] = {spectrum.record_id: [] for spectrum in prepared}
    if blank_stage == "raw":
        for spectrum in prepared:
            if _is_blank(spectrum, blank_settings):
                continue
            reference, sources = _blank_reference(
                spectrum,
                blank_prepared,
                raw_values,
                blank_settings,
                legacy_constant_extrapolation=is_legacy,
            )
            spectrum.y = spectrum.y - reference
            blank_sources[spectrum.record_id] = sources

    preliminary: list[ProcessedSpectrum] = []
    preprocessed_values: dict[str, np.ndarray] = {}
    for spectrum in prepared:
        is_blank = _is_blank(spectrum, blank_settings)
        corrected, parameters, warnings = preprocess_signal(spectrum, job.profile, is_blank=is_blank)
        warnings = list(spectrum.import_metadata.get("processing_warnings", [])) + warnings
        preprocessed_values[spectrum.record_id] = corrected
        preliminary.append(
            ProcessedSpectrum(
                spectrum=spectrum,
                raw_y=original_values[spectrum.record_id].copy(),
                scaled_y=raw_values[spectrum.record_id].copy(),
                preprocessed_y=corrected.copy(),
                final_y=corrected.copy(),
                resolved_parameters={"effective_acquisition": acquisition_reports[spectrum.record_id], **parameters},
                warnings=warnings,
            )
        )

    processed: list[ProcessedSpectrum] = []
    for item in preliminary:
        spectrum = item.spectrum
        final = item.preprocessed_y.copy()
        if blank_stage == "processed" and not _is_blank(spectrum, blank_settings):
            reference, sources = _blank_reference(
                spectrum,
                blank_prepared,
                preprocessed_values,
                blank_settings,
                legacy_constant_extrapolation=is_legacy,
            )
            final = final - reference
            blank_sources[spectrum.record_id] = sources
        final, post_report = apply_post_blank_baseline(
            final, dict(job.profile.get("post_blank_baseline", {}))
        )
        final, normalization_report = normalize_signal(
            spectrum.x, final, dict(job.profile.get("normalization", {}))
        )
        item.final_y = final
        item.resolved_parameters["blank"] = {
            "stage": blank_stage,
            "strategy": blank_settings.get("strategy", "mean"),
            "reference_records": blank_sources[spectrum.record_id],
        }
        item.resolved_parameters["post_blank_baseline"] = post_report
        item.resolved_parameters["normalization"] = normalization_report
        processed.append(item)

    metadata_columns = _metadata_columns([item.spectrum for item in processed])
    replicate_fields, concentration_fields = _group_fields(job.profile, metadata_columns)
    replicate_aggregates, concentration_aggregates, processed_filenames = _write_spectral_outputs(
        job.output_root,
        processed,
        metadata_columns,
        replicate_fields,
        concentration_fields,
        job.profile_name,
    )
    _write_peak_outputs(
        job.output_root,
        processed,
        replicate_aggregates,
        concentration_aggregates,
        metadata_columns,
        replicate_fields,
        concentration_fields,
        job.profile,
    )

    resolved_columns = [
        "record_id",
        "file",
        "source_sha256",
        "source_intensity_column",
        "source_intensity_column_index",
        "processed_file",
        *[column for column in metadata_columns if column != "file"],
    ]
    _write_csv(
        job.output_root / "resolved_manifest.csv",
        resolved_columns,
        (
            {
                "record_id": item.spectrum.record_id,
                "file": item.spectrum.manifest_metadata.get("file"),
                "source_sha256": item.spectrum.source_sha256,
                "source_intensity_column": item.spectrum.source_column,
                "source_intensity_column_index": item.spectrum.source_column_index,
                "processed_file": processed_filenames[item.spectrum.record_id],
                **item.spectrum.manifest_metadata,
            }
            for item in sorted(processed, key=lambda value: value.spectrum.record_id)
        ),
    )
    _write_csv(
        job.output_root / "processing_report.csv",
        [
            "record_id",
            "file",
            "source_intensity_column",
            "points",
            "x_min_cm-1",
            "x_max_cm-1",
            "blank_reference_records",
            "warnings",
            "resolved_parameters_json",
        ],
        (
            {
                "record_id": item.spectrum.record_id,
                "file": item.spectrum.manifest_metadata.get("file"),
                "source_intensity_column": item.spectrum.source_column,
                "points": len(item.spectrum.x),
                "x_min_cm-1": float(np.min(item.spectrum.x)),
                "x_max_cm-1": float(np.max(item.spectrum.x)),
                "blank_reference_records": ";".join(blank_sources[item.spectrum.record_id]),
                "warnings": " | ".join(item.warnings),
                "resolved_parameters_json": _canonical_json(item.resolved_parameters),
            }
            for item in sorted(processed, key=lambda value: value.spectrum.record_id)
        ),
    )
    _write_json(
        job.output_root / "source_metadata.json",
        {
            item.spectrum.record_id: {
                "file": item.spectrum.manifest_metadata.get("file"),
                "source_sha256": item.spectrum.source_sha256,
                "source_intensity_column": item.spectrum.source_column,
                "import": item.spectrum.import_metadata,
                "manifest": item.spectrum.manifest_metadata,
            }
            for item in sorted(processed, key=lambda value: value.spectrum.record_id)
        },
    )

    spectrum_inputs = {
        spectrum.source_path: spectrum.source_sha256 for spectrum in spectra
    }
    input_entries = [
        {
            "role": "spectrum",
            "path_base": "input_root",
            "path": path.relative_to(job.input_root).as_posix(),
            "sha256": digest,
            "bytes": path.stat().st_size,
        }
        for path, digest in sorted(spectrum_inputs.items(), key=lambda item: item[0].relative_to(job.input_root).as_posix())
    ]
    for role, source_path in (("manifest", job.manifest_path), ("configuration", job.config_path)):
        if role == "configuration" and source_path == job.manifest_path:
            continue
        try:
            recorded_path = source_path.relative_to(job.input_root).as_posix()
            path_base = "input_root"
        except ValueError:
            try:
                recorded_path = Path(os.path.relpath(source_path, job.output_root)).as_posix()
            except ValueError as exc:
                raise ConfigurationError(
                    f"{role.capitalize()} and output_root are on different filesystem volumes. "
                    "Move the configuration into the repository so provenance can remain portable and private."
                ) from exc
            path_base = "output_root"
        input_entries.append(
            {
                "role": role,
                "path_base": path_base,
                "path": recorded_path,
                "sha256": sha256_file(source_path),
                "bytes": source_path.stat().st_size,
            }
        )

    generated_relative_paths = {
        "spectra_scan.csv",
        "spectra_replicate.csv",
        "spectra_concentration.csv",
        "peaks_scan.csv",
        "peaks_replicate.csv",
        "peaks_concentration.csv",
        "resolved_manifest.csv",
        "processing_report.csv",
        "source_metadata.json",
        *processed_filenames.values(),
    }
    output_paths = [job.output_root / relative for relative in sorted(generated_relative_paths, key=str.casefold)]
    output_entries = [
        {
            "role": "output",
            "path_base": "output_root",
            "path": path.relative_to(job.output_root).as_posix(),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        for path in output_paths
    ]
    _write_csv(
        job.output_root / "provenance_files.csv",
        ["role", "path_base", "path", "sha256", "bytes"],
        input_entries + output_entries,
    )
    provenance_path = job.output_root / "provenance_files.csv"
    output_entries.append(
        {
            "role": "output",
            "path_base": "output_root",
            "path": provenance_path.relative_to(job.output_root).as_posix(),
            "sha256": sha256_file(provenance_path),
            "bytes": provenance_path.stat().st_size,
        }
    )

    try:
        input_root_from_run = Path(os.path.relpath(job.input_root, job.output_root)).as_posix()
    except ValueError as exc:
        raise ConfigurationError(
            "input_root and output_root are on different filesystem volumes; portable provenance cannot be written."
        ) from exc
    manifest_entry = next(item for item in input_entries if item["role"] == "manifest")
    resolved_config = {
        "schema_version": SCHEMA_VERSION,
        "profile": job.profile_name,
        "input_root_from_run": input_root_from_run,
        "output_root": ".",
        "manifest": {"path_base": manifest_entry["path_base"], "path": manifest_entry["path"]},
        "resolved_profile": job.profile,
    }
    fingerprint_payload = {
        "configuration": resolved_config,
        "manifest_sha256": sha256_file(job.manifest_path),
        "spectra": [{"path": item["path"], "sha256": item["sha256"]} for item in input_entries if item["role"] == "spectrum"],
    }
    run_id = hashlib.sha256(_canonical_json(fingerprint_payload).encode("utf-8")).hexdigest()[:20]
    completed = datetime.now(timezone.utc)
    run = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "status": "complete",
        "started_utc": started.isoformat(),
        "completed_utc": completed.isoformat(),
        "duration_seconds": (completed - started).total_seconds(),
        "software": {
            "package": "auagbc-sers",
            "version": __version__,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "dependencies": _package_versions(),
        },
        "configuration": resolved_config,
        "grid": grid_report,
        "counts": {
            "manifest_rows": len(job.manifest),
            "source_files": len(spectrum_inputs),
            "scan_spectra": len(processed),
            "blank_spectra": len(blank_prepared),
            "replicate_spectra": len(replicate_aggregates),
            "concentration_spectra": len(concentration_aggregates),
        },
        "warnings": run_warnings,
        "files": {"inputs": input_entries, "outputs": output_entries},
    }
    _write_json(job.output_root / "run.json", run)
    returned = dict(run)
    returned["runtime_output_root"] = str(job.output_root)
    return returned


def verify_run(
    run_json: str | Path,
    *,
    input_root: str | Path | None = None,
    verify_inputs: bool = True,
) -> dict[str, Any]:
    """Recalculate recorded hashes; raise :class:`VerificationError` on drift."""
    candidate = Path(run_json).expanduser().resolve()
    if candidate.is_dir():
        candidate = candidate / "run.json"
    if not candidate.is_file():
        raise VerificationError(f"run.json does not exist: {candidate}")
    try:
        run = json.loads(candidate.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise VerificationError(f"Could not read provenance file {candidate}: {exc}") from exc
    output_root = candidate.parent
    configured_input = (
        Path(input_root).expanduser().resolve()
        if input_root
        else (output_root / run["configuration"]["input_root_from_run"]).resolve()
    )
    checks: list[dict[str, Any]] = []
    failures: list[str] = []
    for entry in run.get("files", {}).get("outputs", []):
        path = output_root / entry["path"]
        actual = sha256_file(path) if path.is_file() else None
        valid = actual == entry["sha256"]
        checks.append({"role": "output", "path": entry["path"], "expected": entry["sha256"], "actual": actual, "valid": valid})
        if not valid:
            failures.append(f"output {entry['path']}")
    if verify_inputs:
        for entry in run.get("files", {}).get("inputs", []):
            if entry.get("path_base") == "input_root" or entry["role"] == "spectrum":
                path = configured_input / entry["path"]
            elif entry.get("path_base") == "output_root":
                path = output_root / entry["path"]
            else:
                raise VerificationError(
                    f"Unknown provenance path_base {entry.get('path_base')!r} for {entry.get('path')!r}."
                )
            actual = sha256_file(path) if path.is_file() else None
            valid = actual == entry["sha256"]
            checks.append({"role": entry["role"], "path": entry["path"], "expected": entry["sha256"], "actual": actual, "valid": valid})
            if not valid:
                failures.append(f"{entry['role']} {entry['path']}")
    report = {
        "run_id": run.get("run_id"),
        "valid": not failures,
        "checked": len(checks),
        "failures": failures,
        "checks": checks,
    }
    if failures:
        raise VerificationError("Checksum verification failed for: " + ", ".join(failures))
    return report
