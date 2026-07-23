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
    (provenance_root / "4atp_blank_search_summary.csv").write_text(
        "stale\n", encoding="utf-8"
    )
    (provenance_root / "4atp_blank_unresolved_candidates.csv").write_text(
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
        Path("provenance/4atp_blank_search_summary.csv"),
        Path("provenance/4atp_blank_unresolved_candidates.csv"),
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
    release_paths = [
        release_root / "controlled_legacy_confirmed_blank" / "spectra.csv",
        release_root / "reference_2026" / "spectra.csv",
        release_root / "comparison" / "sample_metrics.csv",
    ]
    for index, path in enumerate(release_paths, start=1):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"x,y\n{index},{index + 1}\n", encoding="utf-8")
    cutoff_lock = repository_root / PREPARE.CONFIRMED_4ATP_FFT_CUTOFF_LOCK
    cutoff_lock.parent.mkdir(parents=True, exist_ok=True)
    cutoff_lock.write_text(
        "lineage,record_id,filter_fft_peak_index\nfixture,row1,1\n",
        encoding="utf-8",
    )
    return [cutoff_lock, *release_paths]


def _medium_replay_fixture(repository_root: Path) -> list[Path]:
    source_root = repository_root / PREPARE.MEDIUM_4ATP_REPLAY_SOURCE_ROOT
    sample_root = source_root / "samples"
    blank = source_root / "historical_blank" / "AAB_Blank.csv"
    sample_root.mkdir(parents=True)
    blank.parent.mkdir(parents=True)
    sources: list[Path] = []
    for index in range(1, 40):
        path = sample_root / f"AAB_fixture_{index:02d}.csv"
        path.write_text(f"x,y\n{index},{index + 1}\n", encoding="utf-8")
        sources.append(path)
    for index in range(1, 4):
        path = sample_root / f"BC_fixture_{index:02d}.csv"
        path.write_text(f"x,y\n{index},{index + 1}\n", encoding="utf-8")
        sources.append(path)
    blank.write_text("x,y\n1,2\n", encoding="utf-8")
    sources.append(blank)

    release_root = repository_root / PREPARE.MEDIUM_4ATP_REPLAY_RELEASE_ROOT
    release_root.mkdir(parents=True)
    release_paths: list[Path] = []
    for name in sorted(PREPARE.MEDIUM_4ATP_REPLAY_REQUIRED_FILES):
        path = release_root / name
        path.write_text(f"fixture {name}\n", encoding="utf-8")
        release_paths.append(path)
    lock = repository_root / PREPARE.MEDIUM_4ATP_FFT_CUTOFF_LOCK
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("record_id,filter_fft_peak_index\nrow1,1\n", encoding="utf-8")
    return [*sources, lock, *release_paths]


