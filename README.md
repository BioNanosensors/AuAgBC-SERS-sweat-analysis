# AuAgBC SERS sweat analysis

This repository accompanies *Miniaturised Setup for Surface-Enhanced Raman
Spectroscopy in Sweat Analysis*. It provides one manifest-driven Python workflow
for portable and benchtop Raman CSV files, the processed tables used to assemble
the article, and an explicit provenance audit of the supplied spectra.

> [!IMPORTANT]
> **Public work in progress.** This repository is public to support transparent
> audit, but it is not yet an unqualified data release. Human-sweat measurements
> were reported as collected with signed informed consent and without formal
> prior institutional ethics approval. A later CFATA/CEID approval dated 1 July
> 2026 covers a broad human biofluid-spectroscopy protocol, but it postdates the
> 2024 acquisitions and does not explicitly address retrospective coverage or
> public data sharing. See the
> [human-data governance record](docs/HUMAN_DATA_GOVERNANCE.md) and
> [release checklist](docs/RELEASE_CHECKLIST.md).

## Read this before using the data

The reconstruction found genuine provenance conflicts in the prepared archive:
some spectra are duplicated under different concentrations, ten shared blank
channels exactly match columns stored in Test HS master folders while five
match columns stored in a Test 4-ATP master folder, and parts of the calibration
and May stability sets disagree with the master measurement collections. Folder
context does not prove the blank's sample identity, and none of the channels is
a confirmed setting-matched low-power blank for the final calibration. A
separate 24 September `750_5_5_H` analyte-free AuAgBC blank is now
author-confirmed and distributed only for the matching high-power optimisation;
it is not substituted for low- or medium-power experiments. Nothing in the
historical quarantine was deleted or silently relabelled. Two
publication-summary headers were transparently corrected after author
confirmation, with both source and corrected hashes recorded in provenance.

- `data/published_snapshot/` contains the paper-facing tables.
- `data/raw/` and `data/processed/` contain verified or newly generated material.
- `data/quarantine/legacy_snapshot/` preserves unresolved CSV files with their
  original relative structure.
- `metadata/dataset_manifest.csv` records checksums and status for every
  source-derived dataset file and copied audit report.

See [the data audit](docs/DATA_AUDIT.md) and the focused
[4-ATP blank-file audit](docs/4ATP_BLANK_AUDIT.md) before quantitative reuse. A
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

Verify the release manifests, file checksums, summary counts, and limited
direct-identifier scan without installing any third-party package:

```text
python scripts/verify_repository_data.py
```

Verify the conservative inventory of direct human-sweat records, shared blank
content with unresolved identity, and explicitly recorded downstream
derivatives:

```text
python scripts/report_human_data_lineage.py --check
```

Verify the author-confirmed proof-of-concept code crosswalk, publication
headers, unchanged numerical bodies, and label-provenance sidecars:

```text
python scripts/proof_of_concept_mapping.py --check
```

Verify the machine-readable 4-ATP blank provenance and candidate decisions:

```text
python scripts/verify_4atp_blank_audit.py
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
| `metadata/` | Checksums, origin matches, author-confirmed code crosswalks, conflicts, script inventory, and validation metrics |
| `docs/PAPER_DATA_MAP.md` | Figure/table-to-data map |
| `docs/HUMAN_DATA_GOVERNANCE.md` | Consent, ethics, pseudonymisation, and public-sharing evidence status |
| `docs/ETHICS_APPROVAL.md` | Scope and limitations of the later CFATA/CEID approval letter |
| `docs/4ATP_BLANK_AUDIT.md` | Historical blank origins, experiment-specific candidates, and unresolved decisions |
| `docs/LICENSING.md` | Proposed path-level licensing arrangement and required decisions |
| `docs/RELEASE_CHECKLIST.md` | Items requiring author confirmation before an unqualified public release |
| `tests/` | Synthetic and regression tests |

## Citation and licence status

Citation metadata are provided in `CITATION.cff`. The code and data licences are
pending confirmation by the copyright holders; public access alone does not
grant a reuse licence. See the [licensing decision record](docs/LICENSING.md).
