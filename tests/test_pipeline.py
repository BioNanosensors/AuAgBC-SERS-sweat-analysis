from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pytest

from auagbc_sers.errors import ConfigurationError, ProcessingError, VerificationError
from auagbc_sers.pipeline import load_job, process_job, verify_run


def _write_spectrum(path: Path, offset: float, peak: float) -> None:
    x = np.linspace(300.0, 1700.0, 181)
    y = offset + 0.02 * x + peak * np.exp(-0.5 * ((x - 1000.0) / 18.0) ** 2)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["Raman shift cm-1", "Intensity"])
        writer.writerows(zip(x, y))


def _make_job(tmp_path: Path, *, unmatched_group: bool = False) -> Path:
    files = {
        "blank_a1.csv": (100.0, 0.0, "blank", "experiment_a", 1, 1, None),
        "blank_a2.csv": (102.0, 0.0, "blank", "experiment_a", 1, 2, None),
        "sample_a1.csv": (150.0, 80.0, "sample", "experiment_a", 1, 1, 1e-9),
        "sample_a2.csv": (151.0, 84.0, "sample", "experiment_a", 1, 2, 1e-9),
    }
    if unmatched_group:
        files["sample_b1.csv"] = (150.0, 70.0, "sample", "experiment_b", 1, 1, 1e-8)
    rows = []
    for filename, (offset, peak, sample_type, group, replicate, accumulation, concentration) in files.items():
        _write_spectrum(tmp_path / filename, offset, peak)
        rows.append(
            {
                "file": filename,
                "record_group": group,
                "sample_type": sample_type,
                "concentration_molar": "" if concentration is None else concentration,
                "replicate": replicate,
                "accumulation": accumulation,
                "instrument": "portable_raman",
                "acquisition": 1,
                "provenance_status": "synthetic_test",
            }
        )
    manifest = tmp_path / "manifest.csv"
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    config = {
        "schema_version": "1.0",
        "profile": "reference_2026",
        "input_root": ".",
        "output_root": "out",
        "manifest": "manifest.csv",
        "blank": {
            "stage": "processed",
            "strategy": "mean",
            "group_by": ["record_group", "instrument"],
            "sample_types": ["blank"],
        },
        "options": {
            "crop": {"min_cm1": 350.0, "max_cm1": 1600.0},
            "grid": {
                "mode": "intersection",
                "step_cm1": None,
                "group_by": ["record_group", "instrument"],
            },
            "baseline": {"lambda": 300.0},
            "filter": {"method": "none"},
            "second_baseline": {"enabled": False},
            "post_blank_baseline": {"enabled": False},
            "peaks": [{"center_cm1": 1000.0, "window_cm1": 25.0, "method": "height", "label": "test"}],
            "aggregation": {"group_by": ["record_group"]},
        },
    }
    config_path = tmp_path / "job.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return config_path


def test_manifest_requires_explicit_scientific_metadata(tmp_path: Path) -> None:
    manifest = tmp_path / "bad.csv"
    manifest.write_text(
        "file,concentration_molar,replicate,accumulation,instrument,acquisition\n"
        "x.csv,,1,1,portable,1\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="sample_type"):
        load_job(manifest, output_root=tmp_path / "out", profile_name="legacy_individual")


def test_cli_path_overrides_resolve_from_cwd_not_manifest_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    manifest = metadata / "manifest.csv"
    manifest.write_text(
        "file,sample_type,concentration_molar,replicate,accumulation,instrument,acquisition\n"
        "data/a.csv,sample,1e-9,1,1,portable,1\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    job = load_job(manifest, input_root=".", output_root="outputs/run", profile_name="legacy_individual")
    assert job.input_root == tmp_path.resolve()
    assert job.output_root == (tmp_path / "outputs" / "run").resolve()


def test_end_to_end_outputs_are_deterministic_and_verifiable(tmp_path: Path) -> None:
    pytest.importorskip("pybaselines")
    config = _make_job(tmp_path)
    run = process_job(config)
    output = tmp_path / "out"
    expected = {
        "spectra_scan.csv",
        "spectra_replicate.csv",
        "spectra_concentration.csv",
        "peaks_scan.csv",
        "peaks_replicate.csv",
        "peaks_concentration.csv",
        "resolved_manifest.csv",
        "processing_report.csv",
        "source_metadata.json",
        "provenance_files.csv",
        "run.json",
    }
    assert expected.issubset({path.name for path in output.iterdir()})
    assert len(list((output / "processed_spectra").glob("*.csv"))) == 4
    assert run["counts"]["scan_spectra"] == 4
    assert verify_run(output / "run.json")["valid"] is True
    persisted_run_text = (output / "run.json").read_text(encoding="utf-8")
    assert str(tmp_path) not in persisted_run_text
    assert "runtime_output_root" not in persisted_run_text

    second_output = tmp_path / "out_second"
    second_run = process_job(config, output_root=second_output)
    assert second_run["run_id"] == run["run_id"]
    for filename in expected.difference({"run.json", "provenance_files.csv"}):
        assert (output / filename).read_bytes() == (second_output / filename).read_bytes()


def test_blank_is_never_borrowed_across_record_groups(tmp_path: Path) -> None:
    pytest.importorskip("pybaselines")
    config = _make_job(tmp_path, unmatched_group=True)
    with pytest.raises(ProcessingError, match="No manifest-declared blank"):
        process_job(config)


def test_verify_detects_output_tampering(tmp_path: Path) -> None:
    pytest.importorskip("pybaselines")
    config = _make_job(tmp_path)
    process_job(config)
    target = tmp_path / "out" / "spectra_scan.csv"
    target.write_text(target.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
    with pytest.raises(VerificationError, match="spectra_scan.csv"):
        verify_run(tmp_path / "out" / "run.json", verify_inputs=False)
