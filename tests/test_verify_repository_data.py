from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "verify_repository_data.py"
SPEC = importlib.util.spec_from_file_location("verify_repository_data", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
VERIFY_MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY_MODULE
SPEC.loader.exec_module(VERIFY_MODULE)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _tiny_repository(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repository"
    for directory in ("data", "metadata", "docs", "configs"):
        (root / directory).mkdir(parents=True, exist_ok=True)

    spectrum = root / "data" / "quarantine" / "legacy_snapshot" / "raw.csv"
    spectrum.parent.mkdir(parents=True)
    spectrum.write_bytes(b"shift,intensity\n100,12\n")
    relative = spectrum.relative_to(root).as_posix()
    digest = hashlib.sha256(spectrum.read_bytes()).hexdigest()

    _write_csv(
        root / "metadata" / "dataset_manifest.csv",
        ["repository_path", "repository_sha256", "repository_bytes", "status"],
        [
            {
                "repository_path": relative,
                "repository_sha256": digest,
                "repository_bytes": spectrum.stat().st_size,
                "status": "raw_unverified",
            }
        ],
    )
    _write_csv(
        root / "metadata" / "raw_processing_manifest.csv",
        [
            "file",
            "sample_type",
            "concentration_molar",
            "replicate",
            "accumulation",
            "instrument",
            "acquisition",
        ],
        [
            {
                "file": relative,
                "sample_type": "4atp",
                "concentration_molar": "1e-9",
                "replicate": "1",
                "accumulation": "1",
                "instrument": "benchtop_raman",
                "acquisition": "1 s",
            }
        ],
    )
    _write_csv(
        root / "metadata" / "legacy_script_inventory.csv",
        ["relative_path"],
        [],
    )
    _write_csv(
        root / "metadata" / "sanitization_report.csv",
        ["source_relative_path", "path_occurrences_replaced"],
        [],
    )
    (root / "metadata" / "curation_summary.json").write_text(
        json.dumps(
            {
                "source_csv_count": 1,
                "legacy_snapshot_csv_count": 1,
                "legacy_snapshot_sanitized_files": 0,
                "legacy_snapshot_sanitized_path_occurrences": 0,
                "publication_snapshot_file_count": 0,
                "raw_processing_manifest_rows": 1,
                "legacy_script_inventory_rows": 0,
                "copied_audit_report_count": 0,
                "dataset_manifest_rows": 1,
                "status_counts": {"raw_unverified": 1},
            }
        ),
        encoding="utf-8",
    )
    (root / "docs" / "README.md").write_text("Portable fixture.\n", encoding="utf-8")
    (root / "configs" / "example.json").write_text("{}\n", encoding="utf-8")
    return root, spectrum


def test_valid_tiny_repository_passes(tmp_path: Path) -> None:
    root, _ = _tiny_repository(tmp_path)

    report = VERIFY_MODULE.verify_repository(root)

    assert report["ok"] is True
    assert report["error_count"] == 0
    assert report["counts"]["manifest_files_hashed"] == 1


def test_tampered_file_reports_size_hash_and_nonzero_exit(
    tmp_path: Path, capsys
) -> None:
    root, spectrum = _tiny_repository(tmp_path)
    spectrum.write_bytes(spectrum.read_bytes() + b"tampered\n")

    report = VERIFY_MODULE.verify_repository(root)
    joined = "\n".join(report["errors"])

    assert report["ok"] is False
    assert "byte-size mismatch" in joined
    assert "SHA-256 mismatch" in joined

    assert VERIFY_MODULE.main(["--root", str(root), "--json"]) == 1
    cli_report = json.loads(capsys.readouterr().out)
    assert cli_report["ok"] is False


def test_duplicate_unsafe_path_and_sensitive_content_are_rejected(tmp_path: Path) -> None:
    root, spectrum = _tiny_repository(tmp_path)
    manifest = root / "metadata" / "dataset_manifest.csv"
    rows = list(csv.DictReader(manifest.open(encoding="utf-8", newline="")))
    rows.append(dict(rows[0]))
    rows.append(
        {
            "repository_path": "../outside.csv",
            "repository_sha256": "0" * 64,
            "repository_bytes": "0",
            "status": "raw_unverified",
        }
    )
    _write_csv(manifest, list(rows[0]), rows)
    (root / "docs" / "private.md").write_text(
        "Do not release C:/Users/researcher/results or person@example.org.\n",
        encoding="utf-8",
    )

    report = VERIFY_MODULE.verify_repository(root)
    joined = "\n".join(report["errors"])

    assert report["ok"] is False
    assert "duplicates repository_path" in joined
    assert "unsafe path" in joined
    assert "Windows user-home path" in joined
    assert "email address" in joined
    assert spectrum.is_file()  # The verifier is read-only.
