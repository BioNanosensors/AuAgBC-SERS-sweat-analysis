"""Build the repository data snapshot and its audit metadata.

This script is intentionally conservative.  It never edits the supplied
archives or the audit workbench.  Every CSV from ``Raman_spectra_data`` is
copied into a quarantine snapshot, while a small, explicitly mapped subset is
also copied into publication-facing locations. Absolute Windows user-home
paths are replaced with repository-relative paths where possible and otherwise
redacted with role placeholders.

Run from anywhere with::

    python scripts/prepare_repository_data.py

Only Python's standard library is required.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import re
import shutil
import tokenize
from collections import Counter, defaultdict
from itertools import zip_longest
from pathlib import Path
from typing import Iterable

try:
    from proof_of_concept_mapping import (
        PUBLICATION_FILES as PROOF_OF_CONCEPT_PUBLICATION_FILES,
        PUBLICATION_MANIFEST_NOTE as PROOF_OF_CONCEPT_MANIFEST_NOTE,
        correct_publication_header,
        write_mapping_sidecars,
    )
except ModuleNotFoundError:  # Supports importing this script from the repo root.
    from scripts.proof_of_concept_mapping import (
        PUBLICATION_FILES as PROOF_OF_CONCEPT_PUBLICATION_FILES,
        PUBLICATION_MANIFEST_NOTE as PROOF_OF_CONCEPT_MANIFEST_NOTE,
        correct_publication_header,
        write_mapping_sidecars,
    )


RAMAN_ARCHIVE_SHA256 = "1b8460a5230bc74e5fe72d47d05d9172ebc9fe48b3024c2ee9e9b44d5fb4680a"
RAMAN_ARCHIVE_BYTES = 132_298_137
SCRIPTS_ARCHIVE_SHA256 = "9c0a8852ea5457911f0860b36ce86cd52783e4b4d6889834366ed941920f119a"
SCRIPTS_ARCHIVE_BYTES = 293_315
MANUSCRIPT_ARCHIVE_SHA256 = "c73c0126f6b5c2d88f5f4bfd4bed77349b2590f92673ab9448f3b9fcdcd5ba50"
MANUSCRIPT_ARCHIVE_BYTES = 61_666
RENDERED_MANUSCRIPT_ARCHIVE_SHA256 = "0dd193d01bd36f0dace705a5003d85eacd686f8bca5698d1f64ef04e2d27c4a9"
RENDERED_MANUSCRIPT_ARCHIVE_BYTES = 61_601_494
THESIS_PDF_SHA256 = "fcbd81d10f444262b4f75007927d604f478dd4ff3c7c9326c897bd7fdfe3e359"
THESIS_PDF_BYTES = 16_886_679
CONFIRMED_4ATP_BLANK_REPOSITORY_PATH = Path(
    "data/raw/4atp/optimisation/750_5_5_H/Blanck_AABC_750_5_5_H.csv"
)
CONFIRMED_4ATP_BLANK_SOURCE_PATH = (
    "Test 4-ATP/24-09-24/Blank/Blanck_AABC_750_5_5_H.csv"
)
CONFIRMED_4ATP_BLANK_SHA256 = "e36f0ad7a57ebab8cba038309284305cfecc98d1586499fe73e266e301257dd9"
CONFIRMED_4ATP_BLANK_BYTES = 27_476


# Archive paths use their original names; destinations are stable, lowercase,
# publication-facing names agreed with the manuscript data map.
ARCHIVE_PUBLICATION_MAP = {
    "Analytical Enhancement/Processed summary/4_ATP_AEF.csv":
        "analytical_enhancement/aef_summary.csv",
    "Blind samples/Processed summary/4_ATP_blind_samples.csv":
        "blind_samples/blind_predictions.csv",
    "Calibration curve/Processed summary/final_spectra_by_accumulation_wide_ascii.csv":
        "calibration_curve/final_spectra_by_accumulation_wide.csv",
    "Calibration curve/Processed summary/replicate_mean_sd_by_shift.csv":
        "calibration_curve/replicate_mean_sd_by_shift.csv",
    "Calibration curve/Processed summary/4_ATP_750_5_5_L_CC.csv":
        "calibration_curve/calibration_at_selected_shifts.csv",
    "Calibration curve/Processed summary/summary_by_concentration.csv":
        "calibration_curve/summary_by_concentration.csv",
    "Optimisation/4_ATP_500_5_5_L.csv": "optimisation/4atp_500_5_5_l.csv",
    "Optimisation/4_ATP_750_5_5_H.csv": "optimisation/4atp_750_5_5_h.csv",
    "Optimisation/4_ATP_750_5_5_M.csv": "optimisation/4atp_750_5_5_m.csv",
}


# The paper project contains the authoritative proof-of-concept exports.  The
# archive copies remain available under quarantine for comparison.
PROJECT_PUBLICATION_MAP = {
    "RP_AS_HS.csv": "proof_of_concept/portable_sweat_summary.csv",
    "RM_AS_HS.csv": "proof_of_concept/benchtop_sweat_summary.csv",
    "AuAgBC_AS_HS_Benchtop_vs_Portable.csv":
        "proof_of_concept/benchtop_vs_portable_normalized.csv",
}


REPORT_MAP = {
    "best_curated_raw_column_matches.csv": "provenance/raw_to_master_best_matches.csv",
    "concentration_label_mismatches.csv": "provenance/concentration_label_conflicts.csv",
    "curated_group_master_origin_summary.csv": "provenance/master_origin_summary.csv",
    "curated_exact_matches_to_masters.csv": "provenance/exact_file_matches.csv",
    "duplicate_groups.csv": "provenance/duplicate_content_groups.csv",
    "inventory_summary.json": "provenance/inventory_summary.json",
    "column_match_summary.json": "provenance/column_match_summary.json",
}


USER_HOME_BACKSLASH = re.compile(rb"(?i)[A-Z]:\\Users\\[^\\/\r\n,\"]+[\\/]")
# JSON escapes each Windows separator, so sanitize that representation before
# applying the ordinary path expression below.
USER_HOME_JSON_BACKSLASH = re.compile(rb"(?i)[A-Z]:\\\\Users\\\\[^\\/\r\n,\"]+\\\\")
USER_HOME_SLASH = re.compile(rb"(?i)[A-Z]:/Users/[^/\r\n,\"]+/")
ABSOLUTE_PATH = re.compile(rb"(?i)(?:[A-Z]:[\\/]|/(?:home|Users)/)")

PORTABLE_PATH_TABLES = {
    "Optimisation/500_5_5_L/_out_raman/final_spectra_by_accumulation_long.csv": "500_5_5_L",
    "Optimisation/500_5_5_L/_out_raman/peak_table_per_spectrum.csv": "500_5_5_L",
    "Optimisation/750_5_5_M/_out_raman/final_spectra_by_accumulation_long.csv": "750_5_5_M",
    "Optimisation/750_5_5_M/_out_raman/peak_table_per_spectrum.csv": "750_5_5_M",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def validate_confirmed_4atp_blank(repository_root: Path) -> Path:
    """Return the committed blank after verifying its immutable source identity."""
    path = repository_root / CONFIRMED_4ATP_BLANK_REPOSITORY_PATH
    if not path.is_file():
        raise FileNotFoundError(f"Author-confirmed 4-ATP blank is missing: {path}")
    size = path.stat().st_size
    if size != CONFIRMED_4ATP_BLANK_BYTES:
        raise RuntimeError(
            f"Author-confirmed 4-ATP blank has {size} bytes; "
            f"expected {CONFIRMED_4ATP_BLANK_BYTES}: {path}"
        )
    digest = sha256_file(path)
    if digest != CONFIRMED_4ATP_BLANK_SHA256:
        raise RuntimeError(
            f"Author-confirmed 4-ATP blank has SHA256 {digest}; "
            f"expected {CONFIRMED_4ATP_BLANK_SHA256}: {path}"
        )
    return path


def sanitize_bytes(data: bytes) -> tuple[bytes, int]:
    """Remove private Windows user-home prefixes while retaining useful tails."""
    data, count_json_backslash = USER_HOME_JSON_BACKSLASH.subn(lambda _: b"<USER_HOME>\\\\", data)
    data, count_backslash = USER_HOME_BACKSLASH.subn(lambda _: b"<USER_HOME>\\", data)
    data, count_slash = USER_HOME_SLASH.subn(b"<USER_HOME>/", data)
    return data, count_json_backslash + count_backslash + count_slash


def copy_sanitized(source: Path, destination: Path) -> tuple[str, str, int, int, int]:
    original = source.read_bytes()
    clean, substitutions = sanitize_bytes(original)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(clean)
    return (
        sha256_bytes(original),
        sha256_bytes(clean),
        len(original),
        len(clean),
        substitutions,
    )


def compare_sanitized_csv(source: Path, destination: Path) -> tuple[int, str, int]:
    """Return rows checked, changed column names, and non-path cell changes."""
    with source.open("r", encoding="utf-8-sig", newline="") as source_handle, destination.open(
        "r", encoding="utf-8-sig", newline=""
    ) as destination_handle:
        source_reader = csv.reader(source_handle)
        destination_reader = csv.reader(destination_handle)
        source_header = next(source_reader, [])
        destination_header = next(destination_reader, [])
        if source_header != destination_header:
            return 0, "header", 1
        changed_columns: set[str] = set()
        non_path_changes = 0
        rows_checked = 0
        for source_row, destination_row in zip_longest(source_reader, destination_reader):
            rows_checked += 1
            if source_row is None or destination_row is None or len(source_row) != len(destination_row):
                non_path_changes += 1
                continue
            for index, (before, after) in enumerate(zip(source_row, destination_row)):
                if before == after:
                    continue
                column = source_header[index] if index < len(source_header) else f"column_{index + 1}"
                changed_columns.add(column)
                if column.casefold() not in {"file", "path", "source_file", "source_path"}:
                    non_path_changes += 1
        return rows_checked, ";".join(sorted(changed_columns)), non_path_changes


def make_file_column_portable(path: Path, acquisition: str) -> int:
    """Replace a generated table's machine-local ``file`` cells with repository paths."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows or "file" not in rows[0]:
        raise ValueError(f"Expected a 'file' column in generated table: {path}")
    file_index = rows[0].index("file")
    changed = 0
    prefix = f"data/quarantine/legacy_snapshot/Optimisation/{acquisition}/"
    for row in rows[1:]:
        if file_index >= len(row) or not row[file_index].strip():
            continue
        basename = row[file_index].replace("\\", "/").rsplit("/", 1)[-1]
        portable = prefix + basename
        if row[file_index] != portable:
            row[file_index] = portable
            changed += 1
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerows(rows)
    return changed


