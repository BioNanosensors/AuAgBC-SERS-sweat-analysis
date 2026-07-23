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
        "4atp_blank_search_summary.csv",
        "4atp_blank_unresolved_candidates.csv",
    ):
        shutil.copy2(PROJECT_ROOT / "metadata" / "provenance" / filename, provenance)
    shutil.copy2(
        PROJECT_ROOT / "metadata" / "author_confirmations.csv",
        root / "metadata" / "author_confirmations.csv",
    )
    confirmed_raw = root / VERIFY.CONFIRMED_RAW_PATH
    confirmed_raw.parent.mkdir(parents=True)
    shutil.copy2(PROJECT_ROOT / VERIFY.CONFIRMED_RAW_PATH, confirmed_raw)
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
        "collection_search_summaries": 1,
        "unresolved_contextual_candidates": 4,
        "provisional_candidates": 0,
        "confirmed_candidates": 1,
        "required_author_confirmations": 3,
        "confirmed_raw_files_verified": 1,
    }


def test_second_confirmation_is_rejected(tmp_path: Path) -> None:
    root = _copy_audit_fixture(tmp_path)
    assessment = (
        root / "metadata" / "provenance" / "4atp_blank_family_assessment.csv"
    )
    _mutate_first_row(
        assessment,
        {"resolution_status": "confirmed_context_match"},
        required_text=("family_id", "calibration_curve"),
    )

    report = VERIFY.verify_audit(root)

    assert report["ok"] is False
    assert "Exactly one family may have a confirmed context-matched blank" in "\n".join(
        report["errors"]
    )


def test_confirmation_requires_all_six_match_flags(tmp_path: Path) -> None:
    root = _copy_audit_fixture(tmp_path)
    assessment = (
        root / "metadata" / "provenance" / "4atp_blank_family_assessment.csv"
    )
    _mutate_first_row(
        assessment,
        {"material_match": "unresolved"},
        required_text=("family_id", "optimisation_750_5_5_H"),
    )

    report = VERIFY.verify_audit(root)

    assert report["ok"] is False
    assert "cannot be confirmed while material_match is 'unresolved'" in "\n".join(
        report["errors"]
    )


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


def test_required_author_confirmation_status_is_enforced(tmp_path: Path) -> None:
    root = _copy_audit_fixture(tmp_path)
    confirmations = root / "metadata" / "author_confirmations.csv"
    _mutate_first_row(
        confirmations,
        {"status": "unresolved"},
        required_text=("confirmation_id", "aabc_blank_identity_confirmed"),
    )

    report = VERIFY.verify_audit(root)

    assert report["ok"] is False
    assert "aabc_blank_identity_confirmed" in "\n".join(report["errors"])
    assert "confirmed_material_alias_and_analyte_free_blank" in "\n".join(
        report["errors"]
    )


def test_confirmed_raw_file_tampering_is_rejected(tmp_path: Path) -> None:
    root = _copy_audit_fixture(tmp_path)
    confirmed_raw = root / VERIFY.CONFIRMED_RAW_PATH
    confirmed_raw.write_bytes(confirmed_raw.read_bytes() + b"tampered\n")

    report = VERIFY.verify_audit(root)

    assert report["ok"] is False
    joined = "\n".join(report["errors"])
    assert "byte-size mismatch" in joined
    assert "SHA-256 mismatch" in joined


def test_collection_search_count_substitution_is_rejected(tmp_path: Path) -> None:
    root = _copy_audit_fixture(tmp_path)
    summary = (
        root / "metadata" / "provenance" / "4atp_blank_search_summary.csv"
    )
    _mutate_first_row(summary, {"explicit_auagbc_750_5_5_m": "1"})

    report = VERIFY.verify_audit(root)

    assert report["ok"] is False
    assert "explicit_auagbc_750_5_5_m differs from reviewed audit value" in "\n".join(
        report["errors"]
    )


def test_contextual_candidate_cannot_be_silently_promoted(tmp_path: Path) -> None:
    root = _copy_audit_fixture(tmp_path)
    candidates = (
        root
        / "metadata"
        / "provenance"
        / "4atp_blank_unresolved_candidates.csv"
    )
    _mutate_first_row(
        candidates,
        {
            "target_context_match": "true",
            "resolution_status": "confirmed_context_match",
        },
        required_text=("candidate_id", "aabc_blank_2024_09_13"),
    )

    report = VERIFY.verify_audit(root)

    assert report["ok"] is False
    joined = "\n".join(report["errors"])
    assert "target_context_match differs from reviewed audit value" in joined
    assert "cannot be promoted from contextual candidate" in joined


def test_contextual_candidate_hash_substitution_is_rejected(tmp_path: Path) -> None:
    root = _copy_audit_fixture(tmp_path)
    candidates = (
        root
        / "metadata"
        / "provenance"
        / "4atp_blank_unresolved_candidates.csv"
    )
    _mutate_first_row(
        candidates,
        {"sha256": "0" * 64},
        required_text=("candidate_id", "auagbc_blank_2024_06_06"),
    )

    report = VERIFY.verify_audit(root)

    assert report["ok"] is False
    assert "sha256 differs from reviewed audit value" in "\n".join(report["errors"])
