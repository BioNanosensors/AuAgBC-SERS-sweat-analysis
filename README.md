# AuAgBC SERS sweat analysis

This repository accompanies *Miniaturised Setup for Surface-Enhanced Raman
Spectroscopy in Sweat Analysis*. It provides one manifest-driven Python workflow
for portable and benchtop Raman CSV files, the processed tables used to assemble
the article, and an explicit provenance audit of the supplied spectra.

## Read this before using the data

The reconstruction found genuine provenance conflicts in the prepared archive:
some spectra are duplicated under different concentrations, the shared blank is
traceable to a human-sweat measurement rather than a confirmed 4-ATP blank, and
parts of the calibration and May stability sets disagree with the master
measurement collections. Nothing was silently deleted or relabelled.

- `data/published_snapshot/` contains the paper-facing tables.
- `data/raw/` and `data/processed/` contain verified or newly generated material.
- `data/quarantine/legacy_snapshot/` preserves unresolved CSV files with their
  original relative structure.
- `metadata/dataset_manifest.csv` records checksums and status for every
  source-derived dataset file and copied audit report.

See [the data audit](docs/DATA_AUDIT.md) before quantitative reuse. A
`publication_snapshot` label means “used in preparation of the manuscript,” not
“complete raw lineage independently verified.”

## Install

Python 3.10 or newer is required.

```text
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

On macOS or Linux, activate the environment with
`source .venv/bin/activate`.

## One processing interface

Inspect any supported CSV without changing it:

```text
python process_raman.py inspect "path/to/spectrum.csv"
```

Process a portable CSV/JSON configuration:

```text
python process_raman.py process configs/reference_example.json
```

Or process a CSV manifest directly:

```text
python process_raman.py process configs/example_manifest.csv --input-root . --output outputs/reference_run --profile reference_2026
```

Verify that an output directory still matches its recorded inputs and products:

```text
python process_raman.py verify outputs/reference_run/run.json
```

Verify the release manifests, file checksums, summary counts, and privacy scan
without installing any third-party package:

```text
python scripts/verify_repository_data.py
```

The archive-wide manifest at `metadata/raw_processing_manifest.csv` includes
quarantined records so that every submitted raw-like file is discoverable. It
spans experiments that require different blank and normalisation rules, so
filter it by `record_group` and select an appropriate profile before processing.
A technically consistent derivative does **not** resolve or certify rows marked
`provenance_conflict`.

Regenerate the five audited legacy families, then compare them with the
preserved processed snapshot:

```text
python scripts/reproduce_legacy_families.py
python scripts/validate_legacy_reproduction.py
```

## Supported input structures

The importer reads all numerical intensity columns rather than silently keeping
the first one. It supports:

- Hamamatsu hand-held exports with instrument metadata followed by a 512-point
  Raman table and multiple intensity columns;
- split two-column hand-held spectra;
- benchtop exports with a Raman-shift column and one or more intensity columns;
- comma-, semicolon-, or tab-delimited text, including decimal-comma files when
  the delimiter is not a comma.

Scientific identity is supplied by a manifest. Concentration, volunteer,
replicate, instrument, and acquisition setting are never guessed from numerical
similarity.

## Processing profiles

- `reference_2026`: the explicit, current reference workflow. It aligns spectra
  within experiment/instrument groups, processes individual scans before any
  averaging, applies configured baseline/filter/blank steps, and records all
  resolved parameters.
- `legacy_individual`: the portable v2 chain recovered from the historical
  scripts and used for numerical archaeology.
- `legacy_sg2`, `legacy_sg3`, and `spyder_tuned`: named historical variants kept
  so their assumptions cannot be confused with the reference workflow.

The manuscript does not contain enough numerical processing parameters to claim
that `reference_2026` exactly regenerates every historical derivative. The
separate `legacy_individual` profile does reproduce all 955 paired spectra in
the five audited stability and optimisation families exactly. Results are in
`metadata/validation/package_reproduction_summary.csv`, with one row per file
in `metadata/validation/package_reproduction_metrics.csv`, and are interpreted
in the [data audit](docs/DATA_AUDIT.md).

## Repository map

| Path | Contents |
| --- | --- |
| `process_raman.py` | Single user-facing entry point |
| `src/auagbc_sers/` | Import, processing, manifest, export, and verification code |
| `configs/` | Portable run examples with explicit parameters |
| `data/published_snapshot/` | Article-facing summary data and manuscript values |
| `data/quarantine/legacy_snapshot/` | Submitted CSV snapshot with unresolved provenance clearly isolated |
| `metadata/` | Checksums, origin matches, conflicts, script inventory, and validation metrics |
| `docs/PAPER_DATA_MAP.md` | Figure/table-to-data map |
| `docs/RELEASE_CHECKLIST.md` | Items requiring author confirmation before an unqualified public release |
| `tests/` | Synthetic and regression tests |

## Citation and licence status

Citation metadata are provided in `CITATION.cff`. The code and data licences are
pending confirmation by the copyright holders; public access alone does not
grant a reuse licence. See the release checklist for suggested options.
