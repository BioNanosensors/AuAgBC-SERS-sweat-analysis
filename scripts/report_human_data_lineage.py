#!/usr/bin/env python3
"""Build a conservative, identifier-minimised human-data lineage inventory.

The report combines explicit sample-type labels with the existing zero-difference
raw-to-master audit. It separates shared-blank sample identity from the master
folder in which an exact match was found, correcting an older unsupported
all-human label. It never infers participant identity from spectral similarity.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path


CSV_FIELDS = (
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
)
SHARED_BLANK_NOTE = (
    "Shared blank identity is unresolved; exact intensity matches link the "
    "15-channel series to ten columns stored in Test HS master exports and five "
    "stored in a Test 4-ATP master export. Storage context is not proof of sample "
    "identity. See metadata/provenance_corrections.csv."
)
BLANK_NAME = re.compile(r"(?i)^blank_rep(?P<rep>\d+)_acc(?P<acc>\d+)\.csv$")
REP_ACC = re.compile(r"(?i)_rep(?P<rep>\d+)_acc(?P<acc>\d+)(?:_|\.)")
DATE_TOKEN = re.compile(r"(?<!\d)20\d{2}-\d{2}-\d{2}(?!\d)")
PROCESSED_HUMAN_LABEL = re.compile(r"(?i)^HS_(?P<label>V\d+S\d+)_")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def opaque_id(*parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return "lg-" + digest[:20]


def repository_path_from_curated_path(curated_path: str) -> str:
    prefix = "Raman_spectra_data/"
    relative = curated_path[len(prefix) :] if curated_path.startswith(prefix) else curated_path
    return "data/quarantine/legacy_snapshot/" + relative


def master_folder_context(master_path: str) -> str:
    if master_path.startswith("Test HS/"):
        return "test_hs_master_folder"
    if master_path.startswith("Test 4-ATP/"):
        return "test_4atp_master_folder"
    return "unresolved_master_folder"


def group_from_processed_path(path: str) -> str:
    parts = path.split("/")
    prefix = ["data", "quarantine", "legacy_snapshot"]
    if parts[:3] != prefix or len(parts) < 5:
        return ""
    if parts[3] in {"Calibration curve", "Blind samples"}:
        return parts[3]
    if parts[3] in {"Optimisation", "Stability"} and len(parts) > 4:
        return f"{parts[3]}/{parts[4]}"
    return parts[3]


def consent_status(artifact_sample_identity: str) -> str:
    if artifact_sample_identity in {
        "human_sweat_labelled",
        "human_sweat_candidate",
        "mixed_human_and_artificial_sweat_summary",
    }:
        return "public_sharing_not_evidenced"
    if artifact_sample_identity in {
        "shared_blank_identity_unresolved",
        "nonhuman_experiment_derivative_with_unresolved_blank_input",
    }:
        return "pending_sample_identity_resolution"
    return "pending_identity_resolution"


def licence_status(artifact_sample_identity: str) -> str:
    if artifact_sample_identity in {
        "human_sweat_labelled",
        "human_sweat_candidate",
        "mixed_human_and_artificial_sweat_summary",
    }:
        return "no_open_licence_pending_human_data_governance"
    return "no_open_licence_pending_sample_identity_resolution"


def build_inventory(repository_root: Path) -> tuple[list[dict[str, str]], dict[str, object]]:
    metadata = repository_root / "metadata"
    dataset_rows = read_csv(metadata / "dataset_manifest.csv")
    processing_rows = read_csv(metadata / "raw_processing_manifest.csv")
    match_rows = read_csv(metadata / "provenance" / "raw_to_master_best_matches.csv")
    label_evidence_rows = read_csv(
        metadata / "provenance" / "proof_of_concept_label_evidence.csv"
    )
    confirmation_rows = read_csv(metadata / "author_confirmations.csv")
    ethics_rows = read_csv(metadata / "ethics_approval_record.csv")
    if (
        len(ethics_rows) != 1
        or ethics_rows[0].get("record_id") != "cfata_ceid_002_2026"
    ):
        raise ValueError(
            "ethics_approval_record.csv must contain the reviewed CFATA/CEID record"
        )
    ethics_record = ethics_rows[0]
    confirmation_by_id = {
        row["confirmation_id"]: row for row in confirmation_rows
    }
    if len(confirmation_by_id) != len(confirmation_rows):
        raise ValueError("author_confirmations.csv contains duplicate confirmation IDs")
    required_confirmation_ids = {
        "signed_consent_forms_retained",
        "no_written_ethics_determination",
        "ethics_approval_document_provided",
        "vp_prefix_semantics",
        "pseudonymous_crosswalk_retained",
        "vp_numeric_crosswalk_confirmed",
        "publication_renumbering_confirmed",
        "aa_hs_session_metadata_correction",
    }
    missing_confirmation_ids = required_confirmation_ids - confirmation_by_id.keys()
    if missing_confirmation_ids:
        raise ValueError(
            "author_confirmations.csv is missing required IDs: "
            + ", ".join(sorted(missing_confirmation_ids))
        )

    dataset_by_path = {
        row["repository_path"]: (row_number, row)
        for row_number, row in enumerate(dataset_rows, start=2)
    }
    if len(dataset_by_path) != len(dataset_rows):
        raise ValueError("dataset_manifest.csv contains duplicate repository paths")
    processing_by_path = {
        row["file"]: row for row in processing_rows if row.get("file")
    }
    dated_record_groups = sorted(
        {
            row.get("record_group", "")
            for row in processing_rows
            if DATE_TOKEN.search(row.get("record_group", ""))
        }
    )
    public_record_groups = {
        record_group: f"stability_session_{index}"
        for index, record_group in enumerate(dated_record_groups, start=1)
    }
    inventory: list[dict[str, str]] = []
    seen: set[tuple[int, str]] = set()

    def add(
        path: str,
        relation: str,
        artifact_sample_identity: str,
        master_context: str,
        evidence_method: str,
        evidence_file: str,
        confidence: str,
        lineage_group_id: str,
        record_group: str = "",
    ) -> None:
        located = dataset_by_path.get(path)
        if located is None:
            raise ValueError(f"Inventory path is missing from dataset manifest: {path}")
        row_number, dataset_row = located
        key = (row_number, relation)
        if key in seen:
            return
        seen.add(key)
        raw_record_group = record_group or processing_by_path.get(path, {}).get(
            "record_group", ""
        )
        inventory.append(
            {
                "dataset_manifest_row": str(row_number),
                "lineage_group_id": lineage_group_id,
                "artifact_sha256": dataset_row.get("repository_sha256", ""),
                "relation": relation,
                "artifact_sample_identity": artifact_sample_identity,
                "master_folder_context": master_context,
                "evidence_method": evidence_method,
                "evidence_file": evidence_file,
                "confidence": confidence,
                "consent_status": consent_status(artifact_sample_identity),
                "licence_status": licence_status(artifact_sample_identity),
                "status": dataset_row.get("status", ""),
                "role": dataset_row.get("role", ""),
                "record_group": public_record_groups.get(
                    raw_record_group, raw_record_group
                ),
            }
        )

    # Direct human-sweat raw-like records explicitly labelled in the processing manifest.
    for path, processing_row in processing_by_path.items():
        if processing_row.get("sample_type") != "human_sweat":
            continue
        located = dataset_by_path.get(path)
        if located is None:
            raise ValueError(f"Direct human-data path is missing from dataset manifest: {path}")
        _, dataset_row = located
        add(
            path,
            "direct_human_sweat_raw_record",
            "human_sweat_labelled",
            "not_applicable",
            "raw_processing_manifest sample_type=human_sweat",
            "metadata/raw_processing_manifest.csv",
            "medium_with_author_confirmed_code_mapping",
            opaque_id("direct-human", dataset_row.get("repository_sha256", "")),
            processing_row.get("record_group", ""),
        )

    # Processed proof-of-concept human-sweat candidates and mixed paper summaries.
    processed_candidate_labels: dict[str, set[str]] = {}
    processed_candidate_rows: dict[str, list[int]] = {}
    for path, (row_number, dataset_row) in dataset_by_path.items():
        if (
            path.startswith(
                "data/quarantine/legacy_snapshot/Proof of concept/"
            )
            and "/Processed spectra/" in path
            and not Path(path).name.startswith("AAB_AS")
        ):
            add(
                path,
                "processed_human_sweat_candidate",
                "human_sweat_candidate",
                "not_applicable",
                "proof-of-concept processed-folder scope and human-sweat filename convention",
                "metadata/dataset_manifest.csv",
                "medium_due_to_unresolved_processing_provenance_with_author_confirmed_code_mapping",
                opaque_id("processed-human", dataset_row.get("repository_sha256", "")),
                "proof_of_concept",
            )
            artifact_sha256 = dataset_row.get("repository_sha256", "")
            label_match = PROCESSED_HUMAN_LABEL.match(Path(path).name)
            if label_match:
                processed_candidate_labels.setdefault(artifact_sha256, set()).add(
                    label_match.group("label").upper()
                )
                processed_candidate_rows.setdefault(artifact_sha256, []).append(
                    row_number
                )
        elif path.startswith("data/published_snapshot/proof_of_concept/"):
            add(
                path,
                "mixed_human_sweat_publication_summary",
                "mixed_human_and_artificial_sweat_summary",
                "not_applicable",
                "paper-data map and publication-snapshot scope",
                "docs/PAPER_DATA_MAP.md",
                "high_for_content_scope_only",
                opaque_id("poc-summary", dataset_row.get("repository_sha256", "")),
                "proof_of_concept",
            )

    # Exact blank copies. The master path is used only to classify context and is
    # replaced by an opaque group identifier in the public output.
    blank_links: dict[tuple[str, str, str], dict[str, str]] = {}
    for match_row in match_rows:
        curated_path = match_row.get("curated_path", "")
        name_match = BLANK_NAME.match(Path(curated_path).name)
        if name_match is None:
            continue
        if float(match_row.get("intensity_max_abs_difference") or "inf") != 0.0:
            continue
        context = master_folder_context(match_row.get("master_path", ""))
        lineage_id = opaque_id(
            "master-column",
            match_row.get("master_source", ""),
            match_row.get("master_path", ""),
            match_row.get("master_column_index", ""),
        )
        path = repository_path_from_curated_path(curated_path)
        processing_row = processing_by_path.get(path, {})
        record_group = processing_row.get("record_group", "")
        add(
            path,
            "exact_copy_used_as_shared_blank",
            "shared_blank_identity_unresolved",
            context,
            "zero-difference intensity match to an independently inventoried master column",
            "metadata/provenance/raw_to_master_best_matches.csv",
            "high_for_numerical_origin_not_sample_identity",
            lineage_id,
            record_group,
        )
        blank_links[
            (
                match_row.get("curated_group", ""),
                name_match.group("rep"),
                name_match.group("acc"),
            )
        ] = {
            "master_folder_context": context,
            "lineage_group_id": lineage_id,
            "record_group": public_record_groups.get(record_group, record_group),
        }

    # The historical manifest note covers Calibration and Optimisation derivatives.
    # It is overbroad, so use replicate/accumulation-specific exact-match evidence
    # to distinguish Test HS and Test 4-ATP master-folder contexts without
    # treating folder context as sample identity.
    for path, (_, dataset_row) in dataset_by_path.items():
        if (
            dataset_row.get("role") != "processed_spectrum"
            or dataset_row.get("note") != SHARED_BLANK_NOTE
        ):
            continue
        name_match = REP_ACC.search("_" + Path(path).name)
        group = group_from_processed_path(path)
        link = (
            blank_links.get((group, name_match.group("rep"), name_match.group("acc")))
            if name_match
            else None
        )
        if link:
            context = link["master_folder_context"]
            lineage_id = link["lineage_group_id"]
            record_group = link["record_group"]
            confidence = "medium_derivative_link_inferred_from_historical_workflow"
        else:
            context = "unresolved_master_folder"
            lineage_id = opaque_id("unresolved-derivative", path)
            record_group = ""
            confidence = "low_unresolved_blank_link"
        add(
            path,
            "derived_after_blank_subtraction",
            "nonhuman_experiment_derivative_with_unresolved_blank_input",
            context,
            "replicate/accumulation link to the exact-match blank audit",
            "metadata/provenance/raw_to_master_best_matches.csv",
            confidence,
            lineage_id,
            record_group,
        )

    inventory.sort(
        key=lambda item: (
            int(item["dataset_manifest_row"]),
            item["relation"],
            item["lineage_group_id"],
        )
    )
    relation_counts = Counter(row["relation"] for row in inventory)
    identity_counts = Counter(row["artifact_sample_identity"] for row in inventory)
    context_counts = Counter(row["master_folder_context"] for row in inventory)
    resolved_alias_rows_by_sha: dict[str, set[int]] = {}
    for evidence_row in label_evidence_rows:
        if evidence_row.get("resolution_status") != (
            "resolved_dual_label_namespace_duplicate"
        ):
            continue
        artifact_sha256 = evidence_row.get("artifact_sha256", "")
        try:
            manifest_row = int(evidence_row.get("dataset_manifest_row", ""))
        except ValueError as error:
            raise ValueError(
                "Invalid manifest row in proof-of-concept label evidence"
            ) from error
        resolved_alias_rows_by_sha.setdefault(artifact_sha256, set()).add(
            manifest_row
        )

    known_label_alias_resolutions: list[dict[str, object]] = []
    known_unresolved_label_conflicts: list[dict[str, object]] = []
    for artifact_sha256, labels in sorted(processed_candidate_labels.items()):
        if len(labels) <= 1:
            continue
        manifest_rows = sorted(processed_candidate_rows[artifact_sha256])
        common = {
            "artifact_sha256": artifact_sha256,
            "dataset_manifest_rows": manifest_rows,
            "artifact_count": len(manifest_rows),
        }
        if resolved_alias_rows_by_sha.get(artifact_sha256) == set(manifest_rows):
            known_label_alias_resolutions.append(
                {
                    "type": "byte_identical_processed_aliases_resolved_by_author_crosswalk",
                    **common,
                    "evidence_file": (
                        "metadata/provenance/proof_of_concept_label_evidence.csv"
                    ),
                    "interpretation": (
                        "The byte-identical files use acquisition- and "
                        "publication-namespace aliases for the same confirmed "
                        "deidentified acquisition record; no participant identity "
                        "is disclosed."
                    ),
                }
            )
        else:
            known_unresolved_label_conflicts.append(
                {
                    "type": "byte_identical_processed_files_with_unresolved_labels",
                    **common,
                    "evidence_file": (
                        "metadata/provenance/duplicate_content_groups.csv"
                    ),
                    "interpretation": (
                        "The files are byte-identical but their label relationship "
                        "has not been resolved by the author-confirmed crosswalk."
                    ),
                }
            )
    summary: dict[str, object] = {
        "schema_version": 2,
        "scope": "identifier-minimised lower-bound human-data and unresolved shared-blank lineage inventory",
        "row_count": len(inventory),
        "relation_counts": dict(sorted(relation_counts.items())),
        "artifact_sample_identity_counts": dict(sorted(identity_counts.items())),
        "master_folder_context_counts": dict(sorted(context_counts.items())),
        "shared_blank_exact_match_rows": len(blank_links),
        "shared_blank_record_groups": sorted(
            {link["record_group"] for link in blank_links.values() if link["record_group"]}
        ),
        "known_label_alias_resolutions": known_label_alias_resolutions,
        "known_unresolved_label_conflicts": known_unresolved_label_conflicts,
        "author_confirmation_statuses": {
            confirmation_id: confirmation_by_id[confirmation_id].get("status", "")
            for confirmation_id in sorted(required_confirmation_ids)
        },
        "ethics_approval_record": {
            "record_id": ethics_record.get("record_id", ""),
            "document_status": ethics_record.get("document_status", ""),
            "committee_review_date": ethics_record.get(
                "committee_review_date", ""
            ),
            "letter_date": ethics_record.get("letter_date", ""),
            "decision": ethics_record.get("decision", ""),
            "scope_status": (
                "postdates_2024_acquisitions_retrospective_and_public_sharing_"
                "scope_unresolved"
            ),
            "document_sha256": ethics_record.get("document_sha256", ""),
            "repository_distribution": ethics_record.get(
                "repository_distribution", ""
            ),
        },
        "limitations": [
            "The CSV intentionally omits participant labels, dates, instrument Name/Tag values, master paths, and repository paths; dataset_manifest_row provides the auditable join.",
            "Participant identity is never inferred from spectral similarity.",
            "The author-confirmed code crosswalk resolves acquisition and publication aliases at the deidentified record level; the private participant linkage key remains outside the repository.",
            "Master-folder context records where an exact numerical match was stored; it does not establish the shared blank's sample identity.",
            "lineage_group_id groups records by the exact-content or exact-match evidence used for that relation; it does not prove a common participant, acquisition, or sample identity.",
            "Processed blind-sample and stability outputs may also use the shared blank even when their manifest note does not expose that derivative link.",
            "The inventory is not evidence of consent, ethics approval, anonymisation, or permission for public reuse.",
        ],
        "correction": "The earlier statement that all fifteen shared blank channels were human-sweat-derived was unsupported; exact-match evidence places ten channels in Test HS master folders and five in a Test 4-ATP master folder, copied across eight groups, while sample identity remains unresolved.",
    }
    return inventory, summary


def render_csv(rows: list[dict[str, str]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def render_json(summary: dict[str, object]) -> str:
    return json.dumps(summary, indent=2, ensure_ascii=False) + "\n"


def check_file(path: Path, expected: str) -> bool:
    return path.is_file() and path.read_text(encoding="utf-8") == expected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed CSV or JSON report is missing or stale.",
    )
    args = parser.parse_args(argv)

    root = args.repository_root.resolve()
    rows, summary = build_inventory(root)
    csv_text = render_csv(rows)
    json_text = render_json(summary)
    csv_path = root / "metadata" / "human_data_lineage.csv"
    json_path = root / "metadata" / "human_data_lineage_summary.json"

    if args.check:
        stale = [
            str(path.relative_to(root))
            for path, expected in ((csv_path, csv_text), (json_path, json_text))
            if not check_file(path, expected)
        ]
        if stale:
            print("Stale or missing human-data lineage report: " + ", ".join(stale))
            return 1
        print(f"PASS: human-data lineage report is current ({len(rows)} rows).")
        return 0

    csv_path.write_text(csv_text, encoding="utf-8", newline="")
    json_path.write_text(json_text, encoding="utf-8", newline="")
    print(f"Wrote {csv_path.relative_to(root)} ({len(rows)} rows).")
    print(f"Wrote {json_path.relative_to(root)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
