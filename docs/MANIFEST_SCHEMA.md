# Manifest and configuration reference

## Why a manifest is required

A spectrum can be numerically identical after being copied to a misleading
filename. Therefore the processor reads numerical structure from the file, but
it obtains sample identity only from an explicit CSV manifest. Unknown columns
are preserved in every output and in `run.json`.

## Required manifest columns

| Column | Meaning |
| --- | --- |
| `file` | Portable path relative to the configured `input_root`; absolute paths and `..` escapes are rejected. |
| `sample_type` | Declared type such as `blank`, `4atp`, `artificial_sweat`, or `human_sweat`. |
| `concentration_molar` | Numerical concentration in mol L-1, or an empty cell when not applicable/unknown. |
| `replicate` | Independent substrate/disc identifier. Use the literal `unresolved` when the laboratory identity is not known; do not invent a number. |
| `accumulation` | Scan/accumulation identifier. For a row that deliberately expands a multi-intensity file, `expanded_column` is an acceptable explicit value. |
| `instrument` | Stable instrument identifier, for example `portable_785nm` or `benchtop_638nm`; use `unresolved` if not confirmed. |
| `acquisition` | Effective acquisition time or another explicit acquisition descriptor. The column must exist; it may be empty unless acquisition scaling is enabled. |

Aliases accepted for compatibility are `type` for `sample_type`,
`concentration_M` for `concentration_molar`, and `scan` for `accumulation`.

## Strongly recommended columns

| Column | Purpose |
| --- | --- |
| `record_group` | Experiment/timepoint boundary used to prevent blanks or averages from crossing between calibration, optimisation, stability, and sweat studies. |
| `spectrum_id` | Stable human-readable identifier. If absent, the program creates a technical ID from the manifest row and intensity column. |
| `intensity_column` | Optional exact header or one-based numeric intensity-column index. If empty, every usable intensity column is expanded. |
| `analyte` | Chemical analyte, such as `4-ATP`. |
| `matrix` | Water, artificial sweat, human sweat, or another matrix. |
| `concentration_label` | Display label such as `100 fM`; the numerical molar field remains authoritative for calculation. |
| `timepoint` | Storage time/date label. |
| `acquisition_setting` | Human-readable setting such as `750_5_5_L`. |
| `baseline_lambda` | Per-record first-baseline override when an explicit historical value is needed. |
| `provenance_status` | One of the audit statuses defined in `DATA_AUDIT.md`. This status is preserved, not interpreted as permission to aggregate. |

If the same file is listed more than once, every row must provide an
`intensity_column`; otherwise a repeated row would duplicate data and the run is
rejected.

## Job configuration

YAML and JSON jobs use schema version `1.0`. All paths are resolved relative to
the configuration file, so the repository can be moved without editing private
computer paths.

```json
{
  "schema_version": "1.0",
  "profile": "reference_2026",
  "manifest": "example_manifest.csv",
  "input_root": "..",
  "output_root": "../outputs/reference_example",
  "options": {
    "blank": {
      "stage": "processed",
      "strategy": "mean",
      "group_by": ["record_group", "instrument"],
      "sample_types": ["blank"]
    },
    "aggregation": {
      "group_by": ["record_group"]
    }
  }
}
```

`options` recursively overrides the named profile and is recorded verbatim in
the provenance. Blank strategies are `mean`, `median`, or deterministic `first`.
Blank stages are `raw`, `processed`, or `none`. If subtraction is enabled and a
sample has no manifest-declared blank in its group, processing stops instead of
borrowing one from another experiment.

## Output contract

Every successful run writes:

- one CSV per processed spectrum in `processed_spectra/`;
- long-form scan, replicate, and concentration spectra;
- scan-, replicate-, and concentration-level peak tables;
- `resolved_manifest.csv` with source and processed-file checksums;
- `processing_report.csv` with warnings and resolved parameters;
- preserved source metadata in `source_metadata.json`;
- `provenance_files.csv`; and
- `run.json`, the machine-readable configuration and checksum record.

`python process_raman.py verify <run.json>` recalculates recorded hashes and
returns a non-zero status if an input or output has changed.
