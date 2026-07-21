"""Named, explicit processing profiles.

The legacy profiles are retained for numerical archaeology.  New analyses should
normally use ``reference_2026`` and record any overrides in the run manifest.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .errors import ConfigurationError


_LEGACY_BASE = {
    "profile_note": (
        "Portable individual-v2 numerical chain retained for reproducibility; it is not a universal profile for all "
        "historical benchtop, substrate, or sweat scripts."
    ),
    "axis_order": "preserve",
    "grid": {"mode": "native", "step_cm1": None, "interpolation": "linear", "group_by": []},
    "crop": {"min_cm1": None, "max_cm1": None},
    "effective_acquisition": {"mode": "none", "field": "acquisition", "reference": 1.0},
    "blank": {
        "stage": "raw",
        "strategy": "mean",
        "interpolation": "linear",
        "group_by": [],
        "sample_types": ["blank"],
    },
    "baseline": {
        "method": "iarpls",
        "lambda": None,
        "legacy_filename_rules": True,
        "legacy_rule_set": "portable_v2",
        "diff_order": 2,
        "max_iter": 50,
        "tol": 0.001,
    },
    "filter": {
        "method": "fft_butterworth",
        "order": 3,
        "percentile_sample": 10.0,
        "percentile_blank": 5.0,
    },
    "second_baseline": {
        "enabled": True,
        "method": "iarpls",
        "lambda": 80.0,
        "diff_order": 2,
        "max_iter": 50,
        "tol": 0.001,
    },
    "savgol_after_second_baseline": None,
    "post_blank_baseline": {"enabled": False},
    "normalization": {"method": "none"},
    "peaks": [
        {"center_cm1": 392.32, "window_cm1": 10.0, "method": "height"},
        {"center_cm1": 1078.50, "window_cm1": 7.0, "method": "height"},
        {"center_cm1": 1589.62, "window_cm1": 8.0, "method": "height"},
    ],
}


PROFILES: dict[str, dict[str, Any]] = {
    # Exact chain in RP_4_ATP_individual_processed_fixed_v2.py:
    # raw blank subtraction -> iARPLS -> FFT-selected Butterworth -> iARPLS.
    "legacy_individual": _LEGACY_BASE,
    "legacy_sg2": {
        **deepcopy(_LEGACY_BASE),
        "savgol_after_second_baseline": {"window": 25, "polyorder": 2},
    },
    "legacy_sg3": {
        **deepcopy(_LEGACY_BASE),
        "savgol_after_second_baseline": {"window": 25, "polyorder": 3},
        "third_baseline": {
            "enabled": True,
            "method": "iarpls",
            "lambda": 80.0,
            "diff_order": 2,
            "max_iter": 50,
            "tol": 0.001,
        },
    },
    # Tuned parameters from the final Spyder workflow. Scientific identity
    # still comes solely from the manifest; the profile only controls maths.
    "spyder_tuned": {
        "axis_order": "increasing",
        "grid": {
            "mode": "intersection",
            "step_cm1": None,
            "interpolation": "linear",
            "group_by": ["record_group", "instrument"],
        },
        "crop": {"min_cm1": 341.6070517, "max_cm1": None},
        "effective_acquisition": {"mode": "none", "field": "acquisition", "reference": 1.0},
        "blank": {
            "stage": "processed",
            "strategy": "mean",
            "interpolation": "linear",
            "group_by": ["record_group", "instrument"],
            "sample_types": ["blank"],
        },
        "baseline": {
            "method": "iarpls",
            "lambda": 3000.0,
            "legacy_filename_rules": False,
            "diff_order": 2,
            "max_iter": 50,
            "tol": 0.001,
        },
        "filter": {
            "method": "fft_butterworth",
            "order": 2,
            "percentile_sample": 60.0,
            "percentile_blank": 60.0,
        },
        "second_baseline": {
            "enabled": True,
            "method": "iarpls",
            "lambda": 600.0,
            "diff_order": 2,
            "max_iter": 50,
            "tol": 0.001,
        },
        "savgol_after_second_baseline": None,
        "post_blank_baseline": {
            "enabled": True,
            "method": "asls",
            "lambda": 5_000_000.0,
            "p": 0.001,
            "diff_order": 2,
            "max_iter": 50,
            "tol": 0.001,
        },
        "normalization": {"method": "none"},
        "peaks": [
            {"center_cm1": 392.32, "window_cm1": 10.0, "method": "height"},
            {"center_cm1": 1078.50, "window_cm1": 7.0, "method": "height"},
            {"center_cm1": 1589.62, "window_cm1": 8.0, "method": "height"},
        ],
    },
}
PROFILES["spyder_tuned"]["aggregation"] = {"group_by": ["record_group"]}
for _name, _lambda in (
    ("sweat_portable_exploratory", 700.0),
    ("sweat_benchtop_exploratory", 5000.0),
):
    _exploratory = deepcopy(_LEGACY_BASE)
    _exploratory["axis_order"] = "increasing"
    _exploratory["blank"] = {
        "stage": "none",
        "strategy": "mean",
        "interpolation": "linear",
        "group_by": ["record_group", "instrument"],
        "sample_types": ["blank"],
    }
    _exploratory["baseline"]["lambda"] = _lambda
    _exploratory["baseline"]["legacy_filename_rules"] = False
    _exploratory["normalization"] = {"method": "max"}
    _exploratory["aggregation"] = {"group_by": ["record_group"]}
    _exploratory["profile_note"] = (
        "Exploratory sweat processing: per-spectrum iARPLS/FFT/iARPLS then max normalization; "
        "not an exact published-data reproduction."
    )
    PROFILES[_name] = _exploratory
PROFILES["reference_2026"] = deepcopy(PROFILES["spyder_tuned"])
PROFILES["reference_2026"]["aggregation"] = {"group_by": ["record_group"]}
# Compatibility name required by early repository drafts.  The pipeline emits a
# prominent provenance warning because the manuscript does not specify enough
# parameters to claim exact regeneration of every published processed folder.
PROFILES["paper_2026"] = deepcopy(PROFILES["reference_2026"])
PROFILES["paper_2026"]["profile_note"] = (
    "Deprecated alias of reference_2026. It must not be described as exact paper reproduction because the manuscript "
    "does not report enough processing parameters to support that claim."
)

PROFILE_NAMES = tuple(PROFILES)


def _deep_update(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_update(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def get_profile(name: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a detached profile with recursively applied user overrides."""
    if name not in PROFILES:
        choices = ", ".join(PROFILE_NAMES)
        raise ConfigurationError(f"Unknown processing profile {name!r}. Choose one of: {choices}.")
    return _deep_update(PROFILES[name], overrides or {})
