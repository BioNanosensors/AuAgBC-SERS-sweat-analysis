from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path


EXPECTED_FIELDS = [
    "dataset_manifest_row",
    "lineage_group_id",
    "artifact_sha256",
    "relation",
    "artifact_sample_identity",
    "master_folder_context",
    "evidence_method",
    "evidence_file",
    "confidence",
    "consent_status",
    "licence_status",
    "status",
    "role",
    "record_group",
]


def test_committed_human_data_lineage_report_is_current_and_semantic() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            str(repository_root / "scripts" / "report_human_data_lineage.py"),
            "--repository-root",
            str(repository_root),
            "--check",
        ],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    csv_path = repository_root / "metadata" / "human_data_lineage.csv"
    json_path = repository_root / "metadata" / "human_data_lineage_summary.json"
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        assert reader.fieldnames == EXPECTED_FIELDS
    summary = json.loads(json_path.read_text(encoding="utf-8"))

    assert len(rows) == 789
    assert Counter(row["relation"] for row in rows) == {
        "direct_human_sweat_raw_record": 18,
        "processed_human_sweat_candidate": 18,
        "mixed_human_sweat_publication_summary": 3,
        "exact_copy_used_as_shared_blank": 120,
        "derived_after_blank_subtraction": 630,
    }
    assert Counter(row["artifact_sample_identity"] for row in rows) == {
        "human_sweat_labelled": 18,
        "human_sweat_candidate": 18,
        "mixed_human_and_artificial_sweat_summary": 3,
        "shared_blank_identity_unresolved": 120,
        "nonhuman_experiment_derivative_with_unresolved_blank_input": 630,
    }
    assert Counter(
        (row["relation"], row["master_folder_context"]) for row in rows
    ) == {
        ("direct_human_sweat_raw_record", "not_applicable"): 18,
        ("processed_human_sweat_candidate", "not_applicable"): 18,
        ("mixed_human_sweat_publication_summary", "not_applicable"): 3,
        ("exact_copy_used_as_shared_blank", "test_hs_master_folder"): 80,
        ("exact_copy_used_as_shared_blank", "test_4atp_master_folder"): 40,
        (
            "derived_after_blank_subtraction",
            "test_hs_master_folder",
        ): 420,
        (
            "derived_after_blank_subtraction",
            "test_4atp_master_folder",
        ): 210,
    }
    assert all("unresolved_master_folder" != row["master_folder_context"] for row in rows)

    with (repository_root / "metadata" / "dataset_manifest.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        manifest_rows = {
            row_number: row
            for row_number, row in enumerate(csv.DictReader(handle), start=2)
        }
    for row in rows:
        manifest_row = manifest_rows[int(row["dataset_manifest_row"])]
        assert row["artifact_sha256"] == manifest_row["repository_sha256"]

    assert summary["schema_version"] == 2
    aliases = summary["known_label_alias_resolutions"]
    assert len(aliases) == 1
    assert aliases[0]["dataset_manifest_rows"] == [1694, 1700]
    assert aliases[0]["artifact_count"] == 2
    assert aliases[0]["type"] == (
        "byte_identical_processed_aliases_resolved_by_author_crosswalk"
    )
    assert summary["known_unresolved_label_conflicts"] == []
    alias_rows = [
        row for row in rows if int(row["dataset_manifest_row"]) in {1694, 1700}
    ]
    assert len(alias_rows) == 2
    assert len({row["lineage_group_id"] for row in alias_rows}) == 1
    assert summary["author_confirmation_statuses"] == {
        "aa_hs_session_metadata_correction": "confirmed_metadata_typo",
        "ethics_approval_document_provided": "document_reviewed_scope_clarification_pending",
        "no_written_ethics_determination": "superseded_by_ethics_approval_document",
        "publication_renumbering_confirmed": "confirmed_intended_publication_mapping",
        "pseudonymous_crosswalk_retained": "confirmed_deidentified_mapping_recorded",
        "signed_consent_forms_retained": "confirmed_retained_governance_scope_pending",
        "vp_numeric_crosswalk_confirmed": "confirmed",
        "vp_prefix_semantics": "confirmed",
    }
    assert summary["ethics_approval_record"] == {
        "record_id": "cfata_ceid_002_2026",
        "document_status": "provided_by_author_not_independently_authenticated",
        "committee_review_date": "2026-06-25",
        "letter_date": "2026-07-01",
        "decision": "approved",
        "scope_status": (
            "postdates_2024_acquisitions_retrospective_and_public_sharing_"
            "scope_unresolved"
        ),
        "document_sha256": (
            "fcf7267f9a72f923ccb698cc311359029364dcabe620702acdd0c0d324e5a1d3"
        ),
        "repository_distribution": "private_source_not_distributed_contains_signatures",
    }

    csv_text = csv_path.read_text(encoding="utf-8")
    privacy_summary = dict(summary)
    privacy_summary.pop("ethics_approval_record")
    privacy_json_text = json.dumps(privacy_summary)
    date_pattern = r"(?<!\d)20\d{2}-\d{2}-\d{2}(?!\d)"
    participant_pattern = r"(?<![A-Za-z0-9])(?:V|P)\d+(?:S\d+)?(?![A-Za-z0-9])"
    assert re.search(date_pattern, csv_text) is None
    assert re.search(date_pattern, privacy_json_text) is None
    assert re.search(participant_pattern, csv_text) is None
    assert re.search(participant_pattern, privacy_json_text) is None
    assert {
        "repository_path",
        "participant_label",
        "acquisition_date",
        "instrument_name",
        "instrument_tag",
        "master_path",
    }.isdisjoint(EXPECTED_FIELDS)
