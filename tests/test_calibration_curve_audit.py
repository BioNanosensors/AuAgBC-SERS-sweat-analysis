from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "audit_calibration_curve.py"
SPEC = importlib.util.spec_from_file_location("audit_calibration_curve", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUDIT
SPEC.loader.exec_module(AUDIT)


def _csv(relative: str) -> pd.DataFrame:
    return pd.read_csv(PROJECT_ROOT / relative)


def test_committed_calibration_summary_has_conservative_result() -> None:
    summary = json.loads(
        (
            PROJECT_ROOT
            / "metadata"
            / "validation"
            / "calibration_audit_summary.json"
        ).read_text(encoding="utf-8")
    )

    assert summary["result"] == (
        "historical_computation_replayed_quantitative_claims_not_validated"
    )
    assert summary["counts"]["prepared_rows"] == 210
    assert summary["counts"]["sample_rows"] == 195
    assert summary["counts"]["blank_rows"] == 15
    assert summary["counts"]["unique_source_scans"] == 204
    assert summary["counts"]["reused_prepared_rows"] == 12
    assert summary["counts"]["fully_context_uniform_concentrations"] == 8
    assert summary["replay"]["scan_channels_passing"] == 210
    assert summary["replay"]["table_checks_passing"] == 6
    assert summary["model_audit"]["paper_parameter_rows_not_reproduced"] == 3
    assert "no context-matched low-power" in summary["model_audit"]["blank_status"]


def test_scan_lineage_records_setting_conflicts_and_exact_reuse() -> None:
    lineage = _csv("metadata/provenance/calibration_scan_lineage.csv")

    assert len(lineage) == 210
    assert lineage["prepared_file"].nunique() == 210
    assert lineage["source_scan_id"].nunique() == 204
    assert lineage["prepared_sha256"].str.fullmatch(r"[0-9a-f]{64}").all()
    assert np.allclose(lineage["intensity_max_abs_difference"], 0.0)
    assert int(lineage["axis_match_1e-5"].astype(bool).sum()) == 165
    assert int((~lineage["axis_match_1e-5"].astype(bool)).sum()) == 45
    assert np.isclose(lineage["axis_max_abs_difference"].max(), 1.2621629626)

    samples = lineage[lineage["sample_type"].eq("sample")]
    blanks = lineage[lineage["sample_type"].eq("blank")]
    context_match = (
        samples["date_matches_expected"].astype(bool)
        & samples["setting_matches_expected"].astype(bool)
    )
    assert len(samples) == 195
    assert len(blanks) == 15
    assert int((~context_match).sum()) == 44
    assert int((~samples["axis_match_1e-5"].astype(bool)).sum()) == 35
    assert int((~blanks["axis_match_1e-5"].astype(bool)).sum()) == 10
    assert blanks["source_setting"].eq("750_5_5_H").all()
    assert not blanks["date_matches_expected"].astype(bool).any()
    assert lineage["source_setting"].value_counts().to_dict() == {
        "750_5_5_L": 156,
        "750_5_5_H": 35,
        "750_5_5_M": 14,
        "500_5_5_L": 5,
    }
    assert int(lineage["source_scan_is_reused"].astype(bool).sum()) == 12

    reuse = _csv("metadata/provenance/calibration_source_reuse.csv")
    assert len(reuse) == 12
    assert reuse["source_scan_id"].nunique() == 6
    assert set(reuse["statistical_independence_status"]) == {
        "not_independent_exact_source_scan_reused"
    }
    ten_micromolar = reuse[reuse["concentration_label"].eq("10uM")]
    assert len(ten_micromolar) == 10
    assert set(ten_micromolar["prepared_replicate"]) == {2, 3}


def test_replay_and_aggregate_tables_pass_declared_bounds() -> None:
    replay = _csv("metadata/validation/calibration_replay_metrics.csv")
    tables = _csv("metadata/validation/calibration_table_replay_metrics.csv")
    locks = _csv(
        "metadata/processing_locks/"
        "calibration_curve_historical_replay_fft_cutoffs.csv"
    )

    assert len(replay) == 210
    assert replay["publication_column"].nunique() == 210
    assert replay["passes_cross_environment_tolerance"].astype(bool).all()
    assert replay["max_abs_difference"].max() <= 2.0e-4
    assert replay["points"].eq(416).all()

    assert len(tables) == 6
    assert tables["passes"].astype(bool).all()
    assert set(tables["dataset"]) == {
        "replicate_mean_sd_by_shift.csv",
        "final_spectra_by_accumulation_wide.csv",
        "summary_by_concentration.csv",
        "calibration_at_selected_shifts.csv:axis",
        "calibration_at_selected_shifts.csv:intensity_and_sd",
        "calibration_at_selected_shifts.csv:cv",
    }

    assert len(locks) == 210
    assert locks["prepared_sha256"].str.fullmatch(r"[0-9a-f]{64}").all()
    assert locks["spectrum_points_after_alignment"].eq(416).all()
    assert locks["percentile"].eq(60.0).all()
    assert locks["butterworth_order"].eq(2).all()


def test_replay_configuration_binds_the_forensic_generator_and_model() -> None:
    config = json.loads(
        (
            PROJECT_ROOT
            / "configs"
            / "reanalysis"
            / "calibration_curve_historical_replay.json"
        ).read_text(encoding="utf-8")
    )

    generator = config["historical_generator"]
    assert generator["archive_relative_path"].endswith(
        "raman_sers_pipeline_merged_spyder_UPDATED2.py"
    )
    assert generator["sha256"] == (
        "ec6583400df1615d808f07299d6e2e1f8eeb4ae7f7340f796da2c45610443892"
    )
    assert generator["repository_status"] == "superseded_not_distributed"

    models = config["recovered_historical_models"]
    assert models["exponential"]["equation"] == (
        "Y = Y0 * exp(k * log10(C_M))"
    )
    assert models["historical_thresholds"] == {
        "LOD": "3 * blank_sigma",
        "LOQ": "10 * blank_sigma",
        "warning": (
            "The recovered script omits blank mean; the manuscript describes "
            "blank mean plus 3 or 10 SD. Samples undergo blank subtraction "
            "before the final baseline, while blank threshold spectra do not, "
            "so the inversion is diagnostic rather than an analytical LOD/LOQ."
        ),
    }


def test_model_sensitivity_never_presents_a_valid_lod_or_loq() -> None:
    sensitivity = _csv(
        "metadata/validation/calibration_model_sensitivity.csv"
    )

    assert len(sensitivity) == 24
    assert set(sensitivity["peak_cm-1"]) == {392.32, 1078.5, 1589.62}
    assert set(sensitivity["fit_method"]) == {
        "deterministic_multistart_nonlinear_least_squares"
    }
    assert sensitivity["fit_status"].eq("numerically_converged").all()
    assert sensitivity["fit_interpretation_scope"].eq(
        "numerical_diagnostic_only_not_experimental_uncertainty_"
        "or_scientific_validity"
    ).all()
    assert sensitivity["lod_loq_reporting_status"].eq(
        "not_reportable_missing_context_matched_low_power_blank"
    ).all()
    assert sensitivity["scientific_interpretation"].str.contains(
        "computational sensitivity only", regex=False
    ).all()

    historical = sensitivity[
        sensitivity["record_selection_scenario"].eq("all_prepared_records")
        & sensitivity["blank_strategy"].eq(
            "historical_mixed_15_blank_scans"
        )
    ]
    assert len(historical) == 3
    assert historical["n_scan_records"].eq(195).all()
    assert historical["n_nominal_prepared_replicate_groups"].eq(39).all()
    assert historical["n_concentrations"].eq(13).all()

    avoided = sensitivity[
        sensitivity["historical_initializer_solution_status"].eq(
            "poorer_local_solution_avoided"
        )
    ]
    assert len(avoided) == 1
    assert avoided.iloc[0]["record_selection_scenario"] == (
        "context_consistent_complete_replicates"
    )
    assert np.isclose(float(avoided.iloc[0]["peak_cm-1"]), 1078.5)
    assert float(avoided.iloc[0]["historical_initializer_rss_ratio_to_best"]) > 7.0

    blank_counts = {
        strategy: set(group["n_blank_scans"].astype(int))
        for strategy, group in sensitivity.groupby("blank_strategy")
    }
    assert blank_counts == {
        "historical_mixed_15_blank_scans": {15},
        "no_blank_subtraction_counterfactual": {0},
        "wrong_context_blank_source_rep1_only": {5},
        "wrong_context_blank_source_rep2_only": {5},
        "wrong_context_blank_source_rep3_only": {5},
    }
    no_blank = sensitivity[
        sensitivity["blank_strategy"].eq(
            "no_blank_subtraction_counterfactual"
        )
    ]
    assert no_blank[
        [
            "blank_peak_mean",
            "blank_peak_sd",
            "LOD_mean_plus_3sd_M",
            "LOQ_mean_plus_10sd_M",
            "LOD_legacy_3sd_only_M",
            "LOQ_legacy_10sd_only_M",
        ]
    ].isna().all().all()


def test_all_paper_parameters_are_explicitly_not_reproduced() -> None:
    parameters = _csv(
        "metadata/validation/calibration_parameter_comparison.csv"
    )
    claims = _csv("metadata/validation/calibration_claim_assessment.csv")

    assert len(parameters) == 3
    assert parameters["parameter_reproduction_status"].eq(
        "not_reproduced_from_supplied_calibration_summary"
    ).all()
    assert set(parameters["paper_shift_cm-1"]) == {392.0, 1078.0, 1590.0}
    assert not np.allclose(parameters["paper_Y0"], parameters["replayed_Y0"])
    assert not np.allclose(parameters["paper_k"], parameters["replayed_k"])
    assert not np.allclose(parameters["paper_R2"], parameters["replayed_R2"])
    assert parameters["lod_loq_reporting_status"].eq(
        "not_reportable_missing_context_matched_low_power_blank"
    ).all()
    assert parameters["diagnostic_blank_strategy"].eq(
        "historical_mixed_15_blank_scans"
    ).all()
    assert parameters["diagnostic_blank_scan_count"].eq(15).all()
    assert "replayed_LOD_mean_plus_3sd_M" not in parameters.columns
    assert "replayed_LOQ_mean_plus_10sd_M" not in parameters.columns

    by_id = claims.set_index("claim_id")["classification"].to_dict()
    assert by_id == {
        "figure_3_4a_computational_lineage": (
            "supportable_as_computational_lineage"
        ),
        "uniform_750_5_5_l_calibration": "contradicted_by_scan_lineage",
        "prepared_axes_match_master_sources": "contradicted_by_axis_lineage",
        "independent_three_replicates": "contradicted_by_exact_source_reuse",
        "low_power_auagbc_blank": "unsupported_blank_missing",
        "paper_calibration_parameters": "not_reproduced",
        "quantitative_blind_predictions": "requires_reanalysis",
        "qualitative_4atp_band_evidence": (
            "supportable_with_acquisition_qualification"
        ),
    }


def test_multistart_fit_avoids_known_historical_initializer_trap() -> None:
    concentration = pd.DataFrame(
        {
            "concentration_M": [
                1e-15,
                1e-14,
                1e-13,
                1e-12,
                1e-11,
                1e-10,
                1e-9,
                1e-8,
                1e-7,
                1e-5,
                1e-3,
            ],
            "intensity_mean": [
                1878.912531,
                2732.173119,
                1091.788759,
                2179.366076,
                4949.447022,
                793.984022,
                930.761201,
                3850.040911,
                3179.000749,
                13623.691932,
                33660.954547,
            ],
        }
    )

    result = AUDIT._fit_exponential(concentration)

    assert result["historical_initializer_solution_status"] == (
        "poorer_local_solution_avoided"
    )
    assert 0.4 < result["k"] < 0.55
    assert 0.9 < result["R2"] < 1.0
    assert result["historical_initializer_rss_ratio_to_best"] > 7.0


def test_committed_fft_cutoff_remains_authoritative_if_peak_is_not_rediscovered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    x = np.linspace(350.0, 1800.0, 416)
    y = 100.0 + np.sin(np.linspace(0.0, 18.0, 416))
    locked_index = 10
    locked_cutoff = locked_index / (len(x) // 2 - 1)
    monkeypatch.setattr(
        AUDIT,
        "find_peaks",
        lambda _values: (np.asarray([], dtype=int), {}),
    )

    _processed, index, cutoff, points, current_peak = AUDIT._preprocess_one(
        x,
        y,
        locked_fft_index=locked_index,
        locked_normalized_cutoff=locked_cutoff,
    )

    assert index == locked_index
    assert cutoff == locked_cutoff
    assert points == len(x)
    assert current_peak is False


def test_fft_lock_rejects_inconsistent_index_and_cutoff() -> None:
    x = np.linspace(350.0, 1800.0, 416)
    y = 100.0 + np.sin(np.linspace(0.0, 18.0, 416))

    with pytest.raises(AUDIT.CalibrationAuditError, match="inconsistent"):
        AUDIT._preprocess_one(
            x,
            y,
            locked_fft_index=10,
            locked_normalized_cutoff=0.5,
        )


def test_documentation_keeps_computation_and_validation_separate() -> None:
    audit = (PROJECT_ROOT / "docs" / "CALIBRATION_CURVE_AUDIT.md").read_text(
        encoding="utf-8"
    )
    checklist = (PROJECT_ROOT / "docs" / "RELEASE_CHECKLIST.md").read_text(
        encoding="utf-8"
    )

    assert "does **not** validate the calibration" in audit
    assert "not reportable" in audit
    assert "No historical spectrum or paper-facing table was overwritten" in audit
    assert "explicitly withdraw" in checklist
