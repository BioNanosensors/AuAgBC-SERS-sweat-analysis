from __future__ import annotations

from pathlib import Path

from auagbc_sers.cli import main


def test_inspect_cli_reports_wide_columns(tmp_path: Path, capsys) -> None:
    spectrum = tmp_path / "wide.csv"
    spectrum.write_text(
        "shift,a,b\n" + "\n".join(f"{index},{index + 1},{index + 2}" for index in range(8)) + "\n",
        encoding="utf-8",
    )
    assert main(["inspect", str(spectrum)]) == 0
    output = capsys.readouterr().out
    assert '"spectrum_files": 1' in output
    assert '"name": "a"' in output
    assert '"name": "b"' in output


def test_profiles_cli_exposes_all_required_profiles(capsys) -> None:
    assert main(["profiles"]) == 0
    output = capsys.readouterr().out
    for name in (
        "legacy_individual",
        "legacy_sg2",
        "legacy_sg3",
        "spyder_tuned",
        "reference_2026",
        "paper_2026",
        "sweat_portable_exploratory",
        "sweat_benchtop_exploratory",
    ):
        assert f'"{name}"' in output
