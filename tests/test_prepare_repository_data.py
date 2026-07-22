from __future__ import annotations

import csv
from pathlib import Path

from scripts import prepare_repository_data as PREPARE


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


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
        Path("provenance_conflicts.csv"),
        Path("provenance/shared_blank_origin_summary.csv"),
        Path("provenance/4atp_blank_family_assessment.csv"),
    )
    for relative_path in generated_paths:
        assert _read_csv(metadata_root / relative_path) == _read_csv(
            PROJECT_ROOT / "metadata" / relative_path
        )
