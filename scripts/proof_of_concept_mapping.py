#!/usr/bin/env python3
"""Generate and verify the confirmed proof-of-concept label mapping.

The historical quarantine is immutable.  This module only relabels the two
publication-facing summary headers, writes identifier-minimised provenance
sidecars, and checks that the numerical bodies and quarantined metadata remain
unchanged.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Iterable, Mapping


UTF8_BOM = b"\xef\xbb\xbf"

PUBLICATION_FILES = {
    "RM_AS_HS.csv": {
        "repository_path": (
            "data/published_snapshot/proof_of_concept/"
            "benchtop_sweat_summary.csv"
        ),
        "source_header": (
            "Raman shift (cm-1),RM_AS,RM_HS_V2,RM_HS_V3,RM_HS_V4"
        ),
        "publication_header": (
            "Raman shift (cm-1),RM_AS,RM_HS_V1,RM_HS_V2,RM_HS_V3"
        ),
        "source_label_set": "V2|V3|V4",
        "publication_label_set": "V1|V2|V3",
        "source_sha256": (
            "80c7d55ffc0081c30a06f78fca567b76ff8b84cd66cd303ced36d6cf68334c16"
        ),
        "repository_sha256": (
            "82c1294c1c3df1c5b12ea63ee65742130efc8d57ba6a8d6ffeaf4a529975cba8"
        ),
        "numerical_body_sha256": (
            "d7020690de750ff33a7c9c9c50c0e3c3984ba0a689402547161b36e5237181de"
        ),
    },
    "RP_AS_HS.csv": {
        "repository_path": (
            "data/published_snapshot/proof_of_concept/portable_sweat_summary.csv"
        ),
        "source_header": (
            "Raman shift (cm-1),RP_AS,RP_HS_V2,RP_HS_V3,RP_HS_V4"
        ),
        "publication_header": (
            "Raman shift (cm-1),RP_AS,RP_HS_V1,RP_HS_V2,RP_HS_V3"
        ),
        "source_label_set": "V2|V3|V4",
        "publication_label_set": "V1|V2|V3",
        "source_sha256": (
            "50c6e67d9b7b6deb7f2b629f9f1a726f4cf62530bc380b411cddd8a637f63075"
        ),
        "repository_sha256": (
            "c23f7003c8d74afbf924421f1e4143ed178bc2df364b80a52ca208eb83cbf802"
        ),
        "numerical_body_sha256": (
            "db8ac8daa713ae19cb4998e244f06b43093015f80c2e86f6bf2c0ad21329a684"
        ),
    },
}

NORMALIZED_PUBLICATION_FILE = {
    "repository_path": (
        "data/published_snapshot/proof_of_concept/"
        "benchtop_vs_portable_normalized.csv"
    ),
    "source_label_set": "V1|V2|V3",
    "publication_label_set": "V1|V2|V3",
    "source_sha256": (
        "85dc95bb9360f0e1d7b0f96a39288513d9738f111d0f5e901b766dca9281aee0"
    ),
    "repository_sha256": (
        "85dc95bb9360f0e1d7b0f96a39288513d9738f111d0f5e901b766dca9281aee0"
    ),
    "numerical_body_sha256": (
        "327c1911e017733f1d680e814cf542317d2acf082a911c8b1d151e08e5df60e9"
    ),
}

PUBLICATION_MANIFEST_NOTE = (
    "Header-only author-confirmed relabelling from acquisition codes V2-V4 "
    "to publication traces V1-V3; Raman shifts and numerical values are "
    "unchanged. See metadata/proof_of_concept_code_crosswalk.csv and "
    "metadata/provenance/publication_header_corrections.csv."
)

REQUIRED_CONFIRMATION_IDS = {
    "aa_hs_session_metadata_correction",
    "publication_renumbering_confirmed",
    "vp_numeric_crosswalk_confirmed",
}

CROSSWALK_FIELDS = [
    "acquisition_index",
    "acquisition_v_code",
    "acquisition_p_code",
    "publication_index",
    "publication_code",
    "included_in_figure6",
    "reason",
    "evidence",
    "resolution_status",
]

CROSSWALK_ROWS = [
    {
        "acquisition_index": "1",
        "acquisition_v_code": "V1",
        "acquisition_p_code": "P1",
        "publication_index": "",
        "publication_code": "",
        "included_in_figure6": "false",
        "reason": "no_usable_signal",
        "evidence": "author_confirmation:publication_renumbering_confirmed",
        "resolution_status": "confirmed_excluded_from_publication_numbering",
    },
    {
        "acquisition_index": "2",
        "acquisition_v_code": "V2",
        "acquisition_p_code": "P2",
        "publication_index": "1",
        "publication_code": "V1",
        "included_in_figure6": "true",
        "reason": "",
        "evidence": (
            "author_confirmation:vp_numeric_crosswalk_confirmed+"
            "publication_renumbering_confirmed"
        ),
        "resolution_status": "confirmed",
    },
    {
        "acquisition_index": "3",
        "acquisition_v_code": "V3",
        "acquisition_p_code": "P3",
        "publication_index": "2",
        "publication_code": "V2",
        "included_in_figure6": "true",
        "reason": "",
        "evidence": (
            "author_confirmation:vp_numeric_crosswalk_confirmed+"
            "publication_renumbering_confirmed"
        ),
        "resolution_status": "confirmed",
    },
    {
        "acquisition_index": "4",
        "acquisition_v_code": "V4",
        "acquisition_p_code": "P4",
        "publication_index": "3",
        "publication_code": "V3",
        "included_in_figure6": "true",
        "reason": "",
        "evidence": (
            "author_confirmation:vp_numeric_crosswalk_confirmed+"
            "publication_renumbering_confirmed"
        ),
        "resolution_status": "confirmed",
    },
]

LABEL_EVIDENCE_FIELDS = [
    "dataset_manifest_row",
    "artifact_sha256",
    "artifact_stage",
    "instrument",
    "evidence_scope",
    "observed_outer_label",
    "outer_label_namespace",
    "observed_embedded_or_internal_label",
    "embedded_or_internal_namespace",
    "observed_master_label",
    "confirmed_acquisition_label",
    "confirmed_publication_label",
    "confirmed_session",
    "resolution_status",
    "evidence",
]

_QUARANTINE = "data/quarantine/legacy_snapshot/Proof of concept"
LABEL_EVIDENCE_SPECS = [
    {
        "repository_path": (
            f"{_QUARANTINE}/Portable Raman/Original spectra/AA_HS_V1S1_H.csv"
        ),
        "artifact_stage": "raw",
        "instrument": "portable_raman",
        "observed_outer_label": "V1S1",
        "outer_label_namespace": "publication",
        "observed_embedded_or_internal_label": "V2S2",
        "embedded_or_internal_namespace": "acquisition_metadata_error",
        "observed_master_label": "V2S1",
        "confirmed_acquisition_label": "V2S1",
        "confirmed_publication_label": "V1S1",
        "confirmed_session": "S1",
        "resolution_status": "resolved_embedded_session_metadata_error",
        "evidence": "author_confirmation:aa_hs_session_metadata_correction",
    },
    {
        "repository_path": (
            f"{_QUARANTINE}/Portable Raman/Original spectra/AA_HS_V1S1_H_2.csv"
        ),
        "artifact_stage": "raw",
        "instrument": "portable_raman",
        "observed_outer_label": "V1S1",
        "outer_label_namespace": "publication",
        "observed_embedded_or_internal_label": "V2S2",
        "embedded_or_internal_namespace": "acquisition_metadata_error",
        "observed_master_label": "V2S1",
        "confirmed_acquisition_label": "V2S1",
        "confirmed_publication_label": "V1S1",
        "confirmed_session": "S1",
        "resolution_status": "resolved_embedded_session_metadata_error",
        "evidence": "author_confirmation:aa_hs_session_metadata_correction",
    },
    {
        "repository_path": (
            f"{_QUARANTINE}/Portable Raman/Original spectra/"
            "HS_AAB_P1_750_5_5_H_S1.csv"
        ),
        "artifact_stage": "raw",
        "instrument": "portable_raman",
        "observed_outer_label": "P1S1",
        "outer_label_namespace": "publication",
        "observed_embedded_or_internal_label": "P2S1",
        "embedded_or_internal_namespace": "acquisition",
        "observed_master_label": "P2S1",
        "confirmed_acquisition_label": "P2S1",
        "confirmed_publication_label": "V1S1",
        "confirmed_session": "S1",
        "resolution_status": "resolved_dual_label_namespace",
        "evidence": (
            "author_confirmation:vp_numeric_crosswalk_confirmed+"
            "publication_renumbering_confirmed"
        ),
    },
    {
        "repository_path": (
            f"{_QUARANTINE}/Portable Raman/Original spectra/"
            "HS_AAB_P1_750_5_5_H_S3.csv"
        ),
        "artifact_stage": "raw",
        "instrument": "portable_raman",
        "observed_outer_label": "P1S3",
        "outer_label_namespace": "publication",
        "observed_embedded_or_internal_label": "P2S3",
        "embedded_or_internal_namespace": "acquisition",
        "observed_master_label": "P2S3",
        "confirmed_acquisition_label": "P2S3",
        "confirmed_publication_label": "V1S3",
        "confirmed_session": "S3",
        "resolution_status": "resolved_dual_label_namespace",
        "evidence": (
            "author_confirmation:vp_numeric_crosswalk_confirmed+"
            "publication_renumbering_confirmed"
        ),
    },
    {
        "repository_path": (
            f"{_QUARANTINE}/Portable Raman/Original spectra/"
            "HS_AAB_P2_750_5_5_H_S1_I1_I2_I3_I4_I5.csv"
        ),
        "artifact_stage": "raw",
        "instrument": "portable_raman",
        "observed_outer_label": "P2S1",
        "outer_label_namespace": "publication",
        "observed_embedded_or_internal_label": "P3S1",
        "embedded_or_internal_namespace": "acquisition",
        "observed_master_label": "P3S1",
        "confirmed_acquisition_label": "P3S1",
        "confirmed_publication_label": "V2S1",
        "confirmed_session": "S1",
        "resolution_status": "resolved_dual_label_namespace",
        "evidence": (
            "author_confirmation:vp_numeric_crosswalk_confirmed+"
            "publication_renumbering_confirmed"
        ),
    },
    {
        "repository_path": (
            f"{_QUARANTINE}/Portable Raman/Original spectra/"
            "HS_AAB_P3_750_5_5_H_S3_I1_I2_I3_I4_I5.csv"
        ),
        "artifact_stage": "raw",
        "instrument": "portable_raman",
        "observed_outer_label": "P3S3",
        "outer_label_namespace": "publication",
        "observed_embedded_or_internal_label": "P4S3",
        "embedded_or_internal_namespace": "acquisition",
        "observed_master_label": "P4S3",
        "confirmed_acquisition_label": "P4S3",
        "confirmed_publication_label": "V3S3",
        "confirmed_session": "S3",
        "resolution_status": "resolved_dual_label_namespace",
        "evidence": (
            "author_confirmation:vp_numeric_crosswalk_confirmed+"
            "publication_renumbering_confirmed"
        ),
    },
    {
        "repository_path": (
            f"{_QUARANTINE}/Portable Raman/Processed spectra/"
            "AA_HS_V1S1_H_2_blank_subtracted_processed.csv"
        ),
        "artifact_stage": "processed",
        "instrument": "portable_raman",
        "evidence_scope": "distributed_apparent_v1_p1_resolution",
        "observed_outer_label": "V1S1",
        "outer_label_namespace": "publication",
        "observed_embedded_or_internal_label": "V2S1",
        "embedded_or_internal_namespace": "acquisition",
        "observed_master_label": "",
        "confirmed_acquisition_label": "V2S1",
        "confirmed_publication_label": "V1S1",
        "confirmed_session": "S1",
        "resolution_status": "resolved_processed_header_namespace",
        "evidence": (
            "author_confirmation:publication_renumbering_confirmed+"
            "processed_column_headers"
        ),
    },
    {
        "repository_path": (
            f"{_QUARANTINE}/Portable Raman/Processed spectra/"
            "AA_HS_V1S1_H_blank_subtracted_processed.csv"
        ),
        "artifact_stage": "processed",
        "instrument": "portable_raman",
        "evidence_scope": "distributed_apparent_v1_p1_resolution",
        "observed_outer_label": "V1S1",
        "outer_label_namespace": "publication",
        "observed_embedded_or_internal_label": "V2S1",
        "embedded_or_internal_namespace": "acquisition",
        "observed_master_label": "",
        "confirmed_acquisition_label": "V2S1",
        "confirmed_publication_label": "V1S1",
        "confirmed_session": "S1",
        "resolution_status": "resolved_processed_header_namespace",
        "evidence": (
            "author_confirmation:publication_renumbering_confirmed+"
            "processed_column_headers"
        ),
    },
    {
        "repository_path": (
            f"{_QUARANTINE}/Portable Raman/Processed spectra/"
            "HS_AAB_P1_750_5_5_H_S3_blank_subtracted_processed.csv"
        ),
        "artifact_stage": "processed",
        "instrument": "portable_raman",
        "evidence_scope": "distributed_apparent_v1_p1_resolution",
        "observed_outer_label": "P1S3",
        "outer_label_namespace": "publication",
        "observed_embedded_or_internal_label": "P2S3",
        "embedded_or_internal_namespace": "acquisition",
        "observed_master_label": "",
        "confirmed_acquisition_label": "P2S3",
        "confirmed_publication_label": "V1S3",
        "confirmed_session": "S3",
        "resolution_status": "resolved_processed_header_namespace",
        "evidence": (
            "author_confirmation:vp_numeric_crosswalk_confirmed+"
            "publication_renumbering_confirmed+processed_column_headers"
        ),
    },
    {
        "repository_path": (
            f"{_QUARANTINE}/Portable Raman/Processed spectra/"
            "RP_AAB_HS_V1_blank_subtracted_processed.csv"
        ),
        "artifact_stage": "processed",
        "instrument": "portable_raman",
        "evidence_scope": "distributed_apparent_v1_p1_resolution",
        "observed_outer_label": "V1",
        "outer_label_namespace": "publication",
        "observed_embedded_or_internal_label": "V2S1|P2S1|P2S3",
        "embedded_or_internal_namespace": "acquisition",
        "observed_master_label": "",
        "confirmed_acquisition_label": "V2|P2",
        "confirmed_publication_label": "V1",
        "confirmed_session": "S1|S3",
        "resolution_status": "resolved_dual_label_namespace_aggregate",
        "evidence": (
            "author_confirmation:vp_numeric_crosswalk_confirmed+"
            "publication_renumbering_confirmed+processed_column_headers"
        ),
    },
    {
        "repository_path": (
            f"{_QUARANTINE}/Benchtop Raman/Processed spectra/"
            "HS_V2S1_AAB_C2_S1_I1_I2_C1_I1_blank_subtracted_processed.csv"
        ),
        "artifact_stage": "processed",
        "instrument": "benchtop_raman",
        "observed_outer_label": "V2S1",
        "outer_label_namespace": "publication",
        "observed_embedded_or_internal_label": "V3S1",
        "embedded_or_internal_namespace": "acquisition",
        "observed_master_label": "",
        "confirmed_acquisition_label": "V3S1",
        "confirmed_publication_label": "V2S1",
        "confirmed_session": "S1",
        "resolution_status": "resolved_dual_label_namespace_duplicate",
        "evidence": (
            "author_confirmation:publication_renumbering_confirmed+"
            "metadata/provenance/duplicate_content_groups.csv"
        ),
    },
    {
        "repository_path": (
            f"{_QUARANTINE}/Benchtop Raman/Processed spectra/"
            "HS_V3S1_AAB_C2_S1_I1_I2_blank_subtracted_processed.csv"
        ),
        "artifact_stage": "processed",
        "instrument": "benchtop_raman",
        "observed_outer_label": "V3S1",
        "outer_label_namespace": "acquisition",
        "observed_embedded_or_internal_label": "V3S1",
        "embedded_or_internal_namespace": "acquisition",
        "observed_master_label": "",
        "confirmed_acquisition_label": "V3S1",
        "confirmed_publication_label": "V2S1",
        "confirmed_session": "S1",
        "resolution_status": "resolved_dual_label_namespace_duplicate",
        "evidence": (
            "author_confirmation:publication_renumbering_confirmed+"
            "metadata/provenance/duplicate_content_groups.csv"
        ),
    },
    {
        "repository_path": (
            f"{_QUARANTINE}/Benchtop Raman/Original spectra/"
            "HS_V1S3_AAB_C1_S4_I1_I2_V2S2_C2_I1_I2_I3_C1_I1_I2_I3_"
            "V2S1_C4_S5_I2_I3_C4_S2_I2.csv"
        ),
        "artifact_stage": "raw",
        "instrument": "benchtop_raman",
        "evidence_scope": "resolved_benchtop_composite",
        "observed_outer_label": "mixed_V1_and_V2",
        "outer_label_namespace": "mixed_historical_filename",
        "observed_embedded_or_internal_label": "",
        "embedded_or_internal_namespace": "not_available",
        "observed_master_label": "V2S1|V2S2|V2S3",
        "confirmed_acquisition_label": "V2",
        "confirmed_publication_label": "V1",
        "confirmed_session": "S1|S2|S3",
        "resolution_status": "resolved_exact_column_assembly",
        "evidence": (
            "author_confirmation:publication_renumbering_confirmed+"
            "exact_columns:dataset_manifest_rows_1679_1680_1682_1683_1684"
        ),
    },
    {
        "repository_path": (
            f"{_QUARANTINE}/Benchtop Raman/Processed spectra/"
            "HS_V1S3_AAB_C1_S4_I1_I2_V1S2_C2_I1_I2_I3_C1_I1_I2_I3_"
            "V1S1_C4_S5_I2_I3_C4_S2_I2_blank_subtracted_processed.csv"
        ),
        "artifact_stage": "processed",
        "instrument": "benchtop_raman",
        "evidence_scope": "resolved_benchtop_composite",
        "observed_outer_label": "V1S1|V1S2|V1S3",
        "outer_label_namespace": "publication",
        "observed_embedded_or_internal_label": "V2S1|V2S2|V2S3",
        "embedded_or_internal_namespace": "acquisition",
        "observed_master_label": "",
        "confirmed_acquisition_label": "V2",
        "confirmed_publication_label": "V1",
        "confirmed_session": "S1|S2|S3",
        "resolution_status": "resolved_dual_label_namespace_composite",
        "evidence": (
            "author_confirmation:publication_renumbering_confirmed+"
            "processed_column_headers"
        ),
    },
]

HEADER_CORRECTION_FIELDS = [
    "repository_path",
    "source_sha256",
    "source_label_set",
    "repository_sha256",
    "repository_label_set",
    "numerical_body_sha256",
    "numerical_body_unchanged",
    "transformation",
    "evidence",
    "resolution_status",
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _split_first_record(data: bytes) -> tuple[bytes, bytes, bytes]:
    newline = data.find(b"\n")
    if newline < 0:
        raise ValueError("CSV has no data records")
    first = data[:newline]
    if first.endswith(b"\r"):
        first = first[:-1]
    bom = UTF8_BOM if first.startswith(UTF8_BOM) else b""
    return bom, first[len(bom):], data[newline + 1:]


def correct_publication_header(path: Path, source_name: str) -> bool:
    """Apply the confirmed header-only correction; return whether it changed."""
    specification = PUBLICATION_FILES.get(source_name)
    if specification is None:
        return False
    data = path.read_bytes()
    newline = data.find(b"\n")
    if newline < 0:
        raise ValueError(f"CSV has no data records: {path}")
    delimiter = b"\r\n" if data[newline - 1:newline] == b"\r" else b"\n"
    bom, header, body = _split_first_record(data)
    source_header = str(specification["source_header"]).encode("utf-8")
    publication_header = str(specification["publication_header"]).encode("utf-8")
    source_delimiter = b"\r\n"
    if header == publication_header and delimiter == source_delimiter:
        return False
    if header not in {source_header, publication_header}:
        raise ValueError(
            f"Unexpected proof-of-concept header in {path}: "
            f"{header.decode('utf-8', errors='replace')!r}"
        )
    # Preserve the source's first-record delimiter. The numerical body is
    # copied byte-for-byte, so the only changed bytes are the three label digits.
    path.write_bytes(bom + publication_header + source_delimiter + body)
    return True


def _csv_bytes(fieldnames: list[str], rows: Iterable[Mapping[str, object]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _manifest_index(
    manifest_rows: list[dict[str, object]],
) -> dict[str, tuple[int, dict[str, object]]]:
    result: dict[str, tuple[int, dict[str, object]]] = {}
    for row_number, row in enumerate(manifest_rows, start=2):
        path = str(row.get("repository_path", ""))
        if not path or path in result:
            raise ValueError(f"Invalid or duplicate dataset-manifest path: {path!r}")
        result[path] = (row_number, row)
    return result


def _label_evidence_rows(
    manifest_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    manifest = _manifest_index(manifest_rows)
    rows: list[dict[str, object]] = []
    for specification in LABEL_EVIDENCE_SPECS:
        path = str(specification["repository_path"])
        if path not in manifest:
            raise ValueError(f"Label-evidence artifact is absent from manifest: {path}")
        row_number, manifest_row = manifest[path]
        output = {
            "dataset_manifest_row": str(row_number),
            "artifact_sha256": str(manifest_row.get("repository_sha256", "")),
            "evidence_scope": specification.get(
                "evidence_scope",
                (
                    "complete_portable_raw_human_mismatch_set"
                    if specification.get("artifact_stage") == "raw"
                    else "resolved_byte_identical_pair"
                ),
            ),
        }
        output.update(
            {
                field: specification.get(field, "")
                for field in LABEL_EVIDENCE_FIELDS
                if field not in output
            }
        )
        rows.append(output)
    return rows


def _header_correction_rows(
    repository_root: Path,
    manifest_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    manifest = _manifest_index(manifest_rows)
    rows: list[dict[str, object]] = []
    specifications = [*PUBLICATION_FILES.values(), NORMALIZED_PUBLICATION_FILE]
    for specification in specifications:
        repository_path = str(specification["repository_path"])
        _, manifest_row = manifest[repository_path]
        data = (repository_root / repository_path).read_bytes()
        _, _, body = _split_first_record(data)
        source_labels = str(specification["source_label_set"])
        repository_labels = str(specification["publication_label_set"])
        changed = source_labels != repository_labels
        rows.append(
            {
                "repository_path": repository_path,
                "source_sha256": str(manifest_row.get("source_sha256", "")),
                "source_label_set": source_labels,
                "repository_sha256": sha256_bytes(data),
                "repository_label_set": repository_labels,
                "numerical_body_sha256": sha256_bytes(body),
                "numerical_body_unchanged": "true",
                "transformation": (
                    "header_only_acquisition_to_publication_relabel"
                    if changed
                    else "none_already_uses_publication_labels"
                ),
                "evidence": (
                    "author_confirmation:publication_renumbering_confirmed"
                ),
                "resolution_status": "confirmed",
            }
        )
    return rows


def expected_sidecars(
    repository_root: Path,
    manifest_rows: list[dict[str, object]],
) -> dict[Path, bytes]:
    return {
        repository_root / "metadata" / "proof_of_concept_code_crosswalk.csv": (
            _csv_bytes(CROSSWALK_FIELDS, CROSSWALK_ROWS)
        ),
        repository_root
        / "metadata"
        / "provenance"
        / "proof_of_concept_label_evidence.csv": _csv_bytes(
            LABEL_EVIDENCE_FIELDS,
            _label_evidence_rows(manifest_rows),
        ),
        repository_root
        / "metadata"
        / "provenance"
        / "publication_header_corrections.csv": _csv_bytes(
            HEADER_CORRECTION_FIELDS,
            _header_correction_rows(repository_root, manifest_rows),
        ),
    }


def write_mapping_sidecars(
    repository_root: Path,
    manifest_rows: list[dict[str, object]],
) -> None:
    for path, content in expected_sidecars(repository_root, manifest_rows).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def _read_manifest(path: Path) -> tuple[list[str], list[dict[str, object]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), [dict(row) for row in reader]


def _update_manifest(repository_root: Path) -> list[dict[str, object]]:
    manifest_path = repository_root / "metadata" / "dataset_manifest.csv"
    fieldnames, rows = _read_manifest(manifest_path)
    manifest = _manifest_index(rows)
    for specification in PUBLICATION_FILES.values():
        repository_path = str(specification["repository_path"])
        _, row = manifest[repository_path]
        data = (repository_root / repository_path).read_bytes()
        if row.get("source_sha256") != specification["source_sha256"]:
            raise ValueError(f"Unexpected source hash for {repository_path}")
        row["repository_sha256"] = sha256_bytes(data)
        row["repository_bytes"] = str(len(data))
        row["note"] = PUBLICATION_MANIFEST_NOTE
    manifest_path.write_bytes(_csv_bytes(fieldnames, rows))
    return rows


def generate(repository_root: Path) -> None:
    for source_name, specification in PUBLICATION_FILES.items():
        correct_publication_header(
            repository_root / str(specification["repository_path"]), source_name
        )
    manifest_rows = _update_manifest(repository_root)
    write_mapping_sidecars(repository_root, manifest_rows)


def verify(repository_root: Path) -> list[str]:
    errors: list[str] = []
    manifest_path = repository_root / "metadata" / "dataset_manifest.csv"
    _, manifest_rows = _read_manifest(manifest_path)
    manifest = _manifest_index(manifest_rows)

    confirmation_path = repository_root / "metadata" / "author_confirmations.csv"
    with confirmation_path.open("r", encoding="utf-8-sig", newline="") as handle:
        confirmation_ids = {
            row.get("confirmation_id", "") for row in csv.DictReader(handle)
        }
    missing_confirmations = REQUIRED_CONFIRMATION_IDS - confirmation_ids
    if missing_confirmations:
        errors.append(
            "Missing author confirmation IDs: "
            + ", ".join(sorted(missing_confirmations))
        )

    for specification in PUBLICATION_FILES.values():
        repository_path = str(specification["repository_path"])
        data = (repository_root / repository_path).read_bytes()
        _, header, body = _split_first_record(data)
        if header.decode("utf-8") != specification["publication_header"]:
            errors.append(f"Incorrect publication header: {repository_path}")
        if sha256_bytes(data) != specification["repository_sha256"]:
            errors.append(f"Unexpected publication-file hash: {repository_path}")
        if sha256_bytes(body) != specification["numerical_body_sha256"]:
            errors.append(f"Numerical body changed: {repository_path}")
        _, manifest_row = manifest[repository_path]
        if manifest_row.get("source_sha256") != specification["source_sha256"]:
            errors.append(f"Unexpected source hash in manifest: {repository_path}")
        if manifest_row.get("repository_sha256") != sha256_bytes(data):
            errors.append(f"Stale repository hash in manifest: {repository_path}")
        if manifest_row.get("repository_bytes") != str(len(data)):
            errors.append(f"Stale repository size in manifest: {repository_path}")
        if manifest_row.get("note") != PUBLICATION_MANIFEST_NOTE:
            errors.append(f"Stale relabelling note in manifest: {repository_path}")

    normalized_path = str(NORMALIZED_PUBLICATION_FILE["repository_path"])
    normalized_data = (repository_root / normalized_path).read_bytes()
    _, _, normalized_body = _split_first_record(normalized_data)
    if sha256_bytes(normalized_data) != NORMALIZED_PUBLICATION_FILE["repository_sha256"]:
        errors.append(f"Unexpected normalized publication hash: {normalized_path}")
    if sha256_bytes(normalized_body) != NORMALIZED_PUBLICATION_FILE["numerical_body_sha256"]:
        errors.append(f"Normalized numerical body changed: {normalized_path}")

    for specification in LABEL_EVIDENCE_SPECS[:2]:
        path = repository_root / str(specification["repository_path"])
        data = path.read_bytes()
        if b"Name,AA_HS_V2S2_H.csv" not in data or b"Tag,AA_HS_V2S2_H" not in data:
            errors.append(f"Quarantined AA metadata was modified: {path}")

    expected = expected_sidecars(repository_root, manifest_rows)
    for path, content in expected.items():
        if not path.is_file():
            errors.append(f"Missing mapping sidecar: {path.relative_to(repository_root)}")
        elif path.read_bytes() != content:
            errors.append(f"Stale mapping sidecar: {path.relative_to(repository_root)}")
    return errors


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="Verify committed files")
    action.add_argument("--write", action="store_true", help="Regenerate assigned files")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repository_root = args.repository_root.resolve()
    if args.write:
        generate(repository_root)
    errors = verify(repository_root)
    report = {"ok": not errors, "errors": errors}
    print(json.dumps(report, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
