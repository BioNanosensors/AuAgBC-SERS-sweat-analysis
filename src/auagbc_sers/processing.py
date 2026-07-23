"""Numerical processing primitives with explicit safeguards."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from typing import Any, Iterable

import numpy as np

from .errors import ConfigurationError, ProcessingError
from .models import PeakSpec, Spectrum


def _scipy_signal() -> Any:
    try:
        import scipy.signal as signal
    except ImportError as exc:  # pragma: no cover - dependency error path
        raise ProcessingError("SciPy is required for filtering. Install the dependencies from requirements.txt.") from exc
    return signal


def _scipy_fft() -> tuple[Any, Any]:
    try:
        from scipy.fft import fft, fftfreq
    except ImportError as exc:  # pragma: no cover
        raise ProcessingError("SciPy is required for FFT filtering. Install the dependencies from requirements.txt.") from exc
    return fft, fftfreq


def _whittaker() -> Any:
    try:
        from pybaselines import whittaker
    except ImportError as exc:  # pragma: no cover
        raise ProcessingError(
            "pybaselines is required for iARPLS/AsLS baseline correction. "
            "Install the dependencies from requirements.txt."
        ) from exc
    return whittaker


def _finite_float(value: Any, description: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"{description} must be numerical; received {value!r}.") from exc
    if not math.isfinite(result):
        raise ConfigurationError(f"{description} must be finite; received {value!r}.")
    return result


def _trapezoid(y: np.ndarray, x: np.ndarray) -> float:
    """Dependency-stable trapezoidal integral (works across NumPy 1.x/2.x)."""
    if len(x) < 2:
        return 0.0
    return float(np.sum(np.diff(x) * (y[:-1] + y[1:]) * 0.5))


def ensure_increasing_unique(spectrum: Spectrum) -> tuple[Spectrum, list[str]]:
    """Sort an axis and mean duplicate positions, recording every alteration."""
    order = np.argsort(spectrum.x, kind="mergesort")
    warnings: list[str] = []
    x_sorted = spectrum.x[order]
    y_sorted = spectrum.y[order]
    if not np.array_equal(order, np.arange(len(order))):
        warnings.append("Raman-shift axis was sorted into increasing order.")
    unique_x, inverse, counts = np.unique(x_sorted, return_inverse=True, return_counts=True)
    if len(unique_x) != len(x_sorted):
        sums = np.bincount(inverse, weights=y_sorted)
        y_sorted = sums / counts
        x_sorted = unique_x
        warnings.append(f"Averaged {len(spectrum.x) - len(unique_x)} duplicate Raman-shift rows.")
    return spectrum.copy_with(x=x_sorted, y=y_sorted), warnings


def crop_spectrum(spectrum: Spectrum, crop: dict[str, Any]) -> Spectrum:
    minimum = crop.get("min_cm1")
    maximum = crop.get("max_cm1")
    if minimum is not None:
        minimum = _finite_float(minimum, "crop.min_cm1")
    if maximum is not None:
        maximum = _finite_float(maximum, "crop.max_cm1")
    if minimum is not None and maximum is not None and minimum >= maximum:
        raise ConfigurationError("crop.min_cm1 must be smaller than crop.max_cm1.")
    mask = np.ones(len(spectrum.x), dtype=bool)
    if minimum is not None:
        mask &= spectrum.x >= minimum
    if maximum is not None:
        mask &= spectrum.x <= maximum
    if int(mask.sum()) < 5:
        raise ProcessingError(
            f"Cropping leaves only {int(mask.sum())} points in record {spectrum.record_id!r}; at least five are required."
        )
    return spectrum.copy_with(x=spectrum.x[mask], y=spectrum.y[mask])


def _group_key(spectrum: Spectrum, fields: list[str]) -> tuple[str, ...]:
    missing = [field for field in fields if field not in spectrum.manifest_metadata]
    if missing:
        raise ConfigurationError(
            f"Record {spectrum.record_id!r} lacks grid.group_by field(s): {', '.join(missing)}."
        )
    return tuple(str(spectrum.manifest_metadata.get(field, "")) for field in fields)


def _interpolate_grid(x_new: np.ndarray, x: np.ndarray, y: np.ndarray, method: str) -> np.ndarray:
    if method == "linear":
        return np.interp(x_new, x, y)
    if method == "nearest":
        right = np.searchsorted(x, x_new, side="left")
        right = np.clip(right, 0, len(x) - 1)
        left = np.clip(right - 1, 0, len(x) - 1)
        choose_right = np.abs(x[right] - x_new) < np.abs(x_new - x[left])
        indexes = np.where(choose_right, right, left)
        return y[indexes]
    if method == "pchip":
        try:
            from scipy.interpolate import PchipInterpolator
        except ImportError as exc:  # pragma: no cover
            raise ProcessingError("SciPy is required for PCHIP interpolation.") from exc
        return np.asarray(PchipInterpolator(x, y, extrapolate=False)(x_new), dtype=float)
    raise ConfigurationError("grid.interpolation must be 'linear', 'nearest', or 'pchip'.")


def align_spectra(spectra: list[Spectrum], grid: dict[str, Any]) -> tuple[list[Spectrum], dict[str, Any]]:
    """Align spectra by configured metadata groups on a shared overlap grid."""
    mode = str(grid.get("mode", "native")).lower()
    if mode == "native":
        return spectra, {"mode": "native", "groups": []}
    if mode not in {"intersection", "reference"}:
        raise ConfigurationError("grid.mode must be 'native', 'intersection', or 'reference'.")
    interpolation = str(grid.get("interpolation", "linear")).lower()
    if interpolation not in {"linear", "nearest", "pchip"}:
        raise ConfigurationError("grid.interpolation must be 'linear', 'nearest', or 'pchip'.")
    group_by = [str(field) for field in grid.get("group_by", [])]
    grouped: dict[tuple[str, ...], list[Spectrum]] = defaultdict(list)
    for spectrum in spectra:
        grouped[_group_key(spectrum, group_by)].append(spectrum)
    output: list[Spectrum] = []
    report_groups: list[dict[str, Any]] = []
    configured_step = grid.get("step_cm1")
    for key in sorted(grouped, key=lambda item: tuple(value.casefold() for value in item)):
        members = grouped[key]
        increasing: list[Spectrum] = []
        for member in members:
            converted, warnings = ensure_increasing_unique(member)
            if warnings:
                converted.import_metadata = dict(converted.import_metadata)
                converted.import_metadata.setdefault("alignment_warnings", []).extend(warnings)
            increasing.append(converted)
        if mode == "reference":
            reference = increasing[0]
            common_x = reference.x.copy()
            lo, hi = float(common_x[0]), float(common_x[-1])
            for member in increasing[1:]:
                if member.x[0] > lo or member.x[-1] < hi:
                    raise ProcessingError(
                        f"grid.mode='reference' would extrapolate record {member.record_id!r}. "
                        "Use grid.mode='intersection' or select a narrower reference grid."
                    )
            step_used = float(np.median(np.diff(common_x)))
        else:
            lo = max(float(member.x[0]) for member in increasing)
            hi = min(float(member.x[-1]) for member in increasing)
            if lo >= hi:
                label = dict(zip(group_by, key)) if group_by else "the configured group"
                raise ProcessingError(f"Spectra in {label} have no overlapping Raman-shift range.")
            if configured_step is None:
                steps = np.concatenate([np.diff(member.x) for member in increasing])
                steps = steps[np.isfinite(steps) & (steps > 0)]
                if not len(steps):
                    raise ProcessingError("Cannot derive an interpolation step from the Raman-shift axes.")
                step_used = float(np.median(steps))
            else:
                step_used = _finite_float(configured_step, "grid.step_cm1")
                if step_used <= 0:
                    raise ConfigurationError("grid.step_cm1 must be greater than zero.")
            points = int(math.floor((hi - lo) / step_used)) + 1
            if points < 5:
                raise ProcessingError(f"The overlap grid contains only {points} points; at least five are required.")
            # Historical merged scripts used linspace after calculating n this way.
            common_x = np.linspace(lo, hi, points)
        for member in increasing:
            output.append(
                member.copy_with(
                    x=common_x,
                    y=_interpolate_grid(common_x, member.x, member.y, interpolation),
                )
            )
        report_groups.append(
            {
                "metadata": dict(zip(group_by, key)),
                "records": len(members),
                "x_min_cm1": float(common_x[0]),
                "x_max_cm1": float(common_x[-1]),
                "points": int(len(common_x)),
                "median_step_cm1": float(step_used),
            }
        )
    by_id = {spectrum.record_id: spectrum for spectrum in output}
    return [by_id[spectrum.record_id] for spectrum in spectra], {
        "mode": mode,
        "interpolation": interpolation,
        "group_by": group_by,
        "groups": report_groups,
    }


def _acquisition_value(raw: Any, field: str) -> float:
    value = raw
    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped.startswith("{"):
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ConfigurationError(f"Manifest field {field!r} contains invalid JSON: {raw!r}.") from exc
        else:
            value = stripped
    if isinstance(value, dict):
        for candidate in ("effective_seconds", "effective_acquisition_s", "seconds", "value"):
            if candidate in value:
                value = value[candidate]
                break
        else:
            raise ConfigurationError(
                f"Acquisition mapping in {field!r} needs one of: effective_seconds, effective_acquisition_s, seconds, value."
            )
    result = _finite_float(value, f"manifest field {field!r}")
    if result <= 0:
        raise ConfigurationError(f"Manifest field {field!r} must be greater than zero when acquisition scaling is enabled.")
    return result


def scale_for_acquisition(spectrum: Spectrum, settings: dict[str, Any]) -> tuple[Spectrum, dict[str, Any]]:
    """Apply only explicitly configured acquisition scaling."""
    mode = str(settings.get("mode", "none")).lower()
    if mode == "none":
        return spectrum, {"mode": "none"}
    if mode not in {"divide", "multiply"}:
        raise ConfigurationError("effective_acquisition.mode must be 'none', 'divide', or 'multiply'.")
    field = str(settings.get("field", "acquisition"))
    if field not in spectrum.manifest_metadata or spectrum.manifest_metadata[field] in (None, ""):
        raise ConfigurationError(
            f"Record {spectrum.record_id!r} lacks manifest field {field!r}, required by acquisition scaling."
        )
    acquisition = _acquisition_value(spectrum.manifest_metadata[field], field)
    reference = _finite_float(settings.get("reference", 1.0), "effective_acquisition.reference")
    if reference <= 0:
        raise ConfigurationError("effective_acquisition.reference must be greater than zero.")
    factor = reference / acquisition if mode == "divide" else acquisition / reference
    return spectrum.copy_with(y=spectrum.y * factor), {
        "mode": mode,
        "field": field,
        "acquisition": acquisition,
        "reference": reference,
        "factor": factor,
    }


def baseline_iarpls(y: np.ndarray, settings: dict[str, Any]) -> np.ndarray:
    if len(y) < 3:
        raise ProcessingError("iARPLS needs at least three points.")
    lam = _finite_float(settings.get("lambda"), "baseline lambda")
    if lam <= 0:
        raise ConfigurationError("Baseline lambda must be greater than zero.")
    baseline, _ = _whittaker().iarpls(
        np.asarray(y, dtype=float),
        lam=lam,
        diff_order=int(settings.get("diff_order", 2)),
        max_iter=int(settings.get("max_iter", 50)),
        tol=float(settings.get("tol", 0.001)),
    )
    return np.asarray(baseline, dtype=float)


def baseline_asls(y: np.ndarray, settings: dict[str, Any]) -> np.ndarray:
    if len(y) < 3:
        raise ProcessingError("AsLS needs at least three points.")
    lam = _finite_float(settings.get("lambda"), "AsLS lambda")
    p_value = _finite_float(settings.get("p", 0.001), "AsLS p")
    if lam <= 0 or not 0 < p_value < 1:
        raise ConfigurationError("AsLS requires lambda > 0 and 0 < p < 1.")
    baseline, _ = _whittaker().asls(
        np.asarray(y, dtype=float),
        lam=lam,
        p=p_value,
        diff_order=int(settings.get("diff_order", 2)),
        max_iter=int(settings.get("max_iter", 50)),
        tol=float(settings.get("tol", 0.001)),
    )
    return np.asarray(baseline, dtype=float)


def _baseline(y: np.ndarray, settings: dict[str, Any]) -> np.ndarray:
    method = str(settings.get("method", "iarpls")).lower()
    if method == "iarpls":
        return baseline_iarpls(y, settings)
    if method == "asls":
        return baseline_asls(y, settings)
    raise ConfigurationError("Baseline method must be 'iarpls' or 'asls'.")


def legacy_lambda_from_filename(
    filename: str,
    *,
    rule_set: str = "portable_v2",
    portable_hint: bool = True,
) -> float:
    """Return a historical lambda without ever creating scientific metadata.

    ``portable_v2`` is the exact switch from
    ``RP_4_ATP_individual_processed_fixed_v2.py`` and is intentionally limited
    to that portable workflow. ``historical_merged`` exposes the broader rules
    found in later scripts.  Ambiguous data should use the manifest's explicit
    ``baseline_lambda`` instead of either filename rule.
    """
    low = filename.casefold()
    is_4atp = any(tag in low for tag in ("4atp", "4-atp", "4_atp", "4 atp"))
    if rule_set == "portable_v2":
        if "blank" in low:
            return 8000.0
        if is_4atp:
            return 3000.0
        if "aab" in low and ("as" in low or "hs" in low):
            return 700.0
        return 3000.0
    if rule_set != "historical_merged":
        raise ConfigurationError(
            "baseline.legacy_rule_set must be 'portable_v2' or 'historical_merged'."
        )
    if "al" in low and is_4atp:
        return 500.0
    if "bc" in low and "aab" not in low and (is_4atp or "blank" in low):
        return 1000.0
    if ("aab" in low and is_4atp and "go" not in low) or (
        "go" in low and ("as" in low or "hs" in low)
    ):
        return 3000.0
    if "aab" in low and "go" not in low and (("as" in low or "hs" in low) or "blank" in low):
        return 700.0 if portable_hint else 5000.0
    if "al" in low and "blank" in low:
        return 8000.0
    return 3000.0


def fft_butterworth(
    x: np.ndarray,
    y: np.ndarray,
    *,
    percentile: float,
    order: int,
    peak_index: int | None = None,
    tie_break: str = "lowest_frequency",
) -> tuple[np.ndarray, dict[str, Any], list[str]]:
    """FFT-selected low-pass filter plus explicit reproducibility controls.

    ``peak_index`` is a release-lock override.  It converts a cutoff that was
    resolved once by the historical automatic rule into an explicit parameter,
    avoiding hardware-dependent branch changes during an audited replay.
    """
    warnings: list[str] = []
    if len(y) < 10:
        warnings.append("FFT Butterworth skipped because the spectrum has fewer than 10 points.")
        return y.copy(), {"applied": False, "reason": "too_few_points"}, warnings
    percentile = _finite_float(percentile, "FFT percentile")
    if not 0 <= percentile <= 100:
        raise ConfigurationError("FFT percentile must lie between 0 and 100.")
    order = int(order)
    if order < 1:
        raise ConfigurationError("Butterworth order must be at least 1.")
    differences = np.diff(np.asarray(x, dtype=float))
    finite_steps = differences[np.isfinite(differences) & (differences != 0)]
    if not len(finite_steps):
        warnings.append("FFT Butterworth skipped because the Raman-shift spacing is degenerate.")
        return y.copy(), {"applied": False, "reason": "degenerate_axis"}, warnings
    dx = float(np.median(finite_steps))
    relative_spread = float(np.std(np.abs(finite_steps)) / max(abs(dx), np.finfo(float).eps))
    if relative_spread > 0.01:
        warnings.append(
            f"Raman-shift spacing is non-uniform (relative SD {relative_spread:.3g}); FFT used the median spacing."
        )
    fft, fftfreq = _scipy_fft()
    signal = _scipy_signal()
    n = len(y)
    frequencies = np.abs(fftfreq(n, d=abs(dx) * 1e-2)[: n // 2])
    if not np.max(frequencies) > 0:
        warnings.append("FFT Butterworth skipped because no usable FFT peaks were found.")
        return y.copy(), {"applied": False, "reason": "no_fft_peaks"}, warnings
    if peak_index is None:
        fft_signal = fft(y, n)
        magnitude = np.abs(fft_signal[: n // 2])
        peaks, _ = signal.find_peaks(magnitude)
        if not len(peaks):
            warnings.append("FFT Butterworth skipped because no usable FFT peaks were found.")
            return y.copy(), {"applied": False, "reason": "no_fft_peaks"}, warnings
        threshold = float(np.percentile(magnitude[peaks], percentile))
        distances = np.abs(magnitude[peaks] - threshold)
        closest = int(np.argmin(distances))
        tie_break = str(tie_break).strip().casefold()
        if tie_break == "legacy_argmin":
            tie_candidates = np.asarray([closest], dtype=int)
        elif tie_break == "lowest_frequency":
            # Linear percentiles can be exact midpoints between two peak
            # magnitudes.  Their computed distances may then differ by only a
            # few floating-point ulps across CPUs.  Treat those as one tie and
            # choose the lowest-frequency peak (``peaks`` is ascending).
            minimum = float(distances[closest])
            absolute_tolerance = (
                32.0
                * np.finfo(float).eps
                * max(
                    1.0,
                    abs(threshold),
                    abs(float(magnitude[peaks[closest]])),
                )
            )
            tie_candidates = np.flatnonzero(
                np.isclose(
                    distances,
                    minimum,
                    rtol=0.0,
                    atol=absolute_tolerance,
                )
            )
            closest = int(tie_candidates[0])
        else:
            raise ConfigurationError(
                "FFT tie_break must be 'lowest_frequency' or 'legacy_argmin'."
            )
        peak_index = int(peaks[closest])
        cutoff_source = "fft_percentile"
        tie_candidate_count = int(len(tie_candidates))
    else:
        numeric_peak_index = _finite_float(peak_index, "FFT peak-index override")
        if not numeric_peak_index.is_integer():
            raise ConfigurationError("FFT peak-index override must be an integer.")
        peak_index = int(numeric_peak_index)
        if peak_index < 1 or peak_index >= len(frequencies) - 1:
            raise ConfigurationError(
                f"FFT peak-index override {peak_index} is outside the usable range "
                f"1..{len(frequencies) - 2}."
            )
        cutoff_source = "manifest_filter_fft_peak_index"
        tie_candidate_count = 0
    cutoff = float(frequencies[peak_index] / np.max(frequencies))
    clipped_cutoff = float(np.clip(cutoff, 1e-4, 0.999))
    if clipped_cutoff != cutoff:
        warnings.append(f"Butterworth normalized cutoff {cutoff:.6g} was clipped to {clipped_cutoff:.6g}.")
    b_coef, a_coef = signal.butter(N=order, Wn=clipped_cutoff, btype="low")
    padlen = 3 * max(len(a_coef), len(b_coef))
    if len(y) <= padlen:
        warnings.append(
            f"FFT Butterworth skipped because {len(y)} points do not exceed filtfilt pad length {padlen}."
        )
        return y.copy(), {"applied": False, "reason": "filtfilt_padlen", "cutoff": clipped_cutoff}, warnings
    try:
        result = signal.filtfilt(b_coef, a_coef, y)
    except ValueError as exc:
        warnings.append(f"FFT Butterworth skipped safely: {exc}")
        return y.copy(), {"applied": False, "reason": "scipy_rejected_filter", "cutoff": clipped_cutoff}, warnings
    return np.asarray(result, dtype=float), {
        "applied": True,
        "percentile": percentile,
        "order": order,
        "cutoff": clipped_cutoff,
        "fft_peak_index": peak_index,
        "cutoff_source": cutoff_source,
        "tie_break": "explicit_peak_index" if cutoff_source.startswith("manifest_") else tie_break,
        "fft_tie_candidate_count": tie_candidate_count,
    }, warnings


def savgol(y: np.ndarray, settings: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any], list[str]]:
    warnings: list[str] = []
    requested = int(settings.get("window", settings.get("window_length", 9)))
    polyorder = int(settings.get("polyorder", 2))
    if requested < 3:
        raise ConfigurationError("Savitzky-Golay window must be at least 3.")
    window = requested + 1 if requested % 2 == 0 else requested
    maximum = len(y) if len(y) % 2 == 1 else len(y) - 1
    if window > maximum:
        window = maximum
        warnings.append(f"Savitzky-Golay window was reduced from {requested} to {window} for this spectrum.")
    if window < 3 or polyorder >= window or polyorder < 0:
        raise ProcessingError(
            f"Savitzky-Golay settings are invalid for {len(y)} points: window={window}, polyorder={polyorder}."
        )
    result = _scipy_signal().savgol_filter(y, window_length=window, polyorder=polyorder, mode="interp")
    return np.asarray(result, dtype=float), {"window": window, "polyorder": polyorder}, warnings


def preprocess_signal(
    spectrum: Spectrum,
    settings: dict[str, Any],
    *,
    is_blank: bool,
) -> tuple[np.ndarray, dict[str, Any], list[str]]:
    """Apply first baseline, smoothing, second baseline, and legacy SG/third pass."""
    warnings: list[str] = []
    resolved: dict[str, Any] = {}
    baseline_settings = dict(settings.get("baseline", {}))
    explicit_lambda = spectrum.manifest_metadata.get("baseline_lambda")
    if explicit_lambda not in (None, ""):
        baseline_settings["lambda"] = _finite_float(explicit_lambda, "manifest baseline_lambda")
        baseline_source = "manifest"
    elif baseline_settings.get("legacy_filename_rules", False):
        instrument = str(spectrum.manifest_metadata.get("instrument", "")).casefold()
        portable_hint = "portable" in instrument or "hand" in instrument
        baseline_settings["lambda"] = legacy_lambda_from_filename(
            spectrum.source_path.stem,
            rule_set=str(baseline_settings.get("legacy_rule_set", "portable_v2")),
            portable_hint=portable_hint,
        )
        baseline_source = "legacy_filename_rule"
    else:
        baseline_source = "profile"
    if baseline_settings.get("lambda") in (None, ""):
        raise ConfigurationError(
            f"No first-baseline lambda is available for record {spectrum.record_id!r}; set profile baseline.lambda "
            "or a manifest baseline_lambda."
        )
    y = np.asarray(spectrum.y, dtype=float)
    y = y - _baseline(y, baseline_settings)
    resolved["first_baseline"] = {**baseline_settings, "lambda_source": baseline_source}

    filter_settings = dict(settings.get("filter", {}))
    filter_method = str(filter_settings.get("method", "none")).lower()
    if filter_method == "fft_butterworth":
        percentile_key = "percentile_blank" if is_blank else "percentile_sample"
        explicit_peak_index = spectrum.manifest_metadata.get(
            "filter_fft_peak_index"
        )
        if explicit_peak_index in (None, ""):
            explicit_peak_index = None
        y, filter_resolved, filter_warnings = fft_butterworth(
            spectrum.x,
            y,
            percentile=filter_settings.get(percentile_key, filter_settings.get("percentile", 10.0)),
            order=int(filter_settings.get("order", 3)),
            peak_index=explicit_peak_index,
            tie_break=str(filter_settings.get("tie_break", "lowest_frequency")),
        )
        warnings.extend(filter_warnings)
        resolved["filter"] = {"method": filter_method, **filter_resolved}
    elif filter_method in {"savgol", "savitzky_golay"}:
        y, filter_resolved, filter_warnings = savgol(y, filter_settings)
        warnings.extend(filter_warnings)
        resolved["filter"] = {"method": "savgol", **filter_resolved}
    elif filter_method == "none":
        resolved["filter"] = {"method": "none"}
    else:
        raise ConfigurationError("filter.method must be 'fft_butterworth', 'savgol', or 'none'.")

    second = dict(settings.get("second_baseline", {}))
    if bool(second.get("enabled", False)):
        y = y - _baseline(y, second)
        resolved["second_baseline"] = second
    else:
        resolved["second_baseline"] = {"enabled": False}

    legacy_sg = settings.get("savgol_after_second_baseline")
    if legacy_sg:
        y, sg_resolved, sg_warnings = savgol(y, dict(legacy_sg))
        warnings.extend(sg_warnings)
        resolved["savgol_after_second_baseline"] = sg_resolved

    third = dict(settings.get("third_baseline", {}))
    if bool(third.get("enabled", False)):
        y = y - _baseline(y, third)
        resolved["third_baseline"] = third
    return y, resolved, warnings


def apply_post_blank_baseline(y: np.ndarray, settings: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]]:
    if not bool(settings.get("enabled", False)):
        return y.copy(), {"enabled": False}
    baseline = _baseline(y, settings)
    return y - baseline, dict(settings)


def normalize_signal(x: np.ndarray, y: np.ndarray, settings: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]]:
    method = str(settings.get("method", "none")).lower()
    if method == "none":
        return y.copy(), {"method": "none"}
    if method in {"max", "maximum"}:
        divisor = float(np.max(np.abs(y)))
        offset = 0.0
    elif method == "minmax":
        offset = float(np.min(y))
        divisor = float(np.max(y) - offset)
    elif method in {"l2", "vector"}:
        offset = 0.0
        divisor = float(np.linalg.norm(y))
    elif method == "area":
        offset = 0.0
        divisor = abs(_trapezoid(y, x))
    elif method in {"snv", "standard_normal_variate"}:
        offset = float(np.mean(y))
        divisor = float(np.std(y, ddof=1))
    else:
        raise ConfigurationError("normalization.method must be none, max, minmax, l2, area, or snv.")
    if not math.isfinite(divisor) or divisor <= np.finfo(float).eps:
        raise ProcessingError(f"Cannot apply {method} normalization because its divisor is zero or non-finite.")
    return (y - offset) / divisor, {"method": method, "offset": offset, "divisor": divisor}


def parse_peak_specs(raw_specs: Iterable[dict[str, Any]]) -> list[PeakSpec]:
    specs: list[PeakSpec] = []
    names: set[str] = set()
    for index, raw in enumerate(raw_specs, start=1):
        if not isinstance(raw, dict):
            raise ConfigurationError(f"Peak specification {index} must be a mapping.")
        center = _finite_float(raw.get("center_cm1", raw.get("cm")), f"peaks[{index}].center_cm1")
        window = _finite_float(raw.get("window_cm1", raw.get("window", 7.0)), f"peaks[{index}].window_cm1")
        method = str(raw.get("method", "height")).lower()
        if window <= 0:
            raise ConfigurationError(f"peaks[{index}].window_cm1 must be greater than zero.")
        if method not in {"height", "area", "mean"}:
            raise ConfigurationError(f"peaks[{index}].method must be height, area, or mean.")
        spec = PeakSpec(center_cm1=center, window_cm1=window, method=method, label=raw.get("label"))
        if spec.output_name in names:
            raise ConfigurationError(f"Peak output name {spec.output_name!r} is duplicated; use unique labels.")
        names.add(spec.output_name)
        specs.append(spec)
    return specs


def peak_value(x: np.ndarray, y: np.ndarray, spec: PeakSpec) -> tuple[float, float, int]:
    mask = (x >= spec.center_cm1 - spec.window_cm1) & (x <= spec.center_cm1 + spec.window_cm1)
    count = int(mask.sum())
    if not count:
        return math.nan, math.nan, 0
    x_window = x[mask]
    y_window = y[mask]
    if spec.method == "area":
        return _trapezoid(y_window, x_window), float(spec.center_cm1), count
    if spec.method == "mean":
        return float(np.mean(y_window)), float(spec.center_cm1), count
    index = int(np.argmax(y_window))
    return float(y_window[index]), float(x_window[index]), count
