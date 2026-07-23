from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from auagbc_sers.errors import ConfigurationError
from auagbc_sers.models import Spectrum
from auagbc_sers.processing import fft_butterworth, legacy_lambda_from_filename, preprocess_signal, savgol
from auagbc_sers.profiles import get_profile


def _spectrum(x: np.ndarray, y: np.ndarray, filename: str = "4ATP_1nM_rep1_acc1.csv") -> Spectrum:
    return Spectrum(
        x=x,
        y=y,
        source_path=Path(filename),
        source_column="Intensity",
        source_column_index=1,
        source_sha256="0" * 64,
        manifest_metadata={"sample_type": "sample", "instrument": "portable"},
        record_id="synthetic",
    )


def test_legacy_lambda_rule_sets_are_explicit() -> None:
    assert legacy_lambda_from_filename("blank_rep1.csv", rule_set="portable_v2") == 8000.0
    assert legacy_lambda_from_filename("Al_4-ATP.csv", rule_set="historical_merged") == 500.0
    assert legacy_lambda_from_filename("BC_4-ATP.csv", rule_set="historical_merged") == 1000.0
    assert legacy_lambda_from_filename("AAB_AS.csv", rule_set="historical_merged", portable_hint=True) == 700.0
    assert legacy_lambda_from_filename("AAB_HS.csv", rule_set="historical_merged", portable_hint=False) == 5000.0


def test_fft_guard_returns_short_signal_unchanged() -> None:
    x = np.arange(8, dtype=float)
    y = np.arange(8, dtype=float) ** 2
    result, report, warnings = fft_butterworth(x, y, percentile=10, order=3)
    np.testing.assert_array_equal(result, y)
    assert report["applied"] is False
    assert warnings


def test_fft_peak_index_override_is_explicit_and_reproducible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scipy_fft = pytest.importorskip("scipy.fft")
    scipy_signal = pytest.importorskip("scipy.signal")
    x = np.linspace(350.0, 1800.0, 129)
    y = np.sin(np.linspace(0.0, 40.0, 129)) + 0.2 * np.sin(
        np.linspace(0.0, 180.0, 129)
    )

    def fail_if_fft_runs(*args: object, **kwargs: object) -> np.ndarray:
        raise AssertionError("Explicit cutoff locks must bypass FFT peak selection")

    monkeypatch.setattr(
        "auagbc_sers.processing._scipy_fft",
        lambda: (fail_if_fft_runs, scipy_fft.fftfreq),
    )
    generated, report, _ = fft_butterworth(
        x, y, percentile=10, order=3, peak_index=12
    )
    expected_cutoff = 12.0 / 63.0
    b_coef, a_coef = scipy_signal.butter(
        N=3, Wn=expected_cutoff, btype="low"
    )
    expected = scipy_signal.filtfilt(b_coef, a_coef, y)

    np.testing.assert_allclose(generated, expected, rtol=1e-12, atol=1e-12)
    assert report["fft_peak_index"] == 12
    assert report["cutoff_source"] == "manifest_filter_fft_peak_index"
    assert report["tie_break"] == "explicit_peak_index"


@pytest.mark.parametrize("peak_index", [0, 63, 1.5, float("nan")])
def test_fft_peak_index_override_rejects_invalid_values(peak_index: float) -> None:
    x = np.linspace(350.0, 1800.0, 129)
    y = np.sin(np.linspace(0.0, 40.0, 129))

    with pytest.raises(ConfigurationError, match="peak-index override"):
        fft_butterworth(x, y, percentile=10, order=3, peak_index=peak_index)


