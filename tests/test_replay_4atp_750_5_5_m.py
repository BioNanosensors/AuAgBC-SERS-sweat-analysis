from __future__ import annotations

import copy
import csv
import hashlib
import importlib.util
import io
import json
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONFIG_ROOT = REPOSITORY_ROOT / "configs" / "reanalysis"
CONFIG_PATH = (
    CONFIG_ROOT / "optimisation_750_5_5_m_historical_replay.json"
)
SOURCE_INVENTORY_PATH = (
    CONFIG_ROOT / "optimisation_750_5_5_m_historical_replay_sources.csv"
)
CHANNEL_MANIFEST_PATH = (
    CONFIG_ROOT / "optimisation_750_5_5_m_historical_replay_manifest.csv"
)
FFT_LOCK_PATH = (
    REPOSITORY_ROOT
    / "metadata"
    / "processing_locks"
    / "optimisation_750_5_5_m_historical_replay_fft_cutoffs.csv"
)
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "replay_4atp_750_5_5_m.py"
PACKAGE_ROOT = (
    REPOSITORY_ROOT
    / "data"
    / "processed"
    / "4atp"
    / "optimisation"
    / "750_5_5_M"
    / "historical_computational_replay"
)
PACKAGE_FILES = {
    "README.md",
    "package_metadata.json",
    "resolved_manifest.csv",
    "replay_metrics.csv",
    "replayed_spectra.zip",
}


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_repository_relative(path_text: str) -> None:
    assert "\\" not in path_text
    path = PurePosixPath(path_text)
    assert not path.is_absolute()
    assert ".." not in path.parts
    assert not any(":" in part for part in path.parts)


