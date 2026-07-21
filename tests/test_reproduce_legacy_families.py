from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts.reproduce_legacy_families import (
    FAMILIES,
    PreparedFamily,
    ReproductionError,
    _pipeline_command,
    prepare_family_manifests,
)


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_generated_family_manifests_are_exact_deterministic_filters(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    first = prepare_family_manifests(repository, manifest_directory=tmp_path)
    first_bytes = {item.spec.record_group: item.manifest_path.read_bytes() for item in first}
    second = prepare_family_manifests(repository, manifest_directory=tmp_path)
    source_rows = _rows(repository / "metadata" / "raw_processing_manifest.csv")

    assert {item.spec for item in first} == set(FAMILIES)
    assert first_bytes == {item.spec.record_group: item.manifest_path.read_bytes() for item in second}
    for item in second:
        expected = [row for row in source_rows if row["record_group"] == item.spec.record_group]
        expected.sort(key=lambda row: (row["file"].replace("\\", "/").casefold(), row["file"]))
        assert _rows(item.manifest_path) == expected
        assert item.row_count == item.spec.expected_rows


def test_pipeline_command_rejects_an_unknown_output_target(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    unsafe = PreparedFamily(
        spec=FAMILIES[0],
        manifest_path=tmp_path / "manifest.csv",
        output_path=tmp_path / "not-a-known-output",
        row_count=FAMILIES[0].expected_rows,
    )
    with pytest.raises(ReproductionError, match="unrecognised output target"):
        _pipeline_command(repository, unsafe)