def test_fft_near_tie_uses_lowest_frequency_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scipy_fft = pytest.importorskip("scipy.fft")
    scipy_signal = pytest.importorskip("scipy.signal")
    x = np.linspace(350.0, 1800.0, 32)
    y = np.linspace(0.0, 1.0, 32)
    synthetic_magnitude = np.zeros(16, dtype=float)

    monkeypatch.setattr(
        "auagbc_sers.processing._scipy_fft",
        lambda: (
            lambda values, n: synthetic_magnitude.astype(complex),
            scipy_fft.fftfreq,
        ),
    )
    monkeypatch.setattr(
        scipy_signal,
        "find_peaks",
        lambda values: (np.asarray([3, 11], dtype=int), {}),
    )

    for upper in (
        4.0,
        np.nextafter(4.0, np.inf),
        np.nextafter(4.0, -np.inf),
    ):
        synthetic_magnitude[3] = upper
        synthetic_magnitude[11] = 2.0
        _, report, _ = fft_butterworth(x, y, percentile=50, order=2)

        assert report["fft_peak_index"] == 3
        assert report["fft_tie_candidate_count"] == 2
        assert report["tie_break"] == "lowest_frequency"


@pytest.mark.filterwarnings(
    "ignore:almost all baseline points are below the data:pybaselines.utils.ParameterWarning"
)
def test_preprocess_signal_consumes_manifest_fft_lock() -> None:
    x = np.linspace(350.0, 1800.0, 129)
    y = (
        1200
        + 0.2 * x
        + 150 * np.exp(-0.5 * ((x - 1078.5) / 10) ** 2)
        + 3 * np.sin(x / 9)
    )
    spectrum = _spectrum(x, y)
    spectrum.manifest_metadata["filter_fft_peak_index"] = "12"

    _, resolved, _ = preprocess_signal(
        spectrum, get_profile("legacy_individual"), is_blank=False
    )

    assert resolved["filter"]["fft_peak_index"] == 12
    assert (
        resolved["filter"]["cutoff_source"]
        == "manifest_filter_fft_peak_index"
    )


def test_savgol_safely_reduces_window() -> None:
    y = np.linspace(0, 1, 11) ** 2
    result, report, warnings = savgol(y, {"window": 25, "polyorder": 2})
    assert result.shape == y.shape
    assert report["window"] == 11
    assert warnings


def test_legacy_individual_matches_v2_numerical_chain() -> None:
    pybl = pytest.importorskip("pybaselines")
    scipy_fft = pytest.importorskip("scipy.fft")
    scipy_signal = pytest.importorskip("scipy.signal")
    x = np.linspace(350.0, 1800.0, 257)
    y = 1200 + 0.2 * x + 150 * np.exp(-0.5 * ((x - 1078.5) / 10) ** 2) + 3 * np.sin(x / 9)
    profile = get_profile("legacy_individual")
    generated, resolved, _ = preprocess_signal(_spectrum(x, y), profile, is_blank=False)

    baseline1, _ = pybl.whittaker.iarpls(y, lam=3000.0, diff_order=2, max_iter=50, tol=0.001)
    corrected = y - baseline1
    fft_values = scipy_fft.fft(corrected, len(corrected))
    frequencies = np.abs(scipy_fft.fftfreq(len(corrected), d=abs(float(np.median(np.diff(x)))) * 1e-2)[: len(y) // 2])
    magnitude = np.abs(fft_values[: len(y) // 2])
    peaks, _ = scipy_signal.find_peaks(magnitude)
    threshold = np.percentile(magnitude[peaks], 10.0)
    peak_index = int(peaks[int(np.argmin(np.abs(magnitude[peaks] - threshold)))])
    cutoff = float(np.clip(frequencies[peak_index] / np.max(frequencies), 1e-4, 0.999))
    b_coef, a_coef = scipy_signal.butter(N=3, Wn=cutoff, btype="low")
    filtered = scipy_signal.filtfilt(b_coef, a_coef, corrected)
    baseline2, _ = pybl.whittaker.iarpls(filtered, lam=80.0, diff_order=2, max_iter=50, tol=0.001)
    expected = filtered - baseline2

    np.testing.assert_allclose(generated, expected, rtol=1e-12, atol=1e-12)
    assert resolved["first_baseline"]["lambda_source"] == "legacy_filename_rule"
