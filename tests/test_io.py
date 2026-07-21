from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from auagbc_sers.errors import ImportFormatError
from auagbc_sers.io import inspect_spectrum_file, read_spectrum_file


def test_simple_wide_csv_expands_every_intensity_column(tmp_path: Path) -> None:
    path = tmp_path / "wide.csv"
    path.write_text(
        "Raman shift,scan A,scan B\n"
        + "\n".join(f"{100 + index},{index + 1},{2 * index + 3}" for index in range(12))
        + "\n",
        encoding="utf-8",
    )
    spectra = read_spectrum_file(path)
    assert [spectrum.source_column for spectrum in spectra] == ["scan A", "scan B"]
    assert all(len(spectrum.x) == 12 for spectrum in spectra)
    np.testing.assert_allclose(spectra[1].y[:3], [3.0, 5.0, 7.0])
    assert spectra[0].import_metadata["format"] == "simple_csv"


def test_portable_vendor_preamble_is_detected_and_preserved(tmp_path: Path) -> None:
    path = tmp_path / "portable.csv"
    preamble = [
        "Instrument,Portable Raman X",
        "Laser wavelength,785 nm",
        "Integration time,5 s",
        "Accumulations,3",
        "Operator,Example",
    ]
    data = ["#Wave,#Intensity1,#Intensity2"]
    data.extend(f"{500 + index * 2},{100 + index},{200 + index}" for index in range(20))
    path.write_text("\n".join(preamble + data) + "\n", encoding="utf-8")

    report = inspect_spectrum_file(path)
    assert report["format"] == "portable_vendor_csv"
    assert report["data_start_line"] == 7
    assert [column["name"] for column in report["intensity_columns"]] == ["Intensity1", "Intensity2"]
    assert report["vendor_metadata"]["Instrument"] == ["Portable Raman X"]
    assert report["vendor_metadata"]["Integration time"] == ["5 s"]


def test_intensity_selector_and_actionable_error(tmp_path: Path) -> None:
    path = tmp_path / "select.csv"
    path.write_text(
        "x,one,two\n" + "\n".join(f"{index},{index + 1},{index + 2}" for index in range(10)) + "\n",
        encoding="utf-8",
    )
    selected = read_spectrum_file(path, intensity_column="two")
    assert len(selected) == 1
    assert selected[0].source_column == "two"
    with pytest.raises(ImportFormatError, match="Available"):
        read_spectrum_file(path, intensity_column="missing")


def test_non_spectrum_csv_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "manifest.csv"
    path.write_text("file,sample_type\na.csv,sample\n", encoding="utf-8")
    with pytest.raises(ImportFormatError, match="numerical rows"):
        read_spectrum_file(path)


def test_labeled_summary_columns_are_not_misrepresented_as_intensity(tmp_path: Path) -> None:
    path = tmp_path / "summary_like.csv"
    path.write_text(
        "shift,Intensity A,Standard Deviation A,Intensity B,CV B\n"
        + "\n".join(f"{index},{index + 1},0.1,{index + 2},3.0" for index in range(10))
        + "\n",
        encoding="utf-8",
    )
    assert [item.source_column for item in read_spectrum_file(path)] == ["Intensity A", "Intensity B"]
