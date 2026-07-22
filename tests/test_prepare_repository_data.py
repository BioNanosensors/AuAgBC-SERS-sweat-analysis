from __future__ import annotations

import csv
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
