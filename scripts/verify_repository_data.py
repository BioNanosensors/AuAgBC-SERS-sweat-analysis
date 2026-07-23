#!/usr/bin/env python3
"""Read-only integrity and limited direct-identifier checks for repository data.

This module deliberately uses only the Python standard library so that a data
release can be checked before the numerical processing dependencies are
installed.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable


DATASET_REQUIRED_COLUMNS = {
    "repository_path",
    "repository_sha256",
    "repository_bytes",
    "status",
}
RAW_REQUIRED_COLUMNS = {
    "file",
    "sample_type",
    "concentration_molar",
    "replicate",
    "accumulation",
    "instrument",
    "acquisition",
}
STATUS_DEFINITION_REQUIRED_COLUMNS = {
    "status",
    "meaning",
    "may_be_aggregated_without_review",
}
FOUR_ATP_RELEASE_PREFIXES = (
    "data/processed/4atp/optimisation/750_5_5_H/",
    "data/processed/4atp/optimisation/750_5_5_M/"
    "historical_computational_replay/",
)
MEDIUM_4ATP_REPLAY_SOURCE_PREFIX = (
    "data/quarantine/computational_lineage_sources/4atp/optimisation/"
    "750_5_5_M/"
)
SCAN_DIRECTORIES = ("data", "metadata", "docs", "configs")
MAX_REPORTED_ERRORS = 50

# These byte patterns work on both ordinary text and binary containers without
# decoding the source file. Scripts are intentionally outside SCAN_DIRECTORIES,
# so a deliberate privacy-check regex in source code does not flag itself.
SENSITIVE_PATTERNS = (
    (
        "Windows user-home path",
        re.compile(
            rb"(?i)(?<![A-Za-z0-9])[A-Z]:[\\/]"
            rb"(?:Users|Documents[ ]and[ ]Settings)[\\/]"
            rb"[^\\/\x00\r\n\t \"'<>|,;]+"
        ),
    ),
    (
        "Unix or macOS user-home path",
        re.compile(
            rb"(?i)(?<![A-Za-z0-9:])/(?:home|Users)/"
            rb"[^/\x00\r\n\t \"'<>|,;]+"
        ),
    ),
    (
        "tilde user-home path",
        re.compile(rb"(?<![A-Za-z0-9])~[\\/](?=[^\x00\r\n\t ])"),
    ),
    (
        "email address",
        re.compile(
            rb"(?i)(?<![A-Z0-9._%+-])[A-Z0-9._%+-]+@"
            rb"[A-Z0-9.-]+\.[A-Z]{2,}(?![A-Z0-9_-])"
        ),
    ),
)


class ErrorCollector:
    """Keep command output useful even when a release has many bad rows."""

    def __init__(self, limit: int = MAX_REPORTED_ERRORS) -> None:
        self.limit = limit
        self.messages: list[str] = []
        self.total = 0

    def add(self, message: str) -> None:
        self.total += 1
        if len(self.messages) < self.limit:
            self.messages.append(message)


def _read_csv(
    path: Path,
    required_columns: set[str],
    errors: ErrorCollector,
) -> tuple[list[dict[str, str]], set[str]]:
    if not path.is_file():
        errors.add(f"Missing required manifest: {path.name}")
        return [], set()

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = set(reader.fieldnames or [])
            missing = sorted(required_columns - columns)
            if missing:
                errors.add(
                    f"{path.name} is missing required column(s): "
                    + ", ".join(missing)
                )
            return [dict(row) for row in reader], columns
    except (OSError, UnicodeError, csv.Error) as exc:
        errors.add(f"Could not read {path.name}: {exc}")
        return [], set()


def _safe_repository_path(
    value: str,
    repository_root: Path,
    context: str,
    errors: ErrorCollector,
) -> tuple[str, Path] | None:
    if not value:
        errors.add(f"{context} has an empty repository path")
        return None
    if value != value.strip():
        errors.add(f"{context} path has leading or trailing whitespace: {value!r}")
        return None
    if "\x00" in value or "\\" in value:
        errors.add(
            f"{context} uses an unsafe or non-portable path; use forward-slash "
            f"repository-relative paths: {value!r}"
        )
        return None

    posix_path = PurePosixPath(value)
    windows_path = PureWindowsPath(value)
    if (
        posix_path.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or any(part in {"", ".", ".."} for part in posix_path.parts)
        or "//" in value
    ):
        errors.add(f"{context} has an unsafe path outside the repository: {value!r}")
        return None

    root_resolved = repository_root.resolve()
    candidate = (repository_root / Path(*posix_path.parts)).resolve(strict=False)
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        errors.add(f"{context} resolves outside the repository: {value!r}")
        return None
    return posix_path.as_posix(), candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _integer(value: Any, context: str, errors: ErrorCollector) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        errors.add(f"{context} must be an integer, found {value!r}")
        return None
    if result < 0:
        errors.add(f"{context} must not be negative, found {result}")
        return None
    return result


def _count_csv_rows(path: Path, errors: ErrorCollector) -> int | None:
    if not path.is_file():
        errors.add(f"Missing count source required by curation summary: {path.name}")
        return None
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return sum(1 for _ in csv.DictReader(handle))
    except (OSError, UnicodeError, csv.Error) as exc:
        errors.add(f"Could not count rows in {path.name}: {exc}")
        return None


def _sanitization_counts(
    path: Path, errors: ErrorCollector
) -> tuple[int | None, int | None]:
    rows, columns = _read_csv(
        path,
        {"path_occurrences_replaced"},
        errors,
    )
    if "path_occurrences_replaced" not in columns:
        return None, None
    occurrences = 0
    for row_number, row in enumerate(rows, start=2):
        value = _integer(
            row.get("path_occurrences_replaced"),
            f"{path.name} row {row_number} path_occurrences_replaced",
            errors,
        )
        if value is not None:
            occurrences += value
    return len(rows), occurrences


def _compare_summary(
    repository_root: Path,
    summary_path: Path,
    actual_counts: dict[str, Any],
    errors: ErrorCollector,
) -> None:
    if not summary_path.is_file():
        errors.add("Missing required curation summary: curation_summary.json")
        return
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.add(f"Could not read curation_summary.json: {exc}")
        return
    if not isinstance(summary, dict):
        errors.add("curation_summary.json must contain a JSON object")
        return

    for key, actual in actual_counts.items():
        if actual is None or key not in summary:
            continue
        expected = summary[key]
        if expected != actual:
            errors.add(
                f"curation_summary.json {key} is {expected!r}, but the "
                f"repository currently contains {actual!r}; regenerate the "
                "summary and manifest together"
            )


def _scan_sensitive_content(
    repository_root: Path,
    errors: ErrorCollector,
) -> int:
    def scan_bytes(label_path: str, content: bytes) -> None:
        for label, pattern in SENSITIVE_PATTERNS:
            match = pattern.search(content)
            if match:
                line = content.count(b"\n", 0, match.start()) + 1
                errors.add(
                    f"Sensitive content ({label}) in {label_path}, line {line}; "
                    "remove or replace it with repository-relative metadata"
                )

    scanned = 0
    root_resolved = repository_root.resolve()
    for directory_name in SCAN_DIRECTORIES:
        directory = repository_root / directory_name
        if not directory.exists():
            errors.add(f"Missing distributable directory: {directory_name}/")
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            resolved = path.resolve(strict=False)
            try:
                resolved.relative_to(root_resolved)
            except ValueError:
                relative = path.relative_to(repository_root).as_posix()
                errors.add(f"Distributable file resolves outside repository: {relative}")
                continue
            scanned += 1
            try:
                content = path.read_bytes()
            except OSError as exc:
                relative = path.relative_to(repository_root).as_posix()
                errors.add(f"Could not scan {relative}: {exc}")
                continue
            relative = path.relative_to(repository_root).as_posix()
            if path.suffix.casefold() == ".gz":
                try:
                    scan_bytes(relative + "::decompressed", gzip.decompress(content))
                except (OSError, EOFError) as exc:
                    errors.add(f"Could not decompress and scan {relative}: {exc}")
            elif path.suffix.casefold() == ".zip":
                try:
                    with zipfile.ZipFile(path) as archive:
                        for member in sorted(archive.namelist(), key=str.casefold):
                            if member.endswith("/"):
                                continue
                            scan_bytes(relative + "::" + member, archive.read(member))
                except (OSError, KeyError, zipfile.BadZipFile) as exc:
                    errors.add(f"Could not open and scan {relative}: {exc}")
            else:
                scan_bytes(relative, content)
    return scanned


def verify_repository(repository_root: Path) -> dict[str, Any]:
    """Verify data integrity and return a JSON-serializable report."""

    root = repository_root.resolve()
    errors = ErrorCollector()
    metadata = root / "metadata"

    dataset_rows, dataset_columns = _read_csv(
        metadata / "dataset_manifest.csv",
        DATASET_REQUIRED_COLUMNS,
        errors,
    )
    raw_rows, raw_columns = _read_csv(
        metadata / "raw_processing_manifest.csv",
        RAW_REQUIRED_COLUMNS,
        errors,
    )
    status_rows, status_columns = _read_csv(
        metadata / "status_definitions.csv",
        STATUS_DEFINITION_REQUIRED_COLUMNS,
        errors,
    )

    defined_statuses: set[str] = set()
    can_validate_statuses = STATUS_DEFINITION_REQUIRED_COLUMNS <= status_columns
    if can_validate_statuses:
        for row_number, row in enumerate(status_rows, start=2):
            status = (row.get("status") or "").strip()
            if not status:
                errors.add(
                    f"status_definitions.csv row {row_number} has an empty status"
                )
                continue
            if status in defined_statuses:
                errors.add(
                    f"status_definitions.csv row {row_number} duplicates status "
                    f"{status!r}"
                )
                continue
            defined_statuses.add(status)

    dataset_paths: set[str] = set()
    casefold_paths: dict[str, str] = {}
    status_counts: Counter[str] = Counter()
    verified_files = 0
    verified_bytes = 0

    can_verify_dataset = DATASET_REQUIRED_COLUMNS <= dataset_columns
    if can_verify_dataset:
        for row_number, row in enumerate(dataset_rows, start=2):
            context = f"dataset_manifest.csv row {row_number}"
            safe = _safe_repository_path(
                row.get("repository_path", ""), root, context, errors
            )
            if safe is None:
                continue
            relative, path = safe
            if relative in dataset_paths:
                errors.add(f"{context} duplicates repository_path {relative!r}")
                continue
            collision = casefold_paths.get(relative.casefold())
            if collision is not None:
                errors.add(
                    f"{context} path {relative!r} collides by letter case with "
                    f"{collision!r}; this is unsafe on case-insensitive filesystems"
                )
                continue
            dataset_paths.add(relative)
            casefold_paths[relative.casefold()] = relative
            status = row.get("status") or ""
            status_counts[status] += 1
            if can_validate_statuses and status not in defined_statuses:
                errors.add(
                    f"{context} uses undefined status {status!r}; add it to "
                    "status_definitions.csv or correct the manifest row"
                )

            if not path.is_file():
                errors.add(f"{context} references a missing file: {relative}")
                continue
            expected_bytes = _integer(
                row.get("repository_bytes"),
                f"{context} repository_bytes",
                errors,
            )
            actual_bytes = path.stat().st_size
            if expected_bytes is not None and expected_bytes != actual_bytes:
                errors.add(
                    f"{context} byte-size mismatch for {relative}: manifest "
                    f"{expected_bytes}, actual {actual_bytes}"
                )

            expected_hash = (row.get("repository_sha256") or "").lower()
            if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
                errors.add(f"{context} has an invalid repository_sha256 for {relative}")
                continue
            try:
                actual_hash = _sha256(path)
            except OSError as exc:
                errors.add(f"Could not hash {relative}: {exc}")
                continue
            if expected_hash != actual_hash:
                errors.add(
                    f"{context} SHA-256 mismatch for {relative}: manifest "
                    f"{expected_hash}, actual {actual_hash}"
                )
            verified_files += 1
            verified_bytes += actual_bytes

    if RAW_REQUIRED_COLUMNS <= raw_columns:
        checked_raw_paths: set[str] = set()
        for row_number, row in enumerate(raw_rows, start=2):
            context = f"raw_processing_manifest.csv row {row_number}"
            safe = _safe_repository_path(row.get("file", ""), root, context, errors)
            if safe is None:
                continue
            relative, path = safe
            if relative not in dataset_paths:
                errors.add(
                    f"{context} references {relative!r}, which is not recorded in "
                    "dataset_manifest.csv"
                )
            if relative not in checked_raw_paths and not path.is_file():
                errors.add(f"{context} references a missing file: {relative}")
            checked_raw_paths.add(relative)

    data_root = root / "data"
    if data_root.is_dir():
        for path in sorted(data_root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if relative not in dataset_paths:
                errors.add(
                    f"Unmanifested distributable data file: {relative}; add it to "
                    "dataset_manifest.csv or remove it from data/"
                )

    legacy_paths = [
        path
        for path in dataset_paths
        if path.startswith("data/quarantine/legacy_snapshot/")
        and path.lower().endswith(".csv")
    ]
    publication_paths = [
        path for path in dataset_paths if path.startswith("data/published_snapshot/")
    ]
    inventory_rows = _count_csv_rows(
        metadata / "legacy_script_inventory.csv", errors
    )
    sanitized_files, sanitized_occurrences = _sanitization_counts(
        metadata / "sanitization_report.csv", errors
    )
    actual_summary_counts: dict[str, Any] = {
        "source_csv_count": len(legacy_paths),
        "legacy_snapshot_csv_count": len(legacy_paths),
        "legacy_snapshot_sanitized_files": sanitized_files,
        "legacy_snapshot_sanitized_path_occurrences": sanitized_occurrences,
        "publication_snapshot_file_count": len(publication_paths),
        "raw_processing_manifest_rows": len(raw_rows),
        "legacy_script_inventory_rows": inventory_rows,
        "copied_audit_report_count": status_counts.get("audit_evidence", 0),
        "regenerated_4atp_release_file_count": sum(
            path.startswith(FOUR_ATP_RELEASE_PREFIXES)
            for path in dataset_paths
        ),
        "medium_power_computational_replay_source_file_count": sum(
            path.startswith(MEDIUM_4ATP_REPLAY_SOURCE_PREFIX)
            for path in dataset_paths
        ),
        "medium_power_computational_replay_file_count": sum(
            path.startswith(FOUR_ATP_RELEASE_PREFIXES[1])
            for path in dataset_paths
        ),
        "dataset_manifest_rows": len(dataset_rows),
        "status_counts": dict(sorted(status_counts.items())),
    }
    _compare_summary(
        root,
        metadata / "curation_summary.json",
        actual_summary_counts,
        errors,
    )

    scanned_files = _scan_sensitive_content(root, errors)
    report = {
        "ok": errors.total == 0,
        "counts": {
            "dataset_manifest_rows": len(dataset_rows),
            "raw_processing_manifest_rows": len(raw_rows),
            "manifest_files_hashed": verified_files,
            "manifest_bytes_hashed": verified_bytes,
            "distributable_files_scanned": scanned_files,
        },
        "errors": errors.messages,
        "error_count": errors.total,
    }
    if errors.total > len(errors.messages):
        report["suppressed_error_count"] = errors.total - len(errors.messages)
    return report


def _human_output(report: dict[str, Any]) -> str:
    counts = report["counts"]
    if report["ok"]:
        return (
            "PASS: repository data verified "
            f"({counts['manifest_files_hashed']} files, "
            f"{counts['raw_processing_manifest_rows']} processing-manifest rows, "
            f"{counts['distributable_files_scanned']} direct-identifier-scanned files)."
        )
    lines = [f"FAIL: {report['error_count']} repository verification error(s):"]
    lines.extend(f"- {message}" for message in report["errors"])
    suppressed = report.get("suppressed_error_count", 0)
    if suppressed:
        lines.append(f"- ... {suppressed} additional error(s) suppressed")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (default: parent of scripts/)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the verification report as JSON",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    report = verify_repository(args.root)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_human_output(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
