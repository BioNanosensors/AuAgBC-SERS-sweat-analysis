from __future__ import annotations

import csv
import importlib.util
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "verify_4atp_blank_audit.py"
SPEC = importlib.util.spec_from_file_location("verify_4atp_blank_audit", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


def _copy_audit_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    provenance = root / "metadata" / "provenance"
    provenance.mkdir(parents=True)
    for filename in (
        "raw_to_master_best_matches.csv",
        "shared_blank_origin_summary.csv",
        "4atp_blank_family_assessment.csv",
    ):
        shutil.copy2(PROJECT_ROOT / "metadata" / "provenance" / filename, provenance)
    return root


def _mutate_first_row(
    path: Path,
    updates: dict[str, str],
    required_text: tuple[str, str] | None = None,
) -> None:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    row = rows[0]
    if required_text is not None:
        field, text = required_text
        row = next(candidate for candidate in rows if text in candidate[field])
    row.update(updates)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_committed_4atp_blank_audit_is_internally_consistent() -> None:
    report = VERIFY.verify_audit(PROJECT_ROOT)

    assert report["ok"] is True, "\n".join(report["errors"])
    assert report["counts"] == {
        "prepared_blank_records": 120,
        "prepared_record_groups": 8,
        "shared_source_files": 3,
        "family_assessments": 9,
        "provisional_candidates": 1,
        "confirmed_candidates": 0,
    }


def test_false_confirmation_is_rejected(tmp_path: Path) -> None:
    root = _copy_audit_fixture(tmp_path)
    assessment = (
        root / "metadata" / "provenance" / "4atp_blank_family_assessment.csv"
    )
    _mutate_first_row(assessment, {"resolution_status": "confirmed_context_match"})

    report = VERIFY.verify_audit(root)

    assert report["ok"] is False
    assert "resolution_status must be one of" in "\n".join(report["errors"])


def test_nonzero_shared_blank_difference_is_rejected(tmp_path: Path) -> None:
    root = _copy_audit_fixture(tmp_path)
    mapping = (
        root / "metadata" / "provenance" / "raw_to_master_best_matches.csv"
    )
    _mutate_first_row(
        mapping,
        {"intensity_max_abs_difference": "1.0"},
        required_text=("curated_path", "blank_rep"),
    )

    report = VERIFY.verify_audit(root)

    assert report["ok"] is False
    assert "is not an exact intensity match" in "\n".join(report["errors"])


def test_shared_source_hash_substitution_is_rejected(tmp_path: Path) -> None:
    root = _copy_audit_fixture(tmp_path)
    summary = (
        root / "metadata" / "provenance" / "shared_blank_origin_summary.csv"
    )
    _mutate_first_row(summary, {"master_file_sha256": "0" * 64})

    report = VERIFY.verify_audit(root)

    assert report["ok"] is False
    assert "master_file_sha256 differs from the audited hash" in "\n".join(
        report["errors"]
    )


def test_family_scientific_condition_substitution_is_rejected(
    tmp_path: Path,
) -> None:
    root = _copy_audit_fixture(tmp_path)
    assessment = (
        root / "metadata" / "provenance" / "4atp_blank_family_assessment.csv"
    )
    _mutate_first_row(
        assessment,
        {"required_setting": "750_5_5_L"},
        required_text=("family_id", "optimisation_750_5_5_H"),
    )

    report = VERIFY.verify_audit(root)

    assert report["ok"] is False
    assert "required_setting differs from reviewed audit value" in "\n".join(
        report["errors"]
    )
