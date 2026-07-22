#!/usr/bin/env python3
"""Verify the committed 4-ATP blank audit without modifying repository data.

The check deliberately uses only the Python standard library.  It verifies the
two audit tables, then independently rebuilds the historical shared-blank
mapping from ``raw_to_master_best_matches.csv``.  The scientific suitability
table is conservative by design: no row may claim a confirmed blank while the
material or acquisition context remains unresolved.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterable


SHARED_TABLE_FIELDS = (
    "prepared_replicate",
    "prepared_accumulations",
    "prepared_record_groups",
    "prepared_copy_count",
    "master_folder_context",
    "canonical_master_path",
    "master_file_sha256",
    "embedded_datetime",
    "embedded_tag",
    "master_setting",
    "intensity_max_abs_difference",
    "axis_max_abs_difference",
    "axis_match_1e-5",
    "scientific_assessment",
)
FAMILY_TABLE_FIELDS = (
    "family_id",
    "scope",
    "required_session",
    "required_setting",
    "required_material",
    "nearest_candidate_path",
    "candidate_sha256",
    "candidate_embedded_datetime",
    "candidate_tag",
    "material_match",
    "session_match",
    "integration_match",
    "power_match",
    "averaging_match",
    "data_count_match",
    "resolution_status",
    "reason",
)
MATCH_FIELDS = (
    "material_match",
    "session_match",
    "integration_match",
    "power_match",
    "averaging_match",
    "data_count_match",
)
MATCH_VALUES = {"true", "false", "unresolved"}
RESOLUTION_STATUSES = {
    "no_confirmed_context_match",
    "provisional_context_match_pending_author_confirmation",
}
SHARED_ASSESSMENTS = {"historical_input_wrong_context"}

EXPECTED_GROUPS = (
    "Blind samples",
    "Calibration curve",
    "Optimisation/500_5_5_L",
    "Optimisation/750_5_5_H",
    "Optimisation/750_5_5_M",
    "Stability/03_07_24",
    "Stability/19_05_24",
    "Stability/24_09_24",
)
REQUIRED_BLANK_MATERIAL = "AuAgBC substrate without 4-ATP"
EXPECTED_FAMILY_ROWS = {
    "calibration_curve": {
        "scope": "published_4atp_calibration_condition",
        "required_session": "2024-07-03",
        "required_setting": "750_5_5_L",
        "required_material": REQUIRED_BLANK_MATERIAL,
        "nearest_candidate_path": "Test 4-ATP/03-07-24/Blank/BC Blank 750_5_5_L.csv",
        "candidate_embedded_datetime": "2024-07-03T10:13:49",
        "candidate_tag": "BC Blank_750_5_5_l",
        "material_match": "false",
        "session_match": "true",
        "integration_match": "true",
        "power_match": "true",
        "averaging_match": "true",
        "data_count_match": "true",
        "resolution_status": "no_confirmed_context_match",
    },
    "blind_samples_prepared_2024_09_24": {
        "scope": "prepared_concentration_labelled_snapshot",
        "required_session": "2024-09-24",
        "required_setting": "750_5_5_L",
        "required_material": REQUIRED_BLANK_MATERIAL,
        "nearest_candidate_path": "Test 4-ATP/24-09-24/Blank/Blanck_AABC_750_5_5_H.csv",
        "candidate_embedded_datetime": "2024-09-24T09:33:50",
        "candidate_tag": "Blanck_AABC_750_5_5_H",
        "material_match": "unresolved",
        "session_match": "true",
        "integration_match": "true",
        "power_match": "false",
        "averaging_match": "true",
        "data_count_match": "true",
        "resolution_status": "no_confirmed_context_match",
    },
    "blind_samples_intended_2024_09_10": {
        "scope": "intended_coded_blind_experiment",
        "required_session": "2024-09-10",
        "required_setting": "750_5_5_L",
        "required_material": REQUIRED_BLANK_MATERIAL,
        "nearest_candidate_path": "Precision y exactitud/10-09-24/Blank/AABC Blank_750_5_5_H.csv",
        "candidate_embedded_datetime": "2024-09-10T14:18:28",
        "candidate_tag": "AAG Blank_750_5_5_H",
        "material_match": "unresolved",
        "session_match": "true",
        "integration_match": "true",
        "power_match": "false",
        "averaging_match": "true",
        "data_count_match": "true",
        "resolution_status": "no_confirmed_context_match",
    },
    "optimisation_500_5_5_L": {
        "scope": "optimisation_condition",
        "required_session": "2024-07-03",
        "required_setting": "500_5_5_L",
        "required_material": REQUIRED_BLANK_MATERIAL,
        "nearest_candidate_path": "Test 4-ATP/03-07-24/Blank/BC Blank 750_5_5_L.csv",
        "candidate_embedded_datetime": "2024-07-03T10:13:49",
        "candidate_tag": "BC Blank_750_5_5_l",
        "material_match": "false",
        "session_match": "true",
        "integration_match": "false",
        "power_match": "true",
        "averaging_match": "true",
        "data_count_match": "true",
        "resolution_status": "no_confirmed_context_match",
    },
    "optimisation_750_5_5_H": {
        "scope": "optimisation_condition",
        "required_session": "2024-09-24",
        "required_setting": "750_5_5_H",
        "required_material": REQUIRED_BLANK_MATERIAL,
        "nearest_candidate_path": "Test 4-ATP/24-09-24/Blank/Blanck_AABC_750_5_5_H.csv",
        "candidate_embedded_datetime": "2024-09-24T09:33:50",
        "candidate_tag": "Blanck_AABC_750_5_5_H",
        "material_match": "unresolved",
        "session_match": "true",
        "integration_match": "true",
        "power_match": "true",
        "averaging_match": "true",
        "data_count_match": "true",
        "resolution_status": "provisional_context_match_pending_author_confirmation",
    },
    "optimisation_750_5_5_M": {
        "scope": "optimisation_condition",
        "required_session": "2024-09-24",
        "required_setting": "750_5_5_M",
        "required_material": REQUIRED_BLANK_MATERIAL,
        "nearest_candidate_path": "Test 4-ATP/24-09-24/Blank/Blanck_AABC_750_5_5_H.csv",
        "candidate_embedded_datetime": "2024-09-24T09:33:50",
        "candidate_tag": "Blanck_AABC_750_5_5_H",
        "material_match": "unresolved",
        "session_match": "true",
        "integration_match": "true",
        "power_match": "false",
        "averaging_match": "true",
        "data_count_match": "true",
        "resolution_status": "no_confirmed_context_match",
    },
    "stability_day_1_2024_05_19": {
        "scope": "stability_day_1_prepared_family",
        "required_session": "2024-05-19",
        "required_setting": "750_5_5_L",
        "required_material": REQUIRED_BLANK_MATERIAL,
        "nearest_candidate_path": (
            "Parámetros heterogéneos de medición/Primeras mediciones/19-05-24/"
            "Sustrato AuAgBC_4-ATP_N/190524_AuAgBC_blank_750_5_5_H.csv"
        ),
        "candidate_embedded_datetime": "2024-05-20T01:29:47",
        "candidate_tag": "AuAgBC_blank_750_5_5_H",
        "material_match": "true",
        "session_match": "unresolved",
        "integration_match": "true",
        "power_match": "false",
        "averaging_match": "true",
        "data_count_match": "true",
        "resolution_status": "no_confirmed_context_match",
    },
    "stability_day_45_2024_07_03": {
        "scope": "stability_day_45_condition",
        "required_session": "2024-07-03",
        "required_setting": "750_5_5_L",
        "required_material": REQUIRED_BLANK_MATERIAL,
        "nearest_candidate_path": "Test 4-ATP/03-07-24/Blank/BC Blank 750_5_5_L.csv",
        "candidate_embedded_datetime": "2024-07-03T10:13:49",
        "candidate_tag": "BC Blank_750_5_5_l",
        "material_match": "false",
        "session_match": "true",
        "integration_match": "true",
        "power_match": "true",
        "averaging_match": "true",
        "data_count_match": "true",
        "resolution_status": "no_confirmed_context_match",
    },
    "stability_day_128_2024_09_24": {
        "scope": "stability_day_128_condition",
        "required_session": "2024-09-24",
        "required_setting": "750_5_5_L",
        "required_material": REQUIRED_BLANK_MATERIAL,
        "nearest_candidate_path": "Test 4-ATP/24-09-24/Blank/Blanck_AABC_750_5_5_H.csv",
        "candidate_embedded_datetime": "2024-09-24T09:33:50",
        "candidate_tag": "Blanck_AABC_750_5_5_H",
        "material_match": "unresolved",
        "session_match": "true",
        "integration_match": "true",
        "power_match": "false",
        "averaging_match": "true",
        "data_count_match": "true",
        "resolution_status": "no_confirmed_context_match",
    },
}
EXPECTED_FAMILY_IDS = set(EXPECTED_FAMILY_ROWS)
EXPECTED_SOURCES = {
    1: {
        "path": "Test HS/25-09-24/Blank/AAB_Blank_750_5_5_H.csv",
        "sha256": "0afc7b1d9e4c687fa1905653ffb82f15a775f30bb890e3f41f493d089b7fa7f1",
        "context": "test_hs",
        "datetime": "2024-09-25T10:48:15",
        "axis_difference": 4.99989937452483e-07,
        "axis_match": True,
    },
    2: {
        "path": "Test HS/30-09-24/Blank/AAB_Blank_750_5_5_H.csv",
        "sha256": "129df9858e729e80689b1ed009484396b99396320f75500b19a4fbb3eb45db0e",
        "context": "test_hs",
        "datetime": "2024-09-30T12:33:37",
        "axis_difference": 0.0535730875099034,
        "axis_match": False,
    },
    3: {
        "path": "Test 4-ATP/18-09-24/Blank/AAB_Blank_750_5_5_H.csv",
        "sha256": "e80ad94586e537db019cc1b7ca324324a25695fa2ccac3a7c31404c6ce530dbd",
        "context": "test_4atp",
        "datetime": "2024-09-18T16:58:16",
        "axis_difference": 0.1610174642698894,
        "axis_match": False,
    },
}
KNOWN_CANDIDATE_HASHES = {
    "Test 4-ATP/03-07-24/Blank/BC Blank 750_5_5_L.csv": (
        "40cfd5b9753568f36381b1596c3e104d8dcda4974dc15cd8f9b013c56001e490"
    ),
    "Precision y exactitud/10-09-24/Blank/AABC Blank_750_5_5_H.csv": (
        "d0b175f45c6fdd717bdf5d3aed02ae116fb8635901ac35c4772ed3ce906de09c"
    ),
    "Test 4-ATP/24-09-24/Blank/Blanck_AABC_750_5_5_H.csv": (
        "e36f0ad7a57ebab8cba038309284305cfecc98d1586499fe73e266e301257dd9"
    ),
    (
        "Parámetros heterogéneos de medición/Primeras mediciones/19-05-24/"
        "Sustrato AuAgBC_4-ATP_N/190524_AuAgBC_blank_750_5_5_H.csv"
    ): "fa77c623f6fbff870353847cd3bd16599e399c34f2a3041d7d81ba90cc9c91eb",
}

BLANK_PATH = re.compile(
    r"(?:^|/)blank_rep(?P<replicate>[1-3])_acc(?P<accumulation>[1-5])\.csv$",
    re.IGNORECASE,
)
SHA256 = re.compile(r"[0-9a-f]{64}")
DATE_TIME = re.compile(r"20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def _read_csv(
    path: Path,
    expected_fields: tuple[str, ...] | None,
    errors: list[str],
) -> list[dict[str, str]]:
    if not path.is_file():
        errors.append(f"Missing required audit file: {path.as_posix()}")
        return []
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            actual_fields = tuple(reader.fieldnames or ())
            if expected_fields is not None and actual_fields != expected_fields:
                errors.append(
                    f"{path.name} schema mismatch: expected {list(expected_fields)!r}, "
                    f"found {list(actual_fields)!r}"
                )
            return [dict(row) for row in reader]
    except (OSError, UnicodeError, csv.Error) as exc:
        errors.append(f"Could not read {path.as_posix()}: {exc}")
        return []


def _number(value: str, context: str, errors: list[str]) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        errors.append(f"{context} must be numeric, found {value!r}")
        return None
    if not math.isfinite(number) or number < 0:
        errors.append(f"{context} must be a finite non-negative number, found {value!r}")
        return None
    return number


def _positive_integer(value: str, context: str, errors: list[str]) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        errors.append(f"{context} must be a positive integer, found {value!r}")
        return None
    if number <= 0:
        errors.append(f"{context} must be a positive integer, found {value!r}")
        return None
    return number


def _boolean(value: str, context: str, errors: list[str]) -> bool | None:
    normalised = value.strip().lower()
    if normalised == "true":
        return True
    if normalised == "false":
        return False
    errors.append(f"{context} must be true or false, found {value!r}")
    return None


def _portable_relative_path(value: str, context: str, errors: list[str]) -> None:
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if (
        not value
        or value != value.strip()
        or "\\" in value
        or posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or any(part in {"", ".", ".."} for part in posix.parts)
    ):
        errors.append(
            f"{context} must be a safe forward-slash relative path, found {value!r}"
        )


def _verify_shared_mapping(
    mapping_rows: list[dict[str, str]], errors: list[str]
) -> dict[int, dict[str, object]]:
    blank_rows: list[tuple[dict[str, str], int, int, int]] = []
    for row_number, row in enumerate(mapping_rows, start=2):
        path = row.get("curated_path", "")
        if "blank_rep" not in path.lower():
            continue
        match = BLANK_PATH.search(path)
        if match is None:
            errors.append(
                f"raw_to_master_best_matches.csv row {row_number} has an "
                f"unrecognised prepared blank path: {path!r}"
            )
            continue
        blank_rows.append(
            (
                row,
                row_number,
                int(match.group("replicate")),
                int(match.group("accumulation")),
            )
        )

    if len(blank_rows) != 120:
        errors.append(
            "raw_to_master_best_matches.csv must contain exactly 120 prepared "
            f"blank records, found {len(blank_rows)}"
        )

    group_counts = Counter(row.get("curated_group", "") for row, _, _, _ in blank_rows)
    expected_group_counts = Counter({group: 15 for group in EXPECTED_GROUPS})
    if group_counts != expected_group_counts:
        errors.append(
            "Prepared blank group counts differ from the eight audited groups: "
            f"{dict(sorted(group_counts.items()))!r}"
        )

    expected_pairs = {(replicate, accumulation) for replicate in range(1, 4) for accumulation in range(1, 6)}
    pairs_by_group: dict[str, set[tuple[int, int]]] = defaultdict(set)
    source_counts: Counter[str] = Counter()
    channel_counts: Counter[tuple[str, int]] = Counter()
    aggregate: dict[int, dict[str, object]] = {}

    for row, row_number, replicate, accumulation in blank_rows:
        context = f"raw_to_master_best_matches.csv row {row_number}"
        group = row.get("curated_group", "")
        pairs_by_group[group].add((replicate, accumulation))
        expected_source = EXPECTED_SOURCES[replicate]
        source_path = row.get("master_path", "")
        source_counts[source_path] += 1

        try:
            master_column = int(row.get("master_column_index", ""))
        except ValueError:
            errors.append(
                f"{context} has a non-integer master_column_index: "
                f"{row.get('master_column_index')!r}"
            )
            master_column = -1
        channel_counts[(source_path, master_column)] += 1

        if source_path != expected_source["path"]:
            errors.append(
                f"{context} maps replicate {replicate} to {source_path!r}; "
                f"expected {expected_source['path']!r}"
            )
        if master_column != accumulation:
            errors.append(
                f"{context} maps accumulation {accumulation} to master column "
                f"{master_column}"
            )
        if row.get("master_source") != "master_portable":
            errors.append(f"{context} is not linked to master_portable")
        if row.get("master_setting") != "750_5_5_H":
            errors.append(
                f"{context} has unexpected source setting {row.get('master_setting')!r}"
            )
        intensity = _number(
            row.get("intensity_max_abs_difference", ""),
            f"{context} intensity_max_abs_difference",
            errors,
        )
        if intensity is not None and intensity != 0.0:
            errors.append(
                f"{context} is not an exact intensity match (difference {intensity})"
            )
        axis = _number(
            row.get("axis_max_abs_difference", ""),
            f"{context} axis_max_abs_difference",
            errors,
        )
        axis_match = _boolean(
            row.get("axis_match_1e-5", ""),
            f"{context} axis_match_1e-5",
            errors,
        )
        expected_axis = float(expected_source["axis_difference"])
        if axis is not None and not math.isclose(axis, expected_axis, rel_tol=0.0, abs_tol=1e-15):
            errors.append(
                f"{context} axis difference {axis} does not match audited value "
                f"{expected_axis}"
            )
        if axis_match is not None and axis_match != expected_source["axis_match"]:
            errors.append(f"{context} has an inconsistent axis_match_1e-5 value")

        aggregate[replicate] = {
            "path": source_path,
            "axis_difference": axis,
            "axis_match": axis_match,
        }

    for group in EXPECTED_GROUPS:
        if pairs_by_group.get(group, set()) != expected_pairs:
            errors.append(
                f"{group!r} does not contain each replicate/accumulation pair once"
            )
    expected_source_counts = Counter(
        {str(source["path"]): 40 for source in EXPECTED_SOURCES.values()}
    )
    if source_counts != expected_source_counts:
        errors.append(
            "The 120 prepared blanks do not resolve to the three audited sources "
            f"40 times each: {dict(source_counts)!r}"
        )
    expected_channel_counts = Counter(
        {
            (str(source["path"]), channel): 8
            for source in EXPECTED_SOURCES.values()
            for channel in range(1, 6)
        }
    )
    if channel_counts != expected_channel_counts:
        errors.append(
            "Each of the five channels from each shared source must occur once in "
            "each of the eight prepared groups"
        )
    return aggregate


def _verify_shared_table(
    rows: list[dict[str, str]],
    mapping_aggregate: dict[int, dict[str, object]],
    errors: list[str],
) -> None:
    if len(rows) != 3:
        errors.append(
            f"shared_blank_origin_summary.csv must contain three rows, found {len(rows)}"
        )
    seen_replicates: set[int] = set()
    expected_groups = set(EXPECTED_GROUPS)
    for row_number, row in enumerate(rows, start=2):
        context = f"shared_blank_origin_summary.csv row {row_number}"
        replicate = _positive_integer(row.get("prepared_replicate", ""), f"{context} prepared_replicate", errors)
        if replicate is None:
            continue
        if replicate not in EXPECTED_SOURCES:
            errors.append(f"{context} has unexpected replicate {replicate}")
            continue
        if replicate in seen_replicates:
            errors.append(f"{context} duplicates prepared replicate {replicate}")
        seen_replicates.add(replicate)
        expected = EXPECTED_SOURCES[replicate]
        mapped = mapping_aggregate.get(replicate, {})

        accumulations = row.get("prepared_accumulations", "").split("|")
        if accumulations != ["1", "2", "3", "4", "5"]:
            errors.append(f"{context} must list accumulations as 1|2|3|4|5")
        groups = row.get("prepared_record_groups", "").split("|")
        if len(groups) != 8 or set(groups) != expected_groups:
            errors.append(f"{context} must list each of the eight audited groups once")
        copy_count = _positive_integer(
            row.get("prepared_copy_count", ""),
            f"{context} prepared_copy_count",
            errors,
        )
        if copy_count is not None and copy_count != 40:
            errors.append(f"{context} must report 40 prepared copies")

        source_path = row.get("canonical_master_path", "")
        _portable_relative_path(source_path, f"{context} canonical_master_path", errors)
        if source_path != expected["path"] or source_path != mapped.get("path"):
            errors.append(f"{context} canonical source does not match the mapping audit")
        if row.get("master_folder_context") != expected["context"]:
            errors.append(
                f"{context} has unexpected master_folder_context "
                f"{row.get('master_folder_context')!r}"
            )
        digest = row.get("master_file_sha256", "")
        if SHA256.fullmatch(digest) is None:
            errors.append(f"{context} master_file_sha256 is not lowercase SHA-256")
        elif digest != expected["sha256"]:
            errors.append(f"{context} master_file_sha256 differs from the audited hash")
        if DATE_TIME.fullmatch(row.get("embedded_datetime", "")) is None:
            errors.append(f"{context} embedded_datetime has an invalid format")
        elif row.get("embedded_datetime") != expected["datetime"]:
            errors.append(f"{context} embedded_datetime differs from the source header")
        if not row.get("embedded_tag", "").strip():
            errors.append(f"{context} embedded_tag must not be empty")
        if row.get("master_setting") != "750_5_5_H":
            errors.append(f"{context} master_setting must be 750_5_5_H")
        intensity = _number(
            row.get("intensity_max_abs_difference", ""),
            f"{context} intensity_max_abs_difference",
            errors,
        )
        if intensity is not None and intensity != 0.0:
            errors.append(f"{context} must report zero intensity difference")
        axis = _number(
            row.get("axis_max_abs_difference", ""),
            f"{context} axis_max_abs_difference",
            errors,
        )
        if axis is not None and not math.isclose(
            axis,
            float(expected["axis_difference"]),
            rel_tol=0.0,
            abs_tol=1e-15,
        ):
            errors.append(f"{context} axis difference differs from the mapping audit")
        axis_match = _boolean(
            row.get("axis_match_1e-5", ""),
            f"{context} axis_match_1e-5",
            errors,
        )
        if axis_match is not None and axis_match != expected["axis_match"]:
            errors.append(f"{context} axis_match_1e-5 differs from the mapping audit")
        assessment = row.get("scientific_assessment", "")
        if assessment not in SHARED_ASSESSMENTS:
            errors.append(
                f"{context} scientific_assessment must be one of "
                f"{sorted(SHARED_ASSESSMENTS)!r}, found {assessment!r}"
            )
    if seen_replicates != set(EXPECTED_SOURCES):
        errors.append(
            "shared_blank_origin_summary.csv must contain prepared replicates 1, 2, and 3"
        )


def _verify_family_table(rows: list[dict[str, str]], errors: list[str]) -> None:
    family_ids = [row.get("family_id", "") for row in rows]
    if set(family_ids) != EXPECTED_FAMILY_IDS or len(family_ids) != len(EXPECTED_FAMILY_IDS):
        errors.append(
            "4atp_blank_family_assessment.csv must contain exactly the nine audited "
            f"family scopes; found {sorted(family_ids)!r}"
        )
    if len(set(family_ids)) != len(family_ids):
        errors.append("4atp_blank_family_assessment.csv contains duplicate family_id values")

    provisional_rows: list[dict[str, str]] = []
    for row_number, row in enumerate(rows, start=2):
        context = f"4atp_blank_family_assessment.csv row {row_number}"
        family_id = row.get("family_id", "")
        for field in ("family_id", "scope", "required_session", "required_setting", "required_material", "reason"):
            if not row.get(field, "").strip():
                errors.append(f"{context} {field} must not be empty")

        expected_row = EXPECTED_FAMILY_ROWS.get(family_id)
        if expected_row is not None:
            for field, expected_value in expected_row.items():
                if row.get(field) != expected_value:
                    errors.append(
                        f"{context} {field} differs from reviewed audit value: "
                        f"expected {expected_value!r}, found {row.get(field)!r}"
                    )

        candidate_path = row.get("nearest_candidate_path", "")
        _portable_relative_path(candidate_path, f"{context} nearest_candidate_path", errors)
        digest = row.get("candidate_sha256", "")
        if SHA256.fullmatch(digest) is None:
            errors.append(f"{context} candidate_sha256 is not lowercase SHA-256")
        expected_digest = KNOWN_CANDIDATE_HASHES.get(candidate_path)
        if expected_digest is None:
            errors.append(f"{context} candidate path is not in the reviewed hash registry")
        elif digest != expected_digest:
            errors.append(f"{context} candidate_sha256 differs from the audited source hash")
        if DATE_TIME.fullmatch(row.get("candidate_embedded_datetime", "")) is None:
            errors.append(f"{context} candidate_embedded_datetime has an invalid format")
        if not row.get("candidate_tag", "").strip():
            errors.append(f"{context} candidate_tag must not be empty")

        for field in MATCH_FIELDS:
            value = row.get(field, "")
            if value not in MATCH_VALUES:
                errors.append(
                    f"{context} {field} must be one of {sorted(MATCH_VALUES)!r}, "
                    f"found {value!r}"
                )
        status = row.get("resolution_status", "")
        if status not in RESOLUTION_STATUSES:
            errors.append(
                f"{context} resolution_status must be one of "
                f"{sorted(RESOLUTION_STATUSES)!r}, found {status!r}"
            )
            continue
        if status == "provisional_context_match_pending_author_confirmation":
            provisional_rows.append(row)
        elif all(row.get(field) == "true" for field in MATCH_FIELDS):
            errors.append(
                f"{context} marks every context criterion true but reports no confirmed match"
            )

    if len(provisional_rows) != 1:
        errors.append(
            "Exactly one candidate must remain provisional pending author confirmation, "
            f"found {len(provisional_rows)}"
        )
    else:
        row = provisional_rows[0]
        if row.get("family_id") != "optimisation_750_5_5_H":
            errors.append(
                "Only optimisation_750_5_5_H may be the provisional context match"
            )
        for field in (
            "session_match",
            "integration_match",
            "power_match",
            "averaging_match",
            "data_count_match",
        ):
            if row.get(field) != "true":
                errors.append(
                    f"The provisional optimisation_750_5_5_H candidate must have {field}=true"
                )
        if row.get("material_match") != "unresolved":
            errors.append(
                "The provisional optimisation_750_5_5_H material match must remain unresolved"
            )


def verify_audit(repository_root: Path) -> dict[str, object]:
    """Return a read-only verification report for the committed blank audit."""

    root = repository_root.resolve()
    provenance = root / "metadata" / "provenance"
    errors: list[str] = []
    mapping_rows = _read_csv(
        provenance / "raw_to_master_best_matches.csv", None, errors
    )
    shared_rows = _read_csv(
        provenance / "shared_blank_origin_summary.csv", SHARED_TABLE_FIELDS, errors
    )
    family_rows = _read_csv(
        provenance / "4atp_blank_family_assessment.csv", FAMILY_TABLE_FIELDS, errors
    )

    mapping_aggregate = _verify_shared_mapping(mapping_rows, errors)
    _verify_shared_table(shared_rows, mapping_aggregate, errors)
    _verify_family_table(family_rows, errors)
    return {
        "ok": not errors,
        "counts": {
            "prepared_blank_records": sum(
                1
                for row in mapping_rows
                if BLANK_PATH.search(row.get("curated_path", ""))
            ),
            "prepared_record_groups": len(
                {
                    row.get("curated_group", "")
                    for row in mapping_rows
                    if BLANK_PATH.search(row.get("curated_path", ""))
                }
            ),
            "shared_source_files": len(shared_rows),
            "family_assessments": len(family_rows),
            "provisional_candidates": sum(
                row.get("resolution_status")
                == "provisional_context_match_pending_author_confirmation"
                for row in family_rows
            ),
            "confirmed_candidates": sum(
                row.get("resolution_status") == "confirmed_context_match"
                for row in family_rows
            ),
        },
        "errors": errors,
        "error_count": len(errors),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (default: parent of scripts/)",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON output")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    report = verify_audit(args.root)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif report["ok"]:
        counts = report["counts"]
        print(
            "PASS: 4-ATP blank audit verified "
            f"({counts['prepared_blank_records']} prepared records, "
            f"{counts['shared_source_files']} historical source files, "
            f"{counts['family_assessments']} family assessments, "
            "0 confirmed candidates)."
        )
    else:
        print(f"FAIL: {report['error_count']} 4-ATP blank audit error(s):")
        for message in report["errors"]:
            print(f"- {message}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