def reset_generated_directory(path: Path, repository_root: Path) -> None:
    resolved = path.resolve()
    if not resolved.is_relative_to(repository_root.resolve()):
        raise RuntimeError(f"Refusing to clear a path outside the repository: {resolved}")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def repository_path(path: Path, repository_root: Path) -> str:
    return path.relative_to(repository_root).as_posix()


def source_rel(path: Path, source_root: Path) -> str:
    return path.relative_to(source_root).as_posix()


def quarantine_status(relative_path: str) -> tuple[str, str, str]:
    """Return status, role, and a short reason for an archived CSV."""
    folded = relative_path.casefold()
    name = Path(relative_path).name.casefold()
    top = relative_path.split("/", 1)[0]

    if top == "Stability":
        return (
            "provenance_conflict",
            "raw_spectrum" if "/processed spectra/" not in folded else "processed_spectrum",
            "Stability labels and cross-date source identities contain documented conflicts.",
        )
    if top == "Blind samples" and "processed summary" not in folded:
        return (
            "provenance_conflict",
            "raw_spectrum" if "/original spectra/" in folded else "processed_spectrum",
            "Blind raw lineage is incomplete and its blank reference is shared with unrelated sets.",
        )
    if top == "Proof of concept" and "/portable raman/" in folded:
        return (
            "provenance_conflict",
            "raw_spectrum" if "/original spectra/" in folded else "processed_spectrum",
            "Portable proof-of-concept filenames conflict with embedded Name/Tag metadata.",
        )
    if top == "Optimisation" and "/750_5_5_m/processed spectra/" in folded:
        return (
            "provenance_conflict",
            "processed_spectrum",
            "This legacy derivative set has no same-stem raw partners in the supplied archive.",
        )
    shared_blank_related = (
        name.startswith("blank_rep")
        or "_blank_subtracted_processed" in name
        or name == "blank_sigma_versions.csv"
    )
    if shared_blank_related and top in {"Calibration curve", "Optimisation"}:
        return (
            "provenance_conflict",
            "raw_spectrum" if "processed" not in folded else "processed_spectrum",
            "Shared blank identity is unresolved; exact intensity matches link the "
            "15-channel series to ten columns stored in Test HS master exports and "
            "five stored in a Test 4-ATP master export. Storage context is not proof "
            "of sample identity. See metadata/provenance_corrections.csv.",
        )
    if "processed" in folded or "/_out_raman/" in folded or top == "Analytical Enhancement" and "/processed" in folded:
        role = "processed_summary" if "summary" in folded else "processed_spectrum"
        return "legacy_derived", role, "Historical derivative retained without a complete executable lineage claim."
    if top == "Optimisation" and relative_path.count("/") == 1:
        return "legacy_derived", "processed_summary", "Historical summary selected from the supplied archive."
    if top == "Hand-held spectrometer calibration" and name == "si_calibration.csv":
        return "legacy_derived", "instrument_calibration", "Historical calibrated axis retained with its raw pair."
    if "original spectra" in folded or top in {"Optimisation", "Stability"}:
        return "raw_unverified", "raw_spectrum", "Raw-like spectrum retained; filename identity is not treated as verified."
    if name == "060624_si_original_file.csv":
        return "raw_unverified", "instrument_calibration", "Original silicon calibration spectrum."
    return "legacy_derived", "supporting_table", "Historical supporting CSV retained in the quarantine snapshot."


def is_raw_like(relative_path: str) -> bool:
    parts = relative_path.split("/")
    folded = relative_path.casefold()
    name = parts[-1].casefold()
    if name == "manifest.csv":
        return False
    if "/original spectra/" in folded:
        return True
    if relative_path == "Hand-held spectrometer calibration/060624_Si_original_file.csv":
        return True
    if parts[0] == "Optimisation" and len(parts) == 3 and parts[1] in {
        "500_5_5_L", "750_5_5_H", "750_5_5_M"
    }:
        return True
    if parts[0] == "Stability" and len(parts) == 3:
        return True
    return False


def record_group(relative_path: str) -> str:
    parts = relative_path.split("/")
    top = parts[0]
    if top == "Optimisation" and len(parts) > 2:
        return f"optimisation_{parts[1].casefold()}"
    if top == "Stability" and len(parts) > 2:
        date_map = {"19_05_24": "2024-05-19", "03_07_24": "2024-07-03", "24_09_24": "2024-09-24"}
        return f"stability_{date_map.get(parts[1], parts[1])}"
    if top == "Proof of concept" and len(parts) > 2:
        return f"proof_of_concept_{parts[1].replace(' Raman', '').replace(' ', '_').casefold()}"
    return top.replace("-", "_").replace(" ", "_").casefold()


