"""Small immutable-ish containers shared by import and processing code."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class Spectrum:
    """One intensity series and its Raman-shift axis."""

    x: np.ndarray
    y: np.ndarray
    source_path: Path
    source_column: str
    source_column_index: int
    source_sha256: str
    import_metadata: dict[str, Any] = field(default_factory=dict)
    manifest_metadata: dict[str, Any] = field(default_factory=dict)
    record_id: str = ""

    def copy_with(self, *, x: np.ndarray | None = None, y: np.ndarray | None = None) -> "Spectrum":
        return Spectrum(
            x=self.x.copy() if x is None else np.asarray(x, dtype=float),
            y=self.y.copy() if y is None else np.asarray(y, dtype=float),
            source_path=self.source_path,
            source_column=self.source_column,
            source_column_index=self.source_column_index,
            source_sha256=self.source_sha256,
            import_metadata=dict(self.import_metadata),
            manifest_metadata=dict(self.manifest_metadata),
            record_id=self.record_id,
        )


@dataclass(frozen=True)
class PeakSpec:
    """A peak band whose height, mean, or integrated area is exported."""

    center_cm1: float
    window_cm1: float = 7.0
    method: str = "height"
    label: str | None = None

    @property
    def output_name(self) -> str:
        base = self.label or f"{self.center_cm1:g}_{self.method}"
        return "peak_" + "".join(ch if ch.isalnum() or ch in "_.-" else "_" for ch in base)


@dataclass
class ProcessedSpectrum:
    """A spectrum after every configured processing step."""

    spectrum: Spectrum
    raw_y: np.ndarray
    scaled_y: np.ndarray
    preprocessed_y: np.ndarray
    final_y: np.ndarray
    resolved_parameters: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