def _load_replay_module():
    spec = importlib.util.spec_from_file_location(
        "replay_4atp_750_5_5_m_for_tests",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_contract_preserves_computational_only_scientific_boundary() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    inventory = _csv_rows(SOURCE_INVENTORY_PATH)
    manifest = _csv_rows(CHANNEL_MANIFEST_PATH)
    locks = _csv_rows(FFT_LOCK_PATH)

    assert config["claim_scope"] == "computational_lineage_only"
    assert config["release_classification"] == "audit_evidence_only"
    assert config["scientific_blank_status"] == "no_confirmed_medium_power_blank"
    assert config["blank_operation"]["source_record_id"] == "M750-CH-211"
    assert config["blank_operation"]["source_channel_index"] == 1
    assert config["blank_operation"]["status"] == "provenance_conflict"
    assert "does not prove" in config["interpretation_limit"]
    environment = config["validated_environment"]
    assert environment["generation_python"] == "3.12.13"
    assert environment["check_python"] == ["3.12.10", "3.12.13"]
    assert environment["system"] == "Windows"
    assert environment["machine"] == "AMD64"
    assert environment["zlib_compile"] == environment["zlib_runtime"] == "1.3.1"
    requirement_pins = {}
    for raw_line in (
        REPOSITORY_ROOT / "requirements-release.txt"
    ).read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if line:
            name, version = line.split("==", 1)
            requirement_pins[name] = version
    assert environment["packages"] == requirement_pins

    assert len(inventory) == 43
    assert Counter(row["lineage_role"] for row in inventory) == {
        "AAB_sample": 39,
        "BC_sample": 3,
        "assembled_blank": 1,
    }
    assert Counter(row["source_provenance_status"] for row in inventory) == {
        "raw_unverified": 42,
        "provenance_conflict": 1,
    }
    blank = next(row for row in inventory if row["lineage_role"] == "assembled_blank")
    assert blank["source_id"] == "M750-SRC-043"
    assert blank["source_sha256"] == (
        "ea9fa6fde91eca76dc1d2c281a7cd2aa0a544ba204293438f7523f3b5121bf77"
    )
    assert blank["embedded_name"] == "AAB_Blank_750_5_5_H.csv"
    assert blank["acquisition_code"] == "750_5_5_H"
    assert blank["scientific_blank_status"] == (
        "not_a_confirmed_medium_power_blank"
    )

    assert len(manifest) == 225
    assert Counter(row["sample_type"] for row in manifest) == {
        "AAB_4ATP_sample": 195,
        "BC_4ATP_sample": 15,
        "historical_blank_composite": 15,
    }
    sample_rows = [
        row for row in manifest if row["sample_type"] != "historical_blank_composite"
    ]
    blank_rows = [
        row for row in manifest if row["sample_type"] == "historical_blank_composite"
    ]
    assert len(sample_rows) == 210
    assert all(
        row["blank_reference_record_id"] == "M750-CH-211"
        for row in sample_rows
    )
    assert all(row["blank_context_match"] == "false" for row in sample_rows)
    assert all(row["blank_reference_record_id"] == "" for row in blank_rows)
    assert all(
        row["source_provenance_status"] == "provenance_conflict"
        for row in blank_rows
    )
    assert all(
        row["acquisition"]
        == "750 ms; 5 averages; 5 measurements; embedded H power code"
        for row in blank_rows
    )
    assert all(
        row["release_classification"] == "audit_evidence_only"
        for row in manifest
    )

    assert len(locks) == 225
    assert sum(int(row["tie_candidate_count"]) > 1 for row in locks) == 13
    assert sum(row["forensic_override"] == "true" for row in locks) == 5
    assert Counter(row["lock_basis"] for row in locks) == {
        "recovered_closest_percentile_rule": 220,
        "preserved_output_minimum_rmse_within_ulp_tie": 5,
    }
    assert "not recommended" in config["processing"]["fft_filter"]["locks"]

    for row in inventory:
        _assert_repository_relative(row["source_path"])
        _assert_repository_relative(row["historical_reference_path"])
    for row in manifest:
        _assert_repository_relative(row["source_path"])
        _assert_repository_relative(row["historical_reference_path"])
        _assert_repository_relative(row["output_zip_member"])


@pytest.mark.parametrize(
    ("section", "field", "replacement"),
    [
        ("blank_operation", "axis_alignment", "interpolate"),
        ("blank_operation", "operation", "axis_aligned_subtraction"),
        ("processing", "savgol", "applied"),
        ("acceptance", "intensity_rtol", 1e-5),
        ("deterministic_package", "zip_compression", "store"),
        ("deterministic_package", "text_encoding", "utf-16"),
    ],
)
def test_executable_contract_rejects_declarative_drift(
    section: str,
    field: str,
    replacement: object,
) -> None:
    replay = _load_replay_module()
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    replay.validate_declared_semantics(config)
    changed = copy.deepcopy(config)
    changed[section][field] = replacement
    with pytest.raises(replay.ReplayError):
        replay.validate_declared_semantics(changed)


def test_release_directory_transaction_rolls_back_then_commits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replay = _load_replay_module()
    monkeypatch.setattr(replay, "check_release", lambda *_: None)
    output = tmp_path / "historical_computational_replay"
    output.mkdir()
    old_files = {
        name: f"old:{name}\n".encode("utf-8") for name in PACKAGE_FILES
    }
    new_files = {
        name: f"new:{name}\n".encode("utf-8") for name in PACKAGE_FILES
    }
    for name, content in old_files.items():
        (output / name).write_bytes(content)

    with pytest.raises(RuntimeError, match="simulated post-publication failure"):
        with replay.published_release_transaction(output, new_files):
            assert {
                path.name: path.read_bytes() for path in output.iterdir()
            } == new_files
            raise RuntimeError("simulated post-publication failure")

    assert {
        path.name: path.read_bytes() for path in output.iterdir()
    } == old_files

    with replay.published_release_transaction(output, new_files):
        pass
    assert {
        path.name: path.read_bytes() for path in output.iterdir()
    } == new_files


def test_released_package_is_hash_bound_and_deterministic() -> None:
    assert {path.name for path in PACKAGE_ROOT.iterdir()} == PACKAGE_FILES
    metadata = json.loads(
        (PACKAGE_ROOT / "package_metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["claim_scope"] == "computational_lineage_only"
    assert metadata["release_classification"] == "audit_evidence_only"
    assert metadata["byte_identity_claimed"] is False
    assert metadata["scientific_blank_status"] == "no_confirmed_medium_power_blank"
    assert metadata["validated_environment"] == json.loads(
        CONFIG_PATH.read_text(encoding="utf-8")
    )["validated_environment"]
    assert metadata["observed"] == {
        "passing_channels": 225,
        "failing_channels": 0,
        "exact_axis_channels": 225,
        "exact_intensity_channels": 0,
        "worst_intensity_rmse": 6.294167560348376e-08,
        "worst_intensity_max_abs": 2.2915082809049636e-07,
        "fft_tie_channels": 13,
        "forensic_fft_overrides": 5,
    }

    contract_paths = {
        "config_sha256": CONFIG_PATH,
        "source_inventory_sha256": SOURCE_INVENTORY_PATH,
        "channel_manifest_sha256": CHANNEL_MANIFEST_PATH,
        "fft_locks_sha256": FFT_LOCK_PATH,
        "replay_script_sha256": SCRIPT_PATH,
    }
    assert metadata["hash_contract"] == {
        key: _sha256(path) for key, path in contract_paths.items()
    }
    assert metadata["package_file_hashes"] == {
        name: _sha256(PACKAGE_ROOT / name)
        for name in (
            "README.md",
            "resolved_manifest.csv",
            "replay_metrics.csv",
            "replayed_spectra.zip",
        )
    }

    resolved = _csv_rows(PACKAGE_ROOT / "resolved_manifest.csv")
    metrics = _csv_rows(PACKAGE_ROOT / "replay_metrics.csv")
    assert len(resolved) == len(metrics) == 225
    assert all(row["source_hash_verified"] == "true" for row in resolved)
    assert all(
        row["historical_reference_hash_verified"] == "true" for row in resolved
    )
    assert all(
        row["resolution_status"] == "computational_mapping_resolved"
        for row in resolved
    )
    resolved_blank_rows = [
        row
        for row in resolved
        if row["sample_type"] == "historical_blank_composite"
    ]
    assert len(resolved_blank_rows) == 15
    assert all(
        row["acquisition"]
        == "750 ms; 5 averages; 5 measurements; embedded H power code"
        for row in resolved_blank_rows
    )
    assert all(row["axis_array_equal"] == "true" for row in metrics)
    assert all(row["intensity_array_equal"] == "false" for row in metrics)
    assert all(row["within_tolerance"] == "true" for row in metrics)
    assert max(float(row["intensity_rmse"]) for row in metrics) <= 1e-7
    assert max(float(row["intensity_max_abs"]) for row in metrics) <= 1e-6

    with zipfile.ZipFile(PACKAGE_ROOT / "replayed_spectra.zip") as archive:
        members = archive.infolist()
        assert len(members) == 43
        assert [member.filename for member in members] == sorted(
            member.filename for member in members
        )
        assert all(member.filename.startswith("spectra/") for member in members)
        assert all(member.date_time == (1980, 1, 1, 0, 0, 0) for member in members)
        assert all((member.external_attr >> 16) == 0o100644 for member in members)
        for member in members:
            rows = list(
                csv.reader(
                    io.StringIO(
                        archive.read(member).decode("utf-8"),
                        newline="",
                    )
                )
            )
            assert len(rows) == 433


def test_dataset_manifest_covers_all_replay_files_conservatively() -> None:
    dataset_rows = _csv_rows(
        REPOSITORY_ROOT / "metadata" / "dataset_manifest.csv"
    )
    by_path = {row["repository_path"]: row for row in dataset_rows}
    inventory = _csv_rows(SOURCE_INVENTORY_PATH)
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    expected: dict[str, tuple[str, str]] = {}
    for source in inventory:
        role = (
            "historical_blank_composite_source"
            if source["lineage_role"] == "assembled_blank"
            else "historical_computational_replay_source"
        )
        expected[source["source_path"]] = (
            source["source_provenance_status"],
            role,
        )
        expected[source["historical_reference_path"]] = (
            "provenance_conflict",
            "processed_spectrum",
        )
    expected[config["paths"]["fft_locks"]] = (
        "audit_evidence",
        "processing_parameter_lock",
    )
    output_prefix = config["paths"]["output_directory"].rstrip("/")
    for name in PACKAGE_FILES:
        expected[f"{output_prefix}/{name}"] = (
            "audit_evidence",
            "historical_computational_replay",
        )

    assert len(expected) == 92
    for repository_path, (status, role) in expected.items():
        row = by_path[repository_path]
        file_path = REPOSITORY_ROOT / Path(*PurePosixPath(repository_path).parts)
        assert row["status"] == status
        assert row["role"] == role
        assert row["repository_sha256"] == _sha256(file_path)
        assert row["repository_bytes"] == str(file_path.stat().st_size)