def test_medium_replay_sources_and_release_remain_conservatively_classified(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    fixture_paths = _medium_replay_fixture(repository_root)
    manifest: list[dict[str, object]] = []
    status_counts: Counter[str] = Counter()

    replay_counts = PREPARE.add_medium_4atp_replay_manifest_entries(
        repository_root,
        manifest,
        status_counts,
    )

    assert replay_counts == {
        "raw_unverified": 42,
        "provenance_conflict": 1,
        "audit_evidence": 6,
    }
    assert status_counts == replay_counts
    assert len(manifest) == len(fixture_paths) == 49
    by_path = {str(row["repository_path"]): row for row in manifest}
    source_prefix = PREPARE.MEDIUM_4ATP_REPLAY_SOURCE_ROOT.as_posix() + "/"
    source_rows = [
        row
        for path, row in by_path.items()
        if path.startswith(source_prefix)
    ]
    assert len(source_rows) == 43
    assert sum(row["status"] == "raw_unverified" for row in source_rows) == 42
    blank_path = (
        PREPARE.MEDIUM_4ATP_REPLAY_SOURCE_ROOT
        / "historical_blank"
        / "AAB_Blank.csv"
    ).as_posix()
    assert by_path[blank_path]["status"] == "provenance_conflict"
    assert by_path[blank_path]["role"] == "historical_blank_composite_source"
    release_prefix = PREPARE.MEDIUM_4ATP_REPLAY_RELEASE_ROOT.as_posix() + "/"
    assert sum(path.startswith(release_prefix) for path in by_path) == 5
    assert all(row["repository_sha256"] for row in manifest)


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
    assert status_counts == {
        "regenerated_partial_provenance": 2,
        "audit_evidence": 2,
    }
    expected_release_paths = [
        PREPARE.CONFIRMED_4ATP_FFT_CUTOFF_LOCK.as_posix(),
        *sorted(
            path.relative_to(repository_root).as_posix()
            for path in release_paths
            if path != repository_root / PREPARE.CONFIRMED_4ATP_FFT_CUTOFF_LOCK
        ),
    ]
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
    validation_report_path = (
        repository_root
        / PREPARE.PERSISTENT_MANIFEST_FINGERPRINT_PATHS[0]
    )
    validation_report_path.parent.mkdir(parents=True)
    validation_report_path.write_text(
        "Updated persistent validation report.\n",
        encoding="utf-8",
    )
    validation_report_row = dict(base_row)
    validation_report_row.update(
        {
            "repository_path": (
                PREPARE.PERSISTENT_MANIFEST_FINGERPRINT_PATHS[0].as_posix()
            ),
            "repository_sha256": "stale",
            "repository_bytes": 0,
            "status": "audit_evidence",
            "role": "numerical_validation",
            "note": "Persistent report with a supersession notice.",
        }
    )
    PREPARE.write_csv(
        metadata_root / "dataset_manifest.csv",
        PREPARE.DATASET_MANIFEST_FIELDS,
        [base_row, validation_report_row, old_release_row],
    )
    (metadata_root / "curation_summary.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dataset_manifest_rows": 3,
                "copied_audit_report_count": 1,
                "status_counts": {
                    "audit_evidence": 1,
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
    assert rows[1]["repository_path"] == (
        PREPARE.PERSISTENT_MANIFEST_FINGERPRINT_PATHS[0].as_posix()
    )
    assert rows[1]["repository_sha256"] == PREPARE.sha256_file(
        validation_report_path
    )
    assert rows[1]["repository_bytes"] == str(validation_report_path.stat().st_size)
    expected_release_paths = [
        PREPARE.CONFIRMED_4ATP_FFT_CUTOFF_LOCK.as_posix(),
        *sorted(
            path.relative_to(repository_root).as_posix()
            for path in release_paths
            if path != repository_root / PREPARE.CONFIRMED_4ATP_FFT_CUTOFF_LOCK
        ),
    ]
    assert [row["repository_path"] for row in rows[2:]] == expected_release_paths
    summary = json.loads(
        (metadata_root / "curation_summary.json").read_text(encoding="utf-8")
    )
    assert summary["dataset_manifest_rows"] == 6
    assert summary["regenerated_4atp_release_file_count"] == 3
    assert summary["copied_audit_report_count"] == 3
    assert summary["status_counts"] == {
        "audit_evidence": 3,
        "raw_unverified": 1,
        "regenerated_partial_provenance": 2,
    }
    assert sidecar.read_bytes() == b"sentinel-sidecar\n"


def test_refresh_manages_high_and_medium_release_rows_as_one_stable_suffix(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    metadata_root = repository_root / "metadata"
    metadata_root.mkdir(parents=True)
    high_paths = _release_fixture(repository_root)
    _medium_replay_fixture(repository_root)
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
    old_high = dict(base_row)
    old_high["repository_path"] = (
        "data/processed/4atp/optimisation/750_5_5_H/reference_2026/old.csv"
    )
    old_medium = dict(base_row)
    old_medium["repository_path"] = (
        PREPARE.MEDIUM_4ATP_REPLAY_RELEASE_ROOT / "old.csv"
    ).as_posix()
    PREPARE.write_csv(
        metadata_root / "dataset_manifest.csv",
        PREPARE.DATASET_MANIFEST_FIELDS,
        [base_row, old_high, old_medium],
    )
    (metadata_root / "curation_summary.json").write_text(
        "{}\n", encoding="utf-8"
    )

    report = PREPARE.refresh_confirmed_4atp_reanalysis_metadata(repository_root)

    _, rows = _read_csv(metadata_root / "dataset_manifest.csv")
    assert rows[0] == {key: str(value) for key, value in base_row.items()}
    high_expected = [
        PREPARE.CONFIRMED_4ATP_FFT_CUTOFF_LOCK.as_posix(),
        *sorted(
            path.relative_to(repository_root).as_posix()
            for path in high_paths
            if path != repository_root / PREPARE.CONFIRMED_4ATP_FFT_CUTOFF_LOCK
        ),
    ]
    assert [row["repository_path"] for row in rows[1:5]] == high_expected
    assert len(rows) == 54
    assert report["dataset_manifest_rows"] == 54
    assert report["regenerated_4atp_release_file_count"] == 8
    assert report["medium_power_computational_replay_source_file_count"] == 43
    assert report["medium_power_computational_replay_file_count"] == 5
    assert report["status_counts"] == {
        "audit_evidence": 8,
        "provenance_conflict": 1,
        "raw_unverified": 43,
        "regenerated_partial_provenance": 2,
    }


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
