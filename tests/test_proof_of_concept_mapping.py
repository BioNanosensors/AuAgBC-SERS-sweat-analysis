from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "proof_of_concept_mapping.py"
SPEC = importlib.util.spec_from_file_location("proof_of_concept_mapping", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MAPPING = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MAPPING
SPEC.loader.exec_module(MAPPING)


def _rows(relative_path: str) -> list[dict[str, str]]:
    with (PROJECT_ROOT / relative_path).open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        return list(csv.DictReader(handle))


def test_committed_mapping_sidecars_and_publication_files_are_current() -> None:
    assert MAPPING.verify(PROJECT_ROOT) == []


def test_confirmed_crosswalk_separates_acquisition_and_publication_numbers() -> None:
    rows = _rows("metadata/proof_of_concept_code_crosswalk.csv")

    assert {
        row["acquisition_v_code"]: row["acquisition_p_code"] for row in rows
    } == {"V1": "P1", "V2": "P2", "V3": "P3", "V4": "P4"}
    assert {
        row["acquisition_index"]: row["publication_index"] for row in rows
    } == {"1": "", "2": "1", "3": "2", "4": "3"}
    assert rows[0]["included_in_figure6"] == "false"
    assert rows[0]["reason"] == "no_usable_signal"
    assert [row["publication_code"] for row in rows[1:]] == ["V1", "V2", "V3"]


def test_all_publication_tables_use_v1_through_v3_headers() -> None:
    expected = {
        "benchtop_sweat_summary.csv": [
            "Raman shift (cm-1)",
            "RM_AS",
            "RM_HS_V1",
            "RM_HS_V2",
            "RM_HS_V3",
        ],
        "portable_sweat_summary.csv": [
            "Raman shift (cm-1)",
            "RP_AS",
            "RP_HS_V1",
            "RP_HS_V2",
            "RP_HS_V3",
        ],
        "benchtop_vs_portable_normalized.csv": [
            "Raman_shift_cm-1",
            "Benchtop AS",
            "Portable AS",
            "Benchtop V1",
            "Portable V1",
            "Benchtop V2",
            "Portable V2",
            "Benchtop V3",
            "Portable V3",
        ],
    }
    root = PROJECT_ROOT / "data" / "published_snapshot" / "proof_of_concept"
    for filename, header in expected.items():
        with (root / filename).open("r", encoding="utf-8-sig", newline="") as handle:
            assert next(csv.reader(handle)) == header


def test_header_rewrite_preserves_every_numerical_body_byte(tmp_path: Path) -> None:
    specification = MAPPING.PUBLICATION_FILES["RM_AS_HS.csv"]
    body = b"2260.0,1,2,3,4\r\n2259.0,5,6,7,8\r\n"
    path = tmp_path / "summary.csv"
    path.write_bytes(
        MAPPING.UTF8_BOM
        + specification["source_header"].encode("utf-8")
        + b"\r\n"
        + body
    )

    assert MAPPING.correct_publication_header(path, "RM_AS_HS.csv") is True
    bom, header, rewritten_body = MAPPING._split_first_record(path.read_bytes())

    assert bom == MAPPING.UTF8_BOM
    assert header.decode("utf-8") == specification["publication_header"]
    assert rewritten_body == body
    assert path.read_bytes().split(body, 1)[0].endswith(b"\r\n")
    assert MAPPING.correct_publication_header(path, "RM_AS_HS.csv") is False


def test_label_evidence_covers_raw_mismatches_and_resolves_duplicate_namespace() -> None:
    rows = _rows("metadata/provenance/proof_of_concept_label_evidence.csv")
    by_manifest_row = {row["dataset_manifest_row"]: row for row in rows}

    assert {"1704", "1705", "1709", "1710", "1711", "1712"}.issubset(
        by_manifest_row
    )
    assert {
        row["dataset_manifest_row"]
        for row in rows
        if row["evidence_scope"] == "complete_portable_raw_human_mismatch_set"
    } == {"1704", "1705", "1709", "1710", "1711", "1712"}
    for row_number in ("1704", "1705"):
        row = by_manifest_row[row_number]
        assert row["observed_embedded_or_internal_label"] == "V2S2"
        assert row["confirmed_acquisition_label"] == "V2S1"
        assert row["confirmed_publication_label"] == "V1S1"
        assert row["resolution_status"] == "resolved_embedded_session_metadata_error"

    duplicate_rows = [by_manifest_row["1694"], by_manifest_row["1700"]]
    assert len({row["artifact_sha256"] for row in duplicate_rows}) == 1
    assert {row["confirmed_acquisition_label"] for row in duplicate_rows} == {
        "V3S1"
    }
    assert {row["confirmed_publication_label"] for row in duplicate_rows} == {
        "V2S1"
    }


def test_all_distributed_apparent_v1_p1_spectra_resolve_to_acquisition_2() -> None:
    rows = _rows("metadata/provenance/proof_of_concept_label_evidence.csv")
    by_manifest_row = {row["dataset_manifest_row"]: row for row in rows}
    apparent_v1_p1_rows = {
        "1678",
        "1693",
        "1704",
        "1705",
        "1709",
        "1710",
        "1713",
        "1714",
        "1718",
        "1722",
    }

    assert apparent_v1_p1_rows.issubset(by_manifest_row)
    for row_number in apparent_v1_p1_rows:
        assert by_manifest_row[row_number]["confirmed_acquisition_label"] in {
            "V2",
            "V2S1",
            "P2S1",
            "P2S3",
            "V2|P2",
        }

    assert by_manifest_row["1678"]["confirmed_acquisition_label"] == "V2"
    assert by_manifest_row["1678"]["confirmed_publication_label"] == "V1"
    assert by_manifest_row["1693"]["confirmed_acquisition_label"] == "V2"
    assert by_manifest_row["1693"]["confirmed_publication_label"] == "V1"


def test_benchtop_composite_is_exactly_assembled_from_v2_source_columns() -> None:
    root = (
        PROJECT_ROOT
        / "data"
        / "quarantine"
        / "legacy_snapshot"
        / "Proof of concept"
        / "Benchtop Raman"
    )

    def read(relative_path: str) -> list[list[str]]:
        with (root / relative_path).open(
            "r", encoding="utf-8-sig", newline=""
        ) as handle:
            return list(csv.reader(handle))

    composite = read(
        "Original spectra/"
        "HS_V1S3_AAB_C1_S4_I1_I2_V2S2_C2_I1_I2_I3_C1_I1_I2_I3_"
        "V2S1_C4_S5_I2_I3_C4_S2_I2.csv"
    )
    sources = [
        read("Original spectra/HS_V2S3_AAB_C1_S4_I1_I2.csv"),
        read("Original spectra/HS_V2S2_AAB_C2_I1_I2_I3.csv"),
        read("Original spectra/HS_V2S2_AAB_C1_I1_I2_I3.csv"),
        read("Original spectra/HS_V2S1_AAB_C4_S5_I2_I3.csv"),
        read("Original spectra/HS_V2S1_AAB_C4_S2_I2.csv"),
    ]
    assert all(len(source) == len(composite) for source in sources)
    for row_index, composite_row in enumerate(composite[1:], start=1):
        assert all(source[row_index][0] == composite_row[0] for source in sources)
        expected = [composite_row[0]]
        for source in sources:
            expected.extend(source[row_index][1:])
        assert composite_row == expected

    processed = read(
        "Processed spectra/"
        "HS_V1S3_AAB_C1_S4_I1_I2_V1S2_C2_I1_I2_I3_C1_I1_I2_I3_"
        "V1S1_C4_S5_I2_I3_C4_S2_I2_blank_subtracted_processed.csv"
    )
    assert all(header.startswith("HS_V2") for header in processed[0][1:])


def test_quarantined_instrument_metadata_remains_historical_evidence() -> None:
    root = (
        PROJECT_ROOT
        / "data"
        / "quarantine"
        / "legacy_snapshot"
        / "Proof of concept"
        / "Portable Raman"
        / "Original spectra"
    )
    for filename in ("AA_HS_V1S1_H.csv", "AA_HS_V1S1_H_2.csv"):
        content = (root / filename).read_bytes()
        assert b"Name,AA_HS_V2S2_H.csv" in content
        assert b"Tag,AA_HS_V2S2_H" in content
        assert b"Name,AA_HS_V2S1_H.csv" not in content