def sample_type(filename: str) -> str:
    folded = filename.casefold().replace("-", "_")
    if "blank" in folded:
        return "blank"
    if "4atp" in folded or "4_atp" in folded or "4 atp" in filename.casefold():
        return "4atp"
    if re.search(r"(?:^|_)as(?:_|\.)", folded):
        return "artificial_sweat"
    if re.search(r"(?:^|_)hs(?:_|\.)", folded):
        return "human_sweat"
    if re.search(r"(?:^|_)si(?:_|\.)", folded) or "silicon" in folded:
        return "silicon"
    return ""


def concentration_molar(filename: str) -> str:
    text = filename.replace("µ", "u").replace("μ", "u")
    exponent_patterns = (
        r"10\^\s*-\s*(\d+)\s*M",
        r"10-\s*(\d+)\s*M",
        r"\^\s*-\s*(\d+)\s*M",
    )
    for pattern in exponent_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return f"{10.0 ** (-int(match.group(1))):.12g}"
    # An underscore is a regex "word" character, so ``\b`` does not match the
    # common ``100fM_rep1`` form.  Stop before any non-alphanumeric separator
    # instead, while still rejecting units embedded in a longer token.
    match = re.search(
        r"(?<![A-Za-z0-9^])([0-9]+(?:\.[0-9]+)?)([fpnumu]?)M(?=[^A-Za-z0-9]|$)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    prefixes = {"": 1.0, "f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3}
    value = float(match.group(1)) * prefixes[match.group(2).casefold()]
    return f"{value:.12g}"


