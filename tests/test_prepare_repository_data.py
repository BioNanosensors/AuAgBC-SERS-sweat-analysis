from __future__ import annotations

import csv
import json
import shutil
from collections import Counter
from pathlib import Path

from scripts import prepare_repository_data as PREPARE


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _copy_confirmed_blank(repository_root: Path) -> Path:
    source = PROJECT_ROOT / PREPARE.CONFIRMED_4ATP_BLANK_REPOSITORY_PATH
    destination = repository_root / PREPARE.CONFIRMED_4ATP_BLANK_REPOSITORY_PATH
    destination.parent.mkdir(parents=True)
    shutil.copy2(source, destination)
    return destination


def test_reference_metadata_survives_a_provenance_rebuild(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    metadata_root = repository_root / "metadata"
    provenance_root = metadata_root / "provenance"
    provenance_root.mkdir(parents=True)

    # Simulate both hazards in main(): provenance is cleared wholesale and
    # reference CSVs from an earlier generator revision are overwritten.
    (provenance_root / "shared_blank_origin_summary.csv").write_text(
        "stale\n", encoding="utf-8"
    )
    (provenance_root / "4atp_blank_family_assessment.csv").write_text(
        "stale\n", encoding="utf-8"
    )
    (metadata_root / "source_archives.csv").write_text("stale\n", encoding="utf-8")
    (metadata_root / "provenance_conflicts.csv").write_text(
        "stale\n", encoding="utf-8"
    )

    PREPARE.reset_generated_directory(provenance_root, repository_root)
    PREPARE.write_reference_metadata(metadata_root)

    generated_paths = (
        Path("source_archives.csv"),
        Path("status_definitions.csv"),
        Path("provenance_conflicts.csv"),
        Path("provenance/shared_blank_origin_summary.csv"),
        Path("provenance/4atp_blank_family_assessment.csv"),
    )
    for relative_path in generated_paths:
        assert _read_csv(metadata_root / relative_path) == _read_csv(
            PROJECT_ROOT / "metadata" / relative_path
        )


def test_confirmed_blank_is_hash_validated_and_manifested() -> None:
    manifest: list[dict[str, object]] = []
    status_counts: Counter[str] = Counter()

    confirmed = PREPARE.validate_confirmed_4atp_blank(PROJECT_ROOT)
    PREPARE.add_confirmed_4atp_blank_manifest_entry(
        PROJECT_ROOT, manifest, status_counts
    )

    assert confirmed.stat().st_size == 27_476
    assert PREPARE.sha256_file(confirmed) == PREPARE.CONFIRMED_4ATP_BLANK_SHA256
    assert status_counts == {"raw_author_confirmed": 1}
    assert len(manifest) == 1
    assert manifest[0] == {
        "repository_path": (
            "data/raw/4atp/optimisation/750_5_5_H/Blanck_AABC_750_5_5_H.csv"
        ),
        "source_name": "Blanck_AABC_750_5_5_H.csv",
        "source_relative_path": (
            "Test 4-ATP/24-09-24/Blank/Blanck_AABC_750_5_5_H.csv"
        ),
        "source_sha256": PREPARE.CONFIRMED_4ATP_BLANK_SHA256,
        "repository_sha256": PREPARE.CONFIRMED_4ATP_BLANK_SHA256,
        "source_bytes": 27_476,
        "repository_bytes": 27_476,
        "status": "raw_author_confirmed",
        "role": "4atp_analytical_blank_raw",
        "sanitized_user_path_occurrences": 0,
        "note": (
            "Exact unchanged source file; the author confirmed AABC is AuAgBC/AAB and "
            "this is an analyte-free blank for the 24 September high-power optimisation."
        ),
    }


def test_raw_processing_manifest_includes_confirmed_blank_without_master_directory(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    source_root = tmp_path / "empty_archive_source"
    metadata_root = repository_root / "metadata"
    source_root.mkdir()
    _copy_confirmed_blank(repository_root)

    row_count = PREPARE.build_raw_processing_manifest(
        source_root,
        metadata_root,
        tmp_path / "missing_best_match_report.csv",
        tmp_path / "missing_inventory_report.csv",
        repository_root,
    )

    _, rows = _read_csv(metadata_root / "raw_processing_manifest.csv")
    assert row_count == 1
    assert rows == [{
        "file": "data/raw/4atp/optimisation/750_5_5_H/Blanck_AABC_750_5_5_H.csv",
        "record_group": "optimisation_750_5_5_h_confirmed_blank",
        "sample_type": "blank",
        "concentration_molar": "",
        "replicate": "unresolved",
        "accumulation": "expanded_column",
        "instrument": "portable_raman",
        "acquisition": "750_5_5_H",
        "provenance_status": "raw_author_confirmed",
    }]


def _release_fixture(repository_root: Path) -> list[Path]:
    release_root = repository_root / PREPARE.CONFIRMED_4ATP_REANALYSIS_RELEASE_ROOT
    paths = [
        release_root / "controlled_legacy_confirmed_blank" / "spectra.csv",
        release_root / "reference_2026" / "spectra.csv",
        release_root / "comparison" / "sample_metrics.csv",
    ]
    for index, path in enumerate(paths, start=1):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"x,y\n{index},{index + 1}\n", encoding="utf-8")
    return paths


def test_reanalysis_release_is_fully_manifested_with_conservative_statuses(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    release_paths = _release_fixture(repository_root)
    manifest: list[dict[str, object]] = []
    status_counts: Counter[str] = Counter()

    release_counts = PREPARE.add_confirmed_4atp_reanalysis_manifest_entries(
        repository_root,
        manifest,
        status_counts,
    )

    assert release_counts == {
        "regenerated_partial_provenance": 2,
        "audit_evidence": 1,
    }
    assert status_counts == release_counts
    expected_release_paths = sorted(
        path.relative_to(repository_root).as_posix() for path in release_paths
    )
    assert [row["repository_path"] for row in manifest] == expected_release_paths
    by_package = {
        Path(str(row["repository_path"])).parts[-2]: row for row in manifest
    }
    assert by_package["controlled_legacy_confirmed_blank"]["role"] == (
        "controlled_legacy_confirmed_blank_output"
    )
    assert by_package["reference_2026"]["status"] == (
        "regenerated_partial_provenance"
    )
    assert by_package["comparison"]["status"] == "audit_evidence"
    assert all(row["repository_sha256"] for row in manifest)
    assert all(row["repository_bytes"] for row in manifest)


def test_refresh_reanalysis_metadata_preserves_base_rows_and_needs_no_archive(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    metadata_root = repository_root / "metadata"
    metadata_root.mkdir(parents=True)
    release_paths = _release_fixture(repository_root)
    base_path = repository_root / "data" / "raw" / "base.csv"
    base_path.parent.mkdir(parents=True)
    base_path.write_text("x,y\n1,2\n", encoding="utf-8")
    base_row = {
        "repository_path": "data/raw/base.csv",
        "source_name": "fixture",
        "source_relative_path": "base.csv",
        "source_sha256": PREPARE.sha256_file(base_path),
        "repository_sha256": PREPARE.sha256_file(base_path),
        "source_bytes": base_path.stat().st_size,
        "repository_bytes": base_path.stat().st_size,
        "status": "raw_unverified",
        "role": "raw_spectrum",
        "sanitized_user_path_occurrences": 0,
        "note": "Stable base row.",
    }
    old_release_row = dict(base_row)
    old_release_row.update(
        {
            "repository_path": (
                "data/processed/4atp/optimisation/750_5_5_H/"
                "reference_2026/obsolete.csv"
            ),
            "status": "regenerated_partial_provenance",
        }
    )
    PREPARE.write_csv(
        metadata_root / "dataset_manifest.csv",
        PREPARE.DATASET_MANIFEST_FIELDS,
        [base_row, old_release_row],
    )
    (metadata_root / "curation_summary.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dataset_manifest_rows": 2,
                "copied_audit_report_count": 0,
                "status_counts": {
                    "raw_unverified": 1,
                    "regenerated_partial_provenance": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    sidecar = metadata_root / "proof_of_concept_code_crosswalk.csv"
    sidecar.write_bytes(b"sentinel-sidecar\n")

    assert PREPARE.main(
        [
            "--repository-root",
            str(repository_root),
            "--refresh-reanalysis-metadata",
        ]
    ) == 0

    _, rows = _read_csv(metadata_root / "dataset_manifest.csv")
    assert rows[0] == {key: str(value) for key, value in base_row.items()}
    expected_release_paths = sorted(
        path.relative_to(repository_root).as_posix() for path in release_paths
    )
    assert [row["repository_path"] for row in rows[1:]] == expected_release_paths
    summary = json.loads(
        (metadata_root / "curation_summary.json").read_text(encoding="utf-8")
    )
    assert summary["dataset_manifest_rows"] == 4
    assert summary["regenerated_4atp_release_file_count"] == 3
    assert summary["copied_audit_report_count"] == 1
    assert summary["status_counts"] == {
        "audit_evidence": 1,
        "raw_unverified": 1,
        "regenerated_partial_provenance": 2,
    }
    assert sidecar.read_bytes() == b"sentinel-sidecar\n"


def test_refresh_refuses_interleaved_release_rows_that_would_shift_ids(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    metadata_root = repository_root / "metadata"
    metadata_root.mkdir(parents=True)
    _release_fixture(repository_root)
    base = {field: "" for field in PREPARE.DATASET_MANIFEST_FIELDS}
    base["repository_path"] = "data/raw/base.csv"
    release = dict(base)
    release["repository_path"] = (
        "data/processed/4atp/optimisation/750_5_5_H/reference_2026/old.csv"
    )
    later_base = dict(base)
    later_base["repository_path"] = "data/raw/later.csv"
    PREPARE.write_csv(
        metadata_root / "dataset_manifest.csv",
        PREPARE.DATASET_MANIFEST_FIELDS,
        [base, release, later_base],
    )
    (metadata_root / "curation_summary.json").write_text("{}\n", encoding="utf-8")

    try:
        PREPARE.refresh_confirmed_4atp_reanalysis_metadata(repository_root)
    except RuntimeError as exc:
        assert "refusing to change established dataset_manifest_row" in str(exc)
    else:
        raise AssertionError("Interleaved release rows should be rejected")


def test_reanalysis_manifesting_rejects_an_incomplete_release(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    incomplete = (
        repository_root
        / PREPARE.CONFIRMED_4ATP_REANALYSIS_RELEASE_ROOT
        / "reference_2026"
        / "spectra.csv"
    )
    incomplete.parent.mkdir(parents=True)
    incomplete.write_text("x,y\n1,2\n", encoding="utf-8")

    try:
        PREPARE.add_confirmed_4atp_reanalysis_manifest_entries(
            repository_root,
            [],
            Counter(),
        )
    except RuntimeError as exc:
        assert "release is incomplete" in str(exc)
        assert "comparison" in str(exc)
        assert "controlled_legacy_confirmed_blank" in str(exc)
    else:
        raise AssertionError("An incomplete reanalysis release should be rejected")
