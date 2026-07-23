from __future__ import annotations

import csv
import importlib.util
import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "reprocess_4atp_750_5_5_h.py"
SPEC = importlib.util.spec_from_file_location("reprocess_4atp_750_5_5_h", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
REPROCESS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = REPROCESS
SPEC.loader.exec_module(REPROCESS)


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_controlled_manifest_has_one_confirmed_blank_and_explicit_lambdas() -> None:
    rows = REPROCESS.build_manifest_rows(
        PROJECT_ROOT, lineage=REPROCESS.CONTROLLED_NAME
    )
    samples = [row for row in rows if row["sample_type"] == "4atp"]
    blanks = [row for row in rows if row["sample_type"] == "blank"]

    assert len(rows) == 200
    assert len(samples) == 195
    assert len(blanks) == 5
    assert {row["record_group"] for row in rows} == {
        REPROCESS.ANALYSIS_RECORD_GROUP
    }
    assert {row["source_record_group"] for row in samples} == {
        REPROCESS.SOURCE_RECORD_GROUP
    }
    assert {row["file"] for row in blanks} == {
        REPROCESS.CONFIRMED_BLANK_RELATIVE.as_posix()
    }
    assert {row["source_record_group"] for row in blanks} == {
        REPROCESS.CONFIRMED_BLANK_SOURCE_GROUP
    }
    assert {row["replicate"] for row in blanks} == {"1"}
    assert {row["accumulation"] for row in blanks} == {"1", "2", "3", "4", "5"}
    assert {row["intensity_column"] for row in blanks} == {
        "1",
        "2",
        "3",
        "4",
        "5",
    }
    assert {row["baseline_lambda"] for row in samples} == {"3000"}
    assert {row["baseline_lambda"] for row in blanks} == {"8000"}
    assert {row["provenance_status"] for row in samples} == {"raw_unverified"}
    assert {row["provenance_status"] for row in blanks} == {
        "raw_author_confirmed"
    }
    assert all("blank_rep" not in row["file"].casefold() for row in rows)


def test_reference_manifest_does_not_inherit_legacy_blank_lambda() -> None:
    rows = REPROCESS.build_manifest_rows(
        PROJECT_ROOT, lineage=REPROCESS.REFERENCE_NAME
    )

    assert len(rows) == 200
    assert {row["baseline_lambda"] for row in rows} == {""}
    assert {row["analysis_lineage"] for row in rows} == {
        REPROCESS.REFERENCE_NAME
    }


def test_concentration_contract_is_thirteen_by_fifteen_and_uses_100_micromolar() -> None:
    rows = REPROCESS.build_manifest_rows(
        PROJECT_ROOT, lineage=REPROCESS.CONTROLLED_NAME
    )
    samples = [row for row in rows if row["sample_type"] == "4atp"]
    counts = Counter(Decimal(row["concentration_molar"]) for row in samples)

    assert counts == Counter({concentration: 15 for concentration in REPROCESS.CONCENTRATION_LABELS})
    hundred_micromolar = [
        row for row in samples if Decimal(row["concentration_molar"]) == Decimal("1e-4")
    ]
    assert len(hundred_micromolar) == 15
    assert {row["concentration_label"] for row in hundred_micromolar} == {"100 µM"}
    assert all(row["concentration_label"] != "100 mM" for row in samples)
    expected_design = {
        (str(replicate), str(accumulation))
        for replicate in range(1, 4)
        for accumulation in range(1, 6)
    }
    for concentration in REPROCESS.CONCENTRATION_LABELS:
        rows_at_concentration = [
            row
            for row in samples
            if Decimal(row["concentration_molar"]) == concentration
        ]
        assert {
            (row["replicate"], row["accumulation"])
            for row in rows_at_concentration
        } == expected_design
    assert {row["instrument"] for row in samples} == {"portable_raman"}
    assert {row["acquisition"] for row in samples} == {"750_5_5_H"}


def test_committed_manifests_and_configs_are_deterministic_and_explicit() -> None:
    expected = REPROCESS.expected_configuration_files(PROJECT_ROOT)

    assert REPROCESS.check_configuration_files(PROJECT_ROOT) == []
    assert all(path.read_bytes() == content for path, content in expected.items())
    controlled_config = json.loads(
        (PROJECT_ROOT / REPROCESS.CONFIG_DIRECTORY_RELATIVE / REPROCESS.CONTROLLED_CONFIG_NAME).read_text(
            encoding="utf-8"
        )
    )
    reference_config = json.loads(
        (PROJECT_ROOT / REPROCESS.CONFIG_DIRECTORY_RELATIVE / REPROCESS.REFERENCE_CONFIG_NAME).read_text(
            encoding="utf-8"
        )
    )
    for config in (controlled_config, reference_config):
        assert config["input_root"] == "../.."
        assert config["options"]["blank"]["group_by"] == [
            "record_group",
            "instrument",
        ]
        assert config["options"]["aggregation"]["group_by"] == ["record_group"]
    assert controlled_config["profile"] == "legacy_individual"
    assert controlled_config["options"]["blank"]["stage"] == "raw"
    assert reference_config["profile"] == "reference_2026"
    assert reference_config["options"]["blank"]["stage"] == "processed"


def test_metric_direction_is_right_minus_left() -> None:
    left = np.array([1.0, 2.0, 3.0])
    right = np.array([2.0, 4.0, 6.0])

    metrics = REPROCESS._metrics(left, right)

    assert metrics["mean_signed_difference"] == 2.0
    assert np.isclose(metrics["rmse"], np.sqrt(14.0 / 3.0))
    assert metrics["mae"] == 2.0
    assert metrics["max_abs"] == 3.0
    assert metrics["pearson_r"] == 1.0


def test_committed_manifest_csv_matches_builder_rows() -> None:
    controlled_path = (
        PROJECT_ROOT
        / REPROCESS.CONFIG_DIRECTORY_RELATIVE
        / REPROCESS.CONTROLLED_MANIFEST_NAME
    )
    reference_path = (
        PROJECT_ROOT
        / REPROCESS.CONFIG_DIRECTORY_RELATIVE
        / REPROCESS.REFERENCE_MANIFEST_NAME
    )

    assert _read_rows(controlled_path) == REPROCESS.build_manifest_rows(
        PROJECT_ROOT, lineage=REPROCESS.CONTROLLED_NAME
    )
    assert _read_rows(reference_path) == REPROCESS.build_manifest_rows(
        PROJECT_ROOT, lineage=REPROCESS.REFERENCE_NAME
    )


def test_release_metadata_records_environment_code_and_warning_scopes() -> None:
    release_root = PROJECT_ROOT / REPROCESS.RELEASE_ROOT_RELATIVE
    expected_dependencies = {
        "PyYAML": "6.0.3",
        "numpy": "2.5.0",
        "pandas": "3.0.3",
        "pybaselines": "1.2.1",
        "pytest": "9.1.1",
        "scipy": "1.18.0",
    }
    metadata_by_lineage: dict[str, dict[str, object]] = {}
    for lineage in (REPROCESS.CONTROLLED_NAME, REPROCESS.REFERENCE_NAME):
        metadata = json.loads(
            (release_root / lineage / "package_metadata.json").read_text(
                encoding="utf-8"
            )
        )
        metadata_by_lineage[lineage] = metadata
        software = metadata["software_environment"]
        assert software["python"] == "3.12.13"
        assert software["dependencies"] == expected_dependencies
        assert metadata["run_warnings"] == []
        assert "warnings" not in metadata
        constraints = metadata["environment_constraints"]
        assert constraints["path"] == "requirements-release.txt"
        assert constraints["sha256"] == REPROCESS.sha256_file(
            PROJECT_ROOT / "requirements-release.txt"
        )
        for code_file in metadata["code_identity"]:
            path = PROJECT_ROOT / code_file["path"]
            assert path.is_file()
            assert code_file["sha256"] == REPROCESS.sha256_file(path)

    controlled = metadata_by_lineage[REPROCESS.CONTROLLED_NAME]
    assert controlled["record_warning_counts"] == {
        "Raman-shift spacing is non-uniform (relative SD 0.221); FFT used the median spacing.": 200
    }
    assert controlled["historical_replay_validation"]["status"] == "pass"
    assert controlled["historical_replay_validation"]["spectra_compared"] == 210
    reference = metadata_by_lineage[REPROCESS.REFERENCE_NAME]
    assert reference["record_warning_counts"] == {}
    assert reference["numerical_library_warnings"]


def test_persistent_generation_environment_guard_rejects_version_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = REPROCESS._expected_release_packages(PROJECT_ROOT)
    monkeypatch.setattr(
        REPROCESS.platform,
        "python_version",
        lambda: REPROCESS.CANONICAL_PYTHON_VERSION,
    )
    monkeypatch.setattr(
        REPROCESS,
        "_installed_distribution_version",
        lambda distribution: expected[distribution],
    )
    report = REPROCESS._validate_canonical_release_environment(PROJECT_ROOT)
    assert report["python"] == REPROCESS.CANONICAL_PYTHON_VERSION
    assert report["packages"] == dict(
        sorted(expected.items(), key=lambda item: item[0].casefold())
    )

    monkeypatch.setattr(
        REPROCESS,
        "_installed_distribution_version",
        lambda distribution: "0.0.0" if distribution == "numpy" else expected[distribution],
    )
    with pytest.raises(REPROCESS.ReanalysisError, match="numpy 0.0.0"):
        REPROCESS._validate_canonical_release_environment(PROJECT_ROOT)