def integer_token(filename: str, token: str) -> str:
    match = re.search(rf"(?:^|_){re.escape(token)}(\d+)(?:_|\.|$)", filename, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def explicit_acquisition(relative_path: str) -> str:
    match = re.search(r"(?:^|[/_])(500|750)_5_5_([LMH])(?:[/_.]|$)", relative_path, flags=re.IGNORECASE)
    return f"{match.group(1)}_5_5_{match.group(2).upper()}" if match else ""


def load_master_instruments(report_path: Path) -> dict[str, str]:
    """Use exact audit matches only; conflicting source types remain blank."""
    candidates: dict[str, set[str]] = defaultdict(set)
    if not report_path.is_file():
        return {}
    with report_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            path = row.get("curated_path", "")
            prefix = "Raman_spectra_data/"
            if path.startswith(prefix):
                path = path[len(prefix):]
            source = row.get("master_source", "")
            if source in {"master_portable", "master_benchtop"}:
                candidates[path].add(source)
    result: dict[str, str] = {}
    for path, values in candidates.items():
        if len(values) == 1:
            value = next(iter(values))
            result[path] = "portable_raman" if value == "master_portable" else "benchtop_raman"
    return result


def load_numeric_column_counts(inventory_path: Path) -> dict[str, int]:
    """Return audited numeric-column counts for curated CSVs when available."""
    result: dict[str, int] = {}
    if not inventory_path.is_file():
        return result
    with inventory_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("source") != "curated":
                continue
            relative = row.get("relative_path", "")
            prefix = "Raman_spectra_data/"
            if relative.startswith(prefix):
                relative = relative[len(prefix):]
            try:
                result[relative] = int(float(row.get("numeric_columns", "")))
            except (TypeError, ValueError):
                continue
    return result


def explicit_instrument(relative_path: str, matched: dict[str, str]) -> str:
    folded = relative_path.casefold()
    if "portable raman" in folded or relative_path.startswith("Hand-held spectrometer calibration/"):
        return "portable_raman"
    if "benchtop raman" in folded:
        return "benchtop_raman"
    return matched.get(relative_path, "")


def build_raw_processing_manifest(
    source_root: Path,
    metadata_root: Path,
    best_match_report: Path,
    file_inventory_report: Path,
    repository_root: Path,
) -> int:
    matched_instruments = load_master_instruments(best_match_report)
    numeric_columns = load_numeric_column_counts(file_inventory_report)
    rows: list[dict[str, object]] = []
    for source in sorted(source_root.rglob("*.csv"), key=lambda item: item.as_posix().casefold()):
        relative = source_rel(source, source_root)
        if not is_raw_like(relative):
            continue
        status, _, _ = quarantine_status(relative)
        filename = source.name
        replicate = integer_token(filename, "rep")
        if not replicate and relative.startswith("Blind samples/"):
            replicate = integer_token(filename, "S")
        accumulation = integer_token(filename, "acc")
        if not accumulation:
            accumulation = "expanded_column" if numeric_columns.get(relative, 0) > 2 else "unresolved"
        rows.append({
            "file": f"data/quarantine/legacy_snapshot/{relative}",
            "record_group": record_group(relative),
            "sample_type": sample_type(filename) or "unresolved",
            "concentration_molar": "" if "blank" in filename.casefold() else concentration_molar(filename),
            "replicate": replicate or "unresolved",
            "accumulation": accumulation,
            "instrument": explicit_instrument(relative, matched_instruments) or "unresolved",
            "acquisition": explicit_acquisition(relative),
            "provenance_status": status,
        })
    validate_confirmed_4atp_blank(repository_root)
    rows.append({
        "file": CONFIRMED_4ATP_BLANK_REPOSITORY_PATH.as_posix(),
        "record_group": "optimisation_750_5_5_h_confirmed_blank",
        "sample_type": "blank",
        "concentration_molar": "",
        "replicate": "unresolved",
        "accumulation": "expanded_column",
        "instrument": "portable_raman",
        "acquisition": "750_5_5_H",
        "provenance_status": "raw_author_confirmed",
    })
    rows.sort(key=lambda row: str(row["file"]).casefold())
    write_csv(
        metadata_root / "raw_processing_manifest.csv",
        [
            "file", "record_group", "sample_type", "concentration_molar", "replicate",
            "accumulation", "instrument", "acquisition", "provenance_status",
        ],
        rows,
    )
    return len(rows)


def build_legacy_script_inventory(legacy_scripts_root: Path, destination: Path) -> int:
    rows: list[dict[str, object]] = []
    if legacy_scripts_root.is_dir():
        for path in sorted(legacy_scripts_root.rglob("*.py"), key=lambda item: item.as_posix().casefold()):
            raw = path.read_bytes()
            parses = False
            try:
                with tokenize.open(path) as handle:
                    ast.parse(handle.read(), filename=str(path))
                parses = True
            except (SyntaxError, UnicodeDecodeError, OSError):
                parses = False
            rows.append({
                "relative_path": path.relative_to(legacy_scripts_root).as_posix(),
                "sha256": sha256_bytes(raw),
                "bytes": len(raw),
                "ast_parses": str(parses).lower(),
                "contains_absolute_path": str(bool(ABSOLUTE_PATH.search(raw))).lower(),
                "status": "superseded_not_distributed",
            })
    write_csv(
        destination,
        ["relative_path", "sha256", "bytes", "ast_parses", "contains_absolute_path", "status"],
        rows,
    )
    return len(rows)


def manuscript_tables(publication_root: Path) -> list[tuple[Path, str]]:
    common = {"status": "publication_snapshot", "source": "manuscript"}
    calibration = publication_root / "paper_tables" / "calibration_parameters.csv"
    write_csv(
        calibration,
        [
            "shift_cm-1", "Y0", "k", "R2", "LOD_M", "LOQ_M", "CV_mean_pct", "CV_sd_pct",
            "delta_log10C_mean", "delta_log10C_sd", "status", "source",
        ],
        [
            {"shift_cm-1": 392, "Y0": 5.7e3, "k": 0.3, "R2": 0.92, "LOD_M": 2.5e-16, "LOQ_M": 2.5e-13,
             "CV_mean_pct": 38.8, "CV_sd_pct": 24.1, "delta_log10C_mean": -3.76, "delta_log10C_sd": 1.46, **common},
            {"shift_cm-1": 1078, "Y0": 2.5e4, "k": 0.5, "R2": 0.99, "LOD_M": 2.3e-12, "LOQ_M": 2.5e-10,
             "CV_mean_pct": 41.5, "CV_sd_pct": 21.3, "delta_log10C_mean": -1.28, "delta_log10C_sd": 1.35, **common},
            {"shift_cm-1": 1590, "Y0": 5.8e4, "k": 0.5, "R2": 0.98, "LOD_M": 1.2e-11, "LOQ_M": 4.1e-9,
             "CV_mean_pct": 35.2, "CV_sd_pct": 18.6, "delta_log10C_mean": -1.69, "delta_log10C_sd": 1.27, **common},
        ],
    )

    stability = publication_root / "paper_tables" / "stability_parameters.csv"
    write_csv(
        stability,
        [
            "reported_day", "measurement_date", "actual_elapsed_days", "Y0", "k", "R2", "LOD_M", "LOQ_M",
            "CV_mean_pct", "CV_sd_pct", "status", "source",
        ],
        [
            {"reported_day": 1, "measurement_date": "2024-05-19", "actual_elapsed_days": 0, "Y0": 7.403e4,
             "k": 0.30, "R2": 0.757, "LOD_M": 2.37e-15, "LOQ_M": 1.28e-12, "CV_mean_pct": 15.68, "CV_sd_pct": 11.5, **common},
            {"reported_day": 45, "measurement_date": "2024-07-03", "actual_elapsed_days": 45, "Y0": 1.943e5,
             "k": 0.58, "R2": 0.95, "LOD_M": 5.95e-10, "LOQ_M": 1.55e-8, "CV_mean_pct": 30.79, "CV_sd_pct": 20.3, **common},
            {"reported_day": "130_reported", "measurement_date": "2024-09-24", "actual_elapsed_days": 128, "Y0": 8.78e4,
             "k": 0.45, "R2": 0.94, "LOD_M": 6.98e-11, "LOQ_M": 4.68e-9, "CV_mean_pct": 35.79, "CV_sd_pct": 20.12, **common},
        ],
    )

    aef = publication_root / "paper_tables" / "aef_parameters.csv"
    write_csv(
        aef,
        [
            "shift_cm-1", "sers_intensity", "sers_concentration_M", "raman_intensity",
            "raman_concentration_M", "analytical_enhancement_factor", "status", "source",
        ],
        [{
            "shift_cm-1": 1590,
            "sers_intensity": 1613.96,
            "sers_concentration_M": 1e-15,
            "raman_intensity": 1171.36,
            "raman_concentration_M": 1e-2,
            "analytical_enhancement_factor": 1.38e13,
            **common,
        }],
    )
    return [
        (calibration, "Manuscript calibration-parameter table transcribed explicitly."),
        (stability, "Manuscript stability table; reported day 130 is 128 elapsed calendar days."),
        (aef, "Manuscript analytical-enhancement-factor inputs and result."),
    ]


def write_reference_metadata(metadata_root: Path) -> None:
    write_csv(
        metadata_root / "source_archives.csv",
        ["source_name", "sha256", "bytes", "hash_status", "role", "note"],
        [
            {
                "source_name": "Raman_spectra_data.zip",
                "sha256": RAMAN_ARCHIVE_SHA256,
                "bytes": RAMAN_ARCHIVE_BYTES,
                "hash_status": "verified_before_extraction",
                "role": "submitted_data_archive",
                "note": "Source of the complete quarantined CSV snapshot.",
            },
            {
                "source_name": "Scripts.zip",
                "sha256": SCRIPTS_ARCHIVE_SHA256,
                "bytes": SCRIPTS_ARCHIVE_BYTES,
                "hash_status": "verified_before_extraction",
                "role": "legacy_script_archive",
                "note": "Inventoried only; superseded scripts are not distributed.",
            },
            {
                "source_name": "Tex.zip",
                "sha256": MANUSCRIPT_ARCHIVE_SHA256,
                "bytes": MANUSCRIPT_ARCHIVE_BYTES,
                "hash_status": "verified_source_file",
                "role": "method_definition_source",
                "note": (
                    "Submitted manuscript source used to confirm the analytical blank definition "
                    "and portable 4-ATP acquisition settings; not redistributed here."
                ),
            },
            {
                "source_name": "PDFs.zip",
                "sha256": RENDERED_MANUSCRIPT_ARCHIVE_SHA256,
                "bytes": RENDERED_MANUSCRIPT_ARCHIVE_BYTES,
                "hash_status": "verified_source_file",
                "role": "rendered_manuscript_source",
                "note": (
                    "Submitted rendered article and supporting information used to visually "
                    "confirm the method statements; not redistributed here."
                ),
            },
            {
                "source_name": "Thesis_MCeIM_DPV.pdf",
                "sha256": THESIS_PDF_SHA256,
                "bytes": THESIS_PDF_BYTES,
                "hash_status": "verified_source_file",
                "role": "method_definition_source",
                "note": (
                    "Submitted thesis used as a corroborating methodological source from the same "
                    "project; not redistributed here."
                ),
            },
            {
                "source_name": "Blanck_AABC_750_5_5_H.csv",
                "sha256": CONFIRMED_4ATP_BLANK_SHA256,
                "bytes": CONFIRMED_4ATP_BLANK_BYTES,
                "hash_status": "verified_source_file",
                "role": "author_confirmed_4atp_blank_source",
                "note": (
                    "Exact unchanged copy from Test 4-ATP/24-09-24/Blank in the expanded portable "
                    "master collection; distributed under data/raw for high-power optimisation only."
                ),
            },
            {
                "source_name": "Mediciones Raman.zip",
                "sha256": "",
                "bytes": "",
                "hash_status": "not_computed_expanded_directory",
                "role": "benchtop_master_search_collection",
                "note": "Used as read-only provenance evidence; the ZIP itself was not available to hash.",
            },
            {
                "source_name": "Mediciones Raman portátil.zip",
                "sha256": "",
                "bytes": "",
                "hash_status": "not_computed_expanded_directory",
                "role": "portable_master_search_collection",
                "note": (
                    "Used as read-only provenance evidence except for the separately hashed and "
                    "distributed author-confirmed 24 September high-power blank."
                ),
            },
        ],
    )

    write_csv(
        metadata_root / "status_definitions.csv",
        ["status", "meaning", "may_be_aggregated_without_review"],
        [
            {"status": "publication_snapshot", "meaning": "Selected manuscript-facing table or spectrum export; selection does not by itself verify raw provenance.", "may_be_aggregated_without_review": "no"},
            {"status": "raw_author_confirmed", "meaning": "Raw source whose sample identity and experimental context were confirmed by the author and whose distributed bytes match the audited source hash.", "may_be_aggregated_without_review": "no"},
            {"status": "raw_unverified", "meaning": "Raw-like spectrum preserved with no detected decisive conflict, but identity and labels remain unverified.", "may_be_aggregated_without_review": "no"},
            {"status": "legacy_derived", "meaning": "Historical processed output retained without a complete, verified source-to-output lineage.", "may_be_aggregated_without_review": "no"},
            {"status": "provenance_conflict", "meaning": "At least one filename, embedded label, source match, blank identity, or raw/processed relationship conflicts.", "may_be_aggregated_without_review": "no"},
            {"status": "audit_evidence", "meaning": "Machine-readable audit or numerical-validation evidence generated from read-only inputs.", "may_be_aggregated_without_review": "not_applicable"},
            {"status": "superseded_not_distributed", "meaning": "Legacy code was inventoried but replaced by the unified pipeline and is not copied into the repository.", "may_be_aggregated_without_review": "not_applicable"},
        ],
    )

    write_csv(
        metadata_root / "provenance_conflicts.csv",
        ["conflict_id", "scope", "severity", "finding", "affected_count", "evidence", "resolution_status"],
        [
            {"conflict_id": "cross_label_duplicate_content", "scope": "curated raw spectra", "severity": "critical", "finding": "Identical spectrum bytes occur under different stated concentrations.", "affected_count": "103 groups; 277 files", "evidence": "provenance/duplicate_content_groups.csv and provenance/concentration_label_conflicts.csv", "resolution_status": "unresolved"},
            {"conflict_id": "shared_blank_wrong_context", "scope": "blind, calibration, optimisation, stability", "severity": "critical", "finding": "The same 15 high-power blank spectra are reused across eight sets that require different sessions and settings. Their exact historical origins are identified, but the shared composite is not a confirmed context-matched analytical blank. A separate 24 September high-power blank is author-confirmed for the matching optimisation condition; required low- and medium-power AuAgBC blanks remain unresolved.", "affected_count": "120 exact copies across 8 sets; 3 historical source exports; 1 separate confirmed high-power match", "evidence": "provenance/shared_blank_origin_summary.csv and provenance/4atp_blank_family_assessment.csv", "resolution_status": "historical_sources_identified_one_context_match_confirmed_others_unresolved"},
            {"conflict_id": "stability_19may_label_mismatch", "scope": "Stability/19_05_24", "severity": "critical", "finding": "Curated concentration labels disagree with the best matching master spectra.", "affected_count": "105 matched columns", "evidence": "provenance/concentration_label_conflicts.csv", "resolution_status": "unresolved"},
            {"conflict_id": "stability_content_overlap", "scope": "all stability dates", "severity": "critical", "finding": "Stability folders substantially overlap calibration or other-date content instead of forming independent dated acquisitions.", "affected_count": "unique content: 149/165, 103/159, and 20/210", "evidence": "provenance/duplicate_content_groups.csv", "resolution_status": "unresolved"},
            {"conflict_id": "optimisation_750m_orphan_derivatives", "scope": "Optimisation/750_5_5_M/Processed Spectra", "severity": "high", "finding": "Legacy processed filenames have no same-stem raw partners.", "affected_count": "43 files", "evidence": "validation/numerical_reproduction_summary.md", "resolution_status": "quarantined"},
            {"conflict_id": "portable_poc_embedded_metadata", "scope": "Proof of concept/Portable Raman", "severity": "high", "finding": "Six human-sweat raw files use outer publication aliases that differ from embedded acquisition aliases. The author-confirmed crosswalk resolves the numbering; the embedded V2S2 session in the two AA_HS copies is a confirmed metadata typo whose canonical session is V2S1. Historical bytes are preserved.", "affected_count": "6 human-sweat raw files", "evidence": "provenance/proof_of_concept_label_evidence.csv", "resolution_status": "resolved_by_author_confirmed_crosswalk_and_session_correction"},
            {"conflict_id": "families_not_exactly_regenerated", "scope": "calibration, analytical enhancement, proof of concept", "severity": "high", "finding": "Candidate recipes do not exactly regenerate supplied processed outputs from the paired curated raw files; missing or different blanks/source columns are implicated.", "affected_count": "3 analysis families", "evidence": "validation/numerical_reproduction_summary.md", "resolution_status": "unresolved"},
        ],
    )

    # These two tables are manually adjudicated reference metadata, not
    # disposable local-audit output. Keep their complete evidence in this
    # deterministic generator because ``main`` clears ``metadata/provenance``
    # before rebuilding it.
    write_csv(
        metadata_root / "provenance" / "shared_blank_origin_summary.csv",
        [
            "prepared_replicate", "prepared_accumulations", "prepared_record_groups",
            "prepared_copy_count", "master_folder_context", "canonical_master_path",
            "master_file_sha256", "embedded_datetime", "embedded_tag", "master_setting",
            "intensity_max_abs_difference", "axis_max_abs_difference", "axis_match_1e-5",
            "scientific_assessment",
        ],
        [
            {
                "prepared_replicate": 1,
                "prepared_accumulations": "1|2|3|4|5",
                "prepared_record_groups": "Blind samples|Calibration curve|Optimisation/500_5_5_L|Optimisation/750_5_5_H|Optimisation/750_5_5_M|Stability/03_07_24|Stability/19_05_24|Stability/24_09_24",
                "prepared_copy_count": 40,
                "master_folder_context": "test_hs",
                "canonical_master_path": "Test HS/25-09-24/Blank/AAB_Blank_750_5_5_H.csv",
                "master_file_sha256": "0afc7b1d9e4c687fa1905653ffb82f15a775f30bb890e3f41f493d089b7fa7f1",
                "embedded_datetime": "2024-09-25T10:48:15",
                "embedded_tag": "AAB_Blank_750_5_5_H",
                "master_setting": "750_5_5_H",
                "intensity_max_abs_difference": 0.0,
                "axis_max_abs_difference": 4.99989937452483e-07,
                "axis_match_1e-5": "true",
                "scientific_assessment": "historical_input_wrong_context",
            },
            {
                "prepared_replicate": 2,
                "prepared_accumulations": "1|2|3|4|5",
                "prepared_record_groups": "Blind samples|Calibration curve|Optimisation/500_5_5_L|Optimisation/750_5_5_H|Optimisation/750_5_5_M|Stability/03_07_24|Stability/19_05_24|Stability/24_09_24",
                "prepared_copy_count": 40,
                "master_folder_context": "test_hs",
                "canonical_master_path": "Test HS/30-09-24/Blank/AAB_Blank_750_5_5_H.csv",
                "master_file_sha256": "129df9858e729e80689b1ed009484396b99396320f75500b19a4fbb3eb45db0e",
                "embedded_datetime": "2024-09-30T12:33:37",
                "embedded_tag": "AAB_Blank_750_5_5_H",
                "master_setting": "750_5_5_H",
                "intensity_max_abs_difference": 0.0,
                "axis_max_abs_difference": 0.0535730875099034,
                "axis_match_1e-5": "false",
                "scientific_assessment": "historical_input_wrong_context",
            },
            {
                "prepared_replicate": 3,
                "prepared_accumulations": "1|2|3|4|5",
                "prepared_record_groups": "Blind samples|Calibration curve|Optimisation/500_5_5_L|Optimisation/750_5_5_H|Optimisation/750_5_5_M|Stability/03_07_24|Stability/19_05_24|Stability/24_09_24",
                "prepared_copy_count": 40,
                "master_folder_context": "test_4atp",
                "canonical_master_path": "Test 4-ATP/18-09-24/Blank/AAB_Blank_750_5_5_H.csv",
                "master_file_sha256": "e80ad94586e537db019cc1b7ca324324a25695fa2ccac3a7c31404c6ce530dbd",
                "embedded_datetime": "2024-09-18T16:58:16",
                "embedded_tag": "AAB_Blank_750_5_5_H",
                "master_setting": "750_5_5_H",
                "intensity_max_abs_difference": 0.0,
                "axis_max_abs_difference": 0.1610174642698894,
                "axis_match_1e-5": "false",
                "scientific_assessment": "historical_input_wrong_context",
            },
        ],
    )

    write_csv(
        metadata_root / "provenance" / "4atp_blank_family_assessment.csv",
        [
            "family_id", "scope", "required_session", "required_setting", "required_material",
            "nearest_candidate_path", "candidate_sha256", "candidate_embedded_datetime",
            "candidate_tag", "material_match", "session_match", "integration_match",
            "power_match", "averaging_match", "data_count_match", "resolution_status", "reason",
        ],
        [
            {
                "family_id": "calibration_curve",
                "scope": "published_4atp_calibration_condition",
                "required_session": "2024-07-03",
                "required_setting": "750_5_5_L",
                "required_material": "AuAgBC substrate without 4-ATP",
                "nearest_candidate_path": "Test 4-ATP/03-07-24/Blank/BC Blank 750_5_5_L.csv",
                "candidate_sha256": "40cfd5b9753568f36381b1596c3e104d8dcda4974dc15cd8f9b013c56001e490",
                "candidate_embedded_datetime": "2024-07-03T10:13:49",
                "candidate_tag": "BC Blank_750_5_5_l",
                "material_match": "false",
                "session_match": "true",
                "integration_match": "true",
                "power_match": "true",
                "averaging_match": "true",
                "data_count_match": "true",
                "resolution_status": "no_confirmed_context_match",
                "reason": "Same-session settings match but the file is a bare BC blank rather than the required AuAgBC substrate blank",
            },
            {
                "family_id": "blind_samples_prepared_2024_09_24",
                "scope": "author_selected_prepared_concentration_labelled_snapshot",
                "required_session": "2024-09-24",
                "required_setting": "750_5_5_L",
                "required_material": "AuAgBC substrate without 4-ATP",
                "nearest_candidate_path": "Test 4-ATP/24-09-24/Blank/Blanck_AABC_750_5_5_H.csv",
                "candidate_sha256": "e36f0ad7a57ebab8cba038309284305cfecc98d1586499fe73e266e301257dd9",
                "candidate_embedded_datetime": "2024-09-24T09:33:50",
                "candidate_tag": "Blanck_AABC_750_5_5_H",
                "material_match": "true",
                "session_match": "true",
                "integration_match": "true",
                "power_match": "false",
                "averaging_match": "true",
                "data_count_match": "true",
                "resolution_status": "no_confirmed_context_match",
                "reason": "The author selected the prepared 24-Sep low-power concentration-labelled set for release and confirmed AABC as analyte-free AuAgBC; the same-day candidate remains unsuitable because it was acquired at high power",
            },
            {
                "family_id": "blind_samples_intended_2024_09_10",
                "scope": "historical_coded_blind_experiment_not_selected_for_release",
                "required_session": "2024-09-10",
                "required_setting": "750_5_5_L",
                "required_material": "AuAgBC substrate without 4-ATP",
                "nearest_candidate_path": "Precision y exactitud/10-09-24/Blank/AABC Blank_750_5_5_H.csv",
                "candidate_sha256": "d0b175f45c6fdd717bdf5d3aed02ae116fb8635901ac35c4772ed3ce906de09c",
                "candidate_embedded_datetime": "2024-09-10T14:18:28",
                "candidate_tag": "AAG Blank_750_5_5_H",
                "material_match": "unresolved",
                "session_match": "true",
                "integration_match": "true",
                "power_match": "false",
                "averaging_match": "true",
                "data_count_match": "true",
                "resolution_status": "no_confirmed_context_match",
                "reason": "The author did not select this historical coded experiment for release; its same-session candidate is high power and the AABC filename still conflicts with the embedded AAG identity",
            },
            {
                "family_id": "optimisation_500_5_5_L",
                "scope": "optimisation_condition",
                "required_session": "2024-07-03",
                "required_setting": "500_5_5_L",
                "required_material": "AuAgBC substrate without 4-ATP",
                "nearest_candidate_path": "Test 4-ATP/03-07-24/Blank/BC Blank 750_5_5_L.csv",
                "candidate_sha256": "40cfd5b9753568f36381b1596c3e104d8dcda4974dc15cd8f9b013c56001e490",
                "candidate_embedded_datetime": "2024-07-03T10:13:49",
                "candidate_tag": "BC Blank_750_5_5_l",
                "material_match": "false",
                "session_match": "true",
                "integration_match": "false",
                "power_match": "true",
                "averaging_match": "true",
                "data_count_match": "true",
                "resolution_status": "no_confirmed_context_match",
                "reason": "The only same-day low-power blank has the wrong substrate material and a 750 ms integration rather than 500 ms",
            },
            {
                "family_id": "optimisation_750_5_5_H",
                "scope": "optimisation_condition",
                "required_session": "2024-09-24",
                "required_setting": "750_5_5_H",
                "required_material": "AuAgBC substrate without 4-ATP",
                "nearest_candidate_path": "Test 4-ATP/24-09-24/Blank/Blanck_AABC_750_5_5_H.csv",
                "candidate_sha256": "e36f0ad7a57ebab8cba038309284305cfecc98d1586499fe73e266e301257dd9",
                "candidate_embedded_datetime": "2024-09-24T09:33:50",
                "candidate_tag": "Blanck_AABC_750_5_5_H",
                "material_match": "true",
                "session_match": "true",
                "integration_match": "true",
                "power_match": "true",
                "averaging_match": "true",
                "data_count_match": "true",
                "resolution_status": "confirmed_context_match",
                "reason": "The author confirmed AABC is AuAgBC/AAB and this file is an analyte-free AuAgBC blank; date and all acquisition settings match the 24-Sep high-power optimisation",
            },
            {
                "family_id": "optimisation_750_5_5_M",
                "scope": "optimisation_condition",
                "required_session": "2024-09-24",
                "required_setting": "750_5_5_M",
                "required_material": "AuAgBC substrate without 4-ATP",
                "nearest_candidate_path": "Test 4-ATP/24-09-24/Blank/Blanck_AABC_750_5_5_H.csv",
                "candidate_sha256": "e36f0ad7a57ebab8cba038309284305cfecc98d1586499fe73e266e301257dd9",
                "candidate_embedded_datetime": "2024-09-24T09:33:50",
                "candidate_tag": "Blanck_AABC_750_5_5_H",
                "material_match": "true",
                "session_match": "true",
                "integration_match": "true",
                "power_match": "false",
                "averaging_match": "true",
                "data_count_match": "true",
                "resolution_status": "no_confirmed_context_match",
                "reason": "The author confirmed the AABC file is an analyte-free AuAgBC blank, but it was acquired at high rather than required medium power",
            },
            {
                "family_id": "stability_day_1_2024_05_19",
                "scope": "stability_day_1_prepared_family",
                "required_session": "2024-05-19",
                "required_setting": "750_5_5_L",
                "required_material": "AuAgBC substrate without 4-ATP",
                "nearest_candidate_path": "Parámetros heterogéneos de medición/Primeras mediciones/19-05-24/Sustrato AuAgBC_4-ATP_N/190524_AuAgBC_blank_750_5_5_H.csv",
                "candidate_sha256": "fa77c623f6fbff870353847cd3bd16599e399c34f2a3041d7d81ba90cc9c91eb",
                "candidate_embedded_datetime": "2024-05-20T01:29:47",
                "candidate_tag": "AuAgBC_blank_750_5_5_H",
                "material_match": "true",
                "session_match": "unresolved",
                "integration_match": "true",
                "power_match": "false",
                "averaging_match": "true",
                "data_count_match": "true",
                "resolution_status": "no_confirmed_context_match",
                "reason": "The prepared day-1 family mixes sessions and settings; this folder candidate is high power and its after-midnight timestamp leaves the session match unresolved",
            },
            {
                "family_id": "stability_day_45_2024_07_03",
                "scope": "stability_day_45_condition",
                "required_session": "2024-07-03",
                "required_setting": "750_5_5_L",
                "required_material": "AuAgBC substrate without 4-ATP",
                "nearest_candidate_path": "Test 4-ATP/03-07-24/Blank/BC Blank 750_5_5_L.csv",
                "candidate_sha256": "40cfd5b9753568f36381b1596c3e104d8dcda4974dc15cd8f9b013c56001e490",
                "candidate_embedded_datetime": "2024-07-03T10:13:49",
                "candidate_tag": "BC Blank_750_5_5_l",
                "material_match": "false",
                "session_match": "true",
                "integration_match": "true",
                "power_match": "true",
                "averaging_match": "true",
                "data_count_match": "true",
                "resolution_status": "no_confirmed_context_match",
                "reason": "Same-session settings match but the file is a bare BC blank rather than the required AuAgBC substrate blank",
            },
            {
                "family_id": "stability_day_128_2024_09_24",
                "scope": "stability_day_128_condition",
                "required_session": "2024-09-24",
                "required_setting": "750_5_5_L",
                "required_material": "AuAgBC substrate without 4-ATP",
                "nearest_candidate_path": "Test 4-ATP/24-09-24/Blank/Blanck_AABC_750_5_5_H.csv",
                "candidate_sha256": "e36f0ad7a57ebab8cba038309284305cfecc98d1586499fe73e266e301257dd9",
                "candidate_embedded_datetime": "2024-09-24T09:33:50",
                "candidate_tag": "Blanck_AABC_750_5_5_H",
                "material_match": "true",
                "session_match": "true",
                "integration_match": "true",
                "power_match": "false",
                "averaging_match": "true",
                "data_count_match": "true",
                "resolution_status": "no_confirmed_context_match",
                "reason": "The author confirmed the same-day AABC file is an analyte-free AuAgBC blank, but it was acquired at high rather than required low power",
            },
        ],
    )


def add_manifest_row(
    manifest: list[dict[str, object]],
    repository_root: Path,
    destination: Path,
    *,
    source_name: str,
    source_relative_path: str,
    source_sha256: str,
    source_bytes: int | str,
    status: str,
    role: str,
    substitutions: int,
    note: str,
) -> None:
    manifest.append({
        "repository_path": repository_path(destination, repository_root),
        "source_name": source_name,
        "source_relative_path": source_relative_path,
        "source_sha256": source_sha256,
        "repository_sha256": sha256_file(destination),
        "source_bytes": source_bytes,
        "repository_bytes": destination.stat().st_size,
        "status": status,
        "role": role,
        "sanitized_user_path_occurrences": substitutions,
        "note": note,
    })


def add_confirmed_4atp_blank_manifest_entry(
    repository_root: Path,
    manifest: list[dict[str, object]],
    status_counts: Counter[str],
) -> None:
    """Validate and manifest the committed author-confirmed raw blank."""
    confirmed_blank = validate_confirmed_4atp_blank(repository_root)
    add_manifest_row(
        manifest,
        repository_root,
        confirmed_blank,
        source_name="Blanck_AABC_750_5_5_H.csv",
        source_relative_path=CONFIRMED_4ATP_BLANK_SOURCE_PATH,
        source_sha256=CONFIRMED_4ATP_BLANK_SHA256,
        source_bytes=CONFIRMED_4ATP_BLANK_BYTES,
        status="raw_author_confirmed",
        role="4atp_analytical_blank_raw",
        substitutions=0,
        note=(
            "Exact unchanged source file; the author confirmed AABC is AuAgBC/AAB and "
            "this is an analyte-free blank for the 24 September high-power optimisation."
        ),
    )
    status_counts["raw_author_confirmed"] += 1


def parse_args() -> argparse.Namespace:
    script = Path(__file__).resolve()
    default_repo = script.parents[1]
    workspace = default_repo.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=default_repo)
    parser.add_argument("--source-root", type=Path, default=workspace / ".workbench" / "curated_input" / "Raman_spectra_data")
    parser.add_argument("--reports-root", type=Path, default=workspace / ".workbench" / "reports")
    parser.add_argument("--legacy-scripts-root", type=Path, default=workspace / ".workbench" / "legacy_scripts")
    parser.add_argument("--project-sources-root", type=Path, default=workspace / "sources")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repository_root = args.repository_root.resolve()
    source_root = args.source_root.resolve()
    reports_root = args.reports_root.resolve()
    legacy_scripts_root = args.legacy_scripts_root.resolve()
    project_sources_root = args.project_sources_root.resolve()
    if not source_root.is_dir():
        raise FileNotFoundError(f"Raman source directory not found: {source_root}")

    data_root = repository_root / "data"
    metadata_root = repository_root / "metadata"
    quarantine_root = data_root / "quarantine" / "legacy_snapshot"
    publication_root = data_root / "published_snapshot"
    raw_calibration_root = data_root / "raw" / "spectrometer_calibration"
    processed_calibration_root = data_root / "processed" / "spectrometer_calibration"
    provenance_root = metadata_root / "provenance"
    validation_root = metadata_root / "validation"
    for generated in (
        quarantine_root,
        publication_root,
        raw_calibration_root,
        processed_calibration_root,
        provenance_root,
        validation_root,
    ):
        reset_generated_directory(generated, repository_root)
    obsolete_manifest = metadata_root / "file_manifest.csv"
    if obsolete_manifest.is_file():
        obsolete_manifest.unlink()

    manifest: list[dict[str, object]] = []
    status_counts: Counter[str] = Counter()
    legacy_csv_count = 0
    sanitized_legacy_files = 0
    sanitized_occurrences = 0
    sanitization_rows: list[dict[str, object]] = []

    # This raw file is intentionally committed and is not regenerated from a
    # machine-local master directory. Validate its exact source identity on
    # every rebuild, then manifest the repository copy directly.
    add_confirmed_4atp_blank_manifest_entry(repository_root, manifest, status_counts)

    # Complete archive CSV snapshot.
    for source in sorted(source_root.rglob("*.csv"), key=lambda item: item.as_posix().casefold()):
        relative = source_rel(source, source_root)
        destination = quarantine_root / Path(relative)
        source_hash, _, source_size, _, substitutions = copy_sanitized(source, destination)
        portable_acquisition = PORTABLE_PATH_TABLES.get(relative)
        if portable_acquisition:
            portable_changes = make_file_column_portable(destination, portable_acquisition)
            if portable_changes != substitutions:
                raise RuntimeError(
                    f"Expected {substitutions} local paths but rewrote {portable_changes} file cells in {relative}."
                )
        status, role, note = quarantine_status(relative)
        add_manifest_row(
            manifest,
            repository_root,
            destination,
            source_name="Raman_spectra_data.zip",
            source_relative_path=relative,
            source_sha256=source_hash,
            source_bytes=source_size,
            status=status,
            role=role,
            substitutions=substitutions,
            note=note,
        )
        status_counts[status] += 1
        legacy_csv_count += 1
        if substitutions:
            sanitized_legacy_files += 1
            sanitized_occurrences += substitutions
            rows_checked, changed_columns, non_path_changes = compare_sanitized_csv(source, destination)
            sanitization_rows.append({
                "source_relative_path": relative,
                "path_occurrences_replaced": substitutions,
                "rows_checked": rows_checked,
                "changed_columns": changed_columns,
                "non_path_cells_changed": non_path_changes,
                "source_sha256": source_hash,
                "repository_sha256": sha256_file(destination),
                "replacement": (
                    "repository-relative data path"
                    if portable_acquisition
                    else "<USER_HOME>\\"
                ),
            })

    write_csv(
        metadata_root / "sanitization_report.csv",
        [
            "source_relative_path", "path_occurrences_replaced", "rows_checked", "changed_columns",
            "non_path_cells_changed", "source_sha256", "repository_sha256", "replacement",
        ],
        sanitization_rows,
    )

    # Explicit archive-derived publication exports.
    for relative, normalized in ARCHIVE_PUBLICATION_MAP.items():
        source = source_root / Path(relative)
        if not source.is_file():
            raise FileNotFoundError(f"Mapped publication source is missing: {source}")
        destination = publication_root / Path(normalized)
        source_hash, _, source_size, _, substitutions = copy_sanitized(source, destination)
        add_manifest_row(
            manifest,
            repository_root,
            destination,
            source_name="Raman_spectra_data.zip",
            source_relative_path=relative,
            source_sha256=source_hash,
            source_bytes=source_size,
            status="publication_snapshot",
            role="manuscript_supporting_table",
            substitutions=substitutions,
            note="Selected and normalized for the publication snapshot; raw provenance still requires status review.",
        )
        status_counts["publication_snapshot"] += 1

    # Paper-context proof-of-concept exports intentionally supersede the
    # archive copies in the publication-facing directory.
    for source_name, normalized in PROJECT_PUBLICATION_MAP.items():
        source = project_sources_root / source_name
        if not source.is_file():
            raise FileNotFoundError(f"Paper-context publication source is missing: {source}")
        destination = publication_root / Path(normalized)
        source_hash, _, source_size, _, substitutions = copy_sanitized(source, destination)
        correct_publication_header(destination, source_name)
        add_manifest_row(
            manifest,
            repository_root,
            destination,
            source_name="paper_project_sources",
            source_relative_path=f"sources/{source_name}",
            source_sha256=source_hash,
            source_bytes=source_size,
            status="publication_snapshot",
            role="manuscript_supporting_table",
            substitutions=substitutions,
            note=(
                PROOF_OF_CONCEPT_MANIFEST_NOTE
                if source_name in PROOF_OF_CONCEPT_PUBLICATION_FILES
                else "Selected from the paper project; the differing archive export remains only in quarantine."
            ),
        )
        status_counts["publication_snapshot"] += 1

    # Silicon pair: one publication-facing pair plus explicit raw/processed
    # lineage locations.
    silicon_pairs = (
        (
            "Hand-held spectrometer calibration/060624_Si_original_file.csv",
            publication_root / "spectrometer_calibration" / "si_original.csv",
            "publication_snapshot",
            "instrument_calibration_raw",
        ),
        (
            "Hand-held spectrometer calibration/Si_calibration.csv",
            publication_root / "spectrometer_calibration" / "si_calibrated.csv",
            "publication_snapshot",
            "instrument_calibration_processed",
        ),
        (
            "Hand-held spectrometer calibration/060624_Si_original_file.csv",
            raw_calibration_root / "si_original.csv",
            "raw_unverified",
            "instrument_calibration_raw",
        ),
        (
            "Hand-held spectrometer calibration/Si_calibration.csv",
            processed_calibration_root / "si_calibrated.csv",
            "legacy_derived",
            "instrument_calibration_processed",
        ),
    )
    for relative, destination, status, role in silicon_pairs:
        source = source_root / Path(relative)
        source_hash, _, source_size, _, substitutions = copy_sanitized(source, destination)
        add_manifest_row(
            manifest,
            repository_root,
            destination,
            source_name="Raman_spectra_data.zip",
            source_relative_path=relative,
            source_sha256=source_hash,
            source_bytes=source_size,
            status=status,
            role=role,
            substitutions=substitutions,
            note="Silicon axis-calibration pair retained without changing intensity values.",
        )
        status_counts[status] += 1

    # Explicit manuscript tables.
    for path, note in manuscript_tables(publication_root):
        add_manifest_row(
            manifest,
            repository_root,
            path,
            source_name="manuscript",
            source_relative_path="manuscript table values",
            source_sha256="",
            source_bytes="",
            status="publication_snapshot",
            role="manuscript_parameter_table",
            substitutions=0,
            note=note,
        )
        status_counts["publication_snapshot"] += 1

    # Audit evidence copied with the same privacy sanitation.
    audit_report_count = 0
    for source_name, normalized in REPORT_MAP.items():
        source = reports_root / source_name
        if not source.is_file():
            continue
        destination = metadata_root / Path(normalized)
        source_hash, _, source_size, _, substitutions = copy_sanitized(source, destination)
        if source_name == "inventory_summary.json":
            inventory = json.loads(destination.read_text(encoding="utf-8-sig"))
            inventory["roots"] = {
                "curated": "<CURATED_ARCHIVE_EXTRACT>",
                "master_benchtop": "<BENCHTOP_MASTER_COLLECTION>",
                "master_portable": "<PORTABLE_MASTER_COLLECTION>",
            }
            destination.write_text(
                json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        add_manifest_row(
            manifest,
            repository_root,
            destination,
            source_name="local_audit",
            source_relative_path=f"reports/{source_name}",
            source_sha256=source_hash,
            source_bytes=source_size,
            status="audit_evidence",
            role="provenance_audit",
            substitutions=substitutions,
            note=(
                "Read-only audit output copied with local source-root values replaced by role placeholders."
                if source_name == "inventory_summary.json"
                else "Read-only audit output copied into repository metadata."
            ),
        )
        status_counts["audit_evidence"] += 1
        audit_report_count += 1

    numerical_root = reports_root / "numerical"
    if numerical_root.is_dir():
        supported = {".csv", ".json", ".md"}
        for source in sorted(numerical_root.iterdir(), key=lambda item: item.name.casefold()):
            if not source.is_file() or source.suffix.casefold() not in supported:
                continue
            destination = validation_root / source.name
            source_hash, _, source_size, _, substitutions = copy_sanitized(source, destination)
            if source.name == "numerical_reproduction_summary.md":
                supersession_notice = (
                    "> **Superseded package result (20 July 2026).** This exploratory report used a separate "
                    "data-frame replay. Its conclusion that 27 large differences demonstrate provenance mismatches "
                    "is not supported by the released workflow. The deterministic package replay later reproduced "
                    "all 955 paired spectra exactly (RMSE and maximum absolute difference both zero). See "
                    "`package_reproduction_summary.csv`, `package_reproduction_metrics.csv`, and "
                    "`../../docs/DATA_AUDIT.md`. The report below is retained only as evidence of the historical "
                    "FFT cutoff's sensitivity to approximately 1e-12 parsing and summation differences.\n\n"
                )
                existing = destination.read_text(encoding="utf-8-sig")
                destination.write_text(supersession_notice + existing, encoding="utf-8", newline="\n")
            add_manifest_row(
                manifest,
                repository_root,
                destination,
                source_name="local_numerical_audit",
                source_relative_path=f"reports/numerical/{source.name}",
                source_sha256=source_hash,
                source_bytes=source_size,
                status="audit_evidence",
                role="numerical_validation",
                substitutions=substitutions,
                note=(
                    "Exploratory numerical comparison retained with a supersession notice."
                    if source.name == "numerical_reproduction_summary.md"
                    else "Numerical comparison generated from read-only archive inputs."
                ),
            )
            status_counts["audit_evidence"] += 1
            audit_report_count += 1

    write_reference_metadata(metadata_root)
    raw_manifest_count = build_raw_processing_manifest(
        source_root,
        metadata_root,
        reports_root / "best_curated_raw_column_matches.csv",
        reports_root / "file_inventory.csv",
        repository_root,
    )
    legacy_script_count = build_legacy_script_inventory(
        legacy_scripts_root,
        metadata_root / "legacy_script_inventory.csv",
    )

    manifest.sort(key=lambda row: str(row["repository_path"]).casefold())
    write_mapping_sidecars(repository_root, manifest)
    write_csv(
        metadata_root / "dataset_manifest.csv",
        [
            "repository_path", "source_name", "source_relative_path", "source_sha256",
            "repository_sha256", "source_bytes", "repository_bytes", "status", "role",
            "sanitized_user_path_occurrences", "note",
        ],
        manifest,
    )

    summary = {
        "schema_version": 1,
        "source_csv_count": len(list(source_root.rglob("*.csv"))),
        "legacy_snapshot_csv_count": legacy_csv_count,
        "legacy_snapshot_sanitized_files": sanitized_legacy_files,
        "legacy_snapshot_sanitized_path_occurrences": sanitized_occurrences,
        "publication_snapshot_file_count": len(list(publication_root.rglob("*.*"))),
        "raw_processing_manifest_rows": raw_manifest_count,
        "legacy_script_inventory_rows": legacy_script_count,
        "copied_audit_report_count": audit_report_count,
        "dataset_manifest_rows": len(manifest),
        "status_counts": dict(sorted(status_counts.items())),
    }
    (metadata_root / "curation_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
