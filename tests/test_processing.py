from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

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
