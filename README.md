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
it is not substituted for low- or medium-power experiments. An expanded
23 July 2026 search of all 1,623 portable CSV paths found no explicitly labelled
AuAgBC blank at `500_5_5_L`, `750_5_5_L`, or `750_5_5_M`; the collection counts
and four rejected contextual candidates are recorded as machine-readable audit
evidence. Nothing in the historical quarantine was deleted or silently
relabelled. Two
publication-summary headers were transparently corrected after author
confirmation, with both source and corrected hashes recorded in provenance.

- `data/published_snapshot/` contains the paper-facing tables.
- `data/raw/` contains preserved raw-like inputs with explicit statuses ranging
  from author-confirmed to unresolved; `data/processed/` contains regenerated
  derivatives, retained legacy products, and audit evidence, each separately
  classified in the manifest.
- `data/quarantine/legacy_snapshot/` preserves unresolved CSV files with their
  original relative structure.
- `metadata/dataset_manifest.csv` records checksums and status for every
  source-derived dataset file and copied audit report.

See [the data audit](docs/DATA_AUDIT.md) and the focused
[4-ATP blank-file audit](docs/4ATP_BLANK_AUDIT.md) before quantitative reuse. A
`publication_snapshot` label means “used in preparation of the manuscript,” not
“complete raw lineage independently verified.”

For the Figure 3/4A calibration, read the dedicated
[computational-lineage and sensitivity audit](docs/CALIBRATION_CURVE_AUDIT.md).
The recovered October 2025 chain regenerates all 210 processed scan channels
and all four paper-facing tables within declared cross-environment tolerances.
This is a computational result, not validation of the experiment: 44 of 195
sample scans conflict with the intended date or setting, 45 of 210 prepared
axes differ from their exact-intensity source match beyond `1 × 10⁻⁵ cm⁻¹`, 12
prepared rows participate in exact source-scan reuse, all 15 blanks are later
high-power records, and none of the paper's three `Y0`/`k`/`R²` rows is
reproduced from the supplied calibration summary. Quantitative calibration,
LOD/LOQ, and dependent blind-prediction claims therefore remain unresolved.

For the high-power `750_5_5_H` optimisation, also read the dedicated
[reanalysis record](docs/4ATP_HIGH_POWER_REANALYSIS.md). It keeps three lineages
strictly separate: the historical snapshot made with a mixed 15-spectrum blank
composite, a controlled `legacy_individual` rerun that changes only to the
author-confirmed five-channel blank, and a `reference_2026` reanalysis that also
changes the workflow. The 195 sample spectra in both new runs remain
`raw_unverified`; their intensities match the vendor exports, but their prepared
Raman axes differ from the corresponding vendor axes by approximately
0.39937 cm⁻¹.

For the medium-power `750_5_5_M` optimisation, read the separate
[computational-lineage replay record](docs/4ATP_MEDIUM_POWER_COMPUTATIONAL_REPLAY.md).
An explicit mapping from 42 unchanged vendor exports and one assembled
15-channel blank numerically reproduces all 43 preserved historical files and
all 225 channels within machine-scale bounds. This establishes computation
only. The historical workflow subtracts the first channel of a mixed
high-power assembled blank, not a confirmed medium-power AuAgBC blank, so the
preserved outputs remain `provenance_conflict` and the replay package is
classified as `audit_evidence`.

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

Regenerate or verify the Figure 3/4A calibration computational-lineage and
sensitivity audit:

```text
python scripts/audit_calibration_curve.py
python scripts/audit_calibration_curve.py --check
```

The calibration check binds every prepared scan to its source column and hash,
replays the recovered processing with locked FFT decisions, compares all
paper-facing tables, and verifies that every diagnostic LOD/LOQ remains marked
non-reportable in the absence of a context-matched low-power blank.

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

Persistent generation uses Windows x64 with Python 3.12.13. The high-power
verifier accepts Python 3.12.10 or 3.12.13 because 3.12.10 is the latest
official Windows binary available to GitHub Actions for this series. All
release modes use the exact direct-package constraints in
`requirements-release.txt` and refuse undeclared platforms or package
environments.

```text
python -m pip install -e ".[test]" -c requirements-release.txt
```

The separate Python 3.10 compatibility lane uses the mature patch releases in
`requirements-compatibility.txt`. It runs the complete test suite, repository
verification, and calibration replay on Linux. This is the oldest tested patch
stack, not a claim that every earlier patch in the declared dependency series
was independently tested.

Then regenerate the two separately labelled high-power 4-ATP reanalyses and
their comparison package, or verify the committed compact products:

```text
python scripts/reprocess_4atp_750_5_5_h.py
python scripts/reprocess_4atp_750_5_5_h.py --check
```

Regenerate or verify the computation-only medium-power historical replay:

```text
python scripts/replay_4atp_750_5_5_m.py
python scripts/replay_4atp_750_5_5_m.py --check
python scripts/replay_4atp_750_5_5_m.py --cross-environment-check
```

The medium-power exact check requires canonical regenerated package bytes. Its
separate cross-environment check exact-hash-verifies the committed package,
schemas, mappings, axes, and source-bound FFT decisions, then requires all 43
files and 225 freshly replayed channels to pass the declared numerical bounds.
It makes no regenerated byte-identity claim. Neither mode validates the mixed
high-power historical blank for `750_5_5_M`.

This high-power release uses the auditable 610-row cutoff lock in
`metadata/processing_locks/optimisation_750_5_5_h_fft_cutoffs.csv`. It binds
each canonical FFT peak index to its exact source hash, intensity selector, and
processing contract, so a midpoint tie cannot send another CPU down a different
Butterworth branch. The resolved index remains visible in the generated
manifests and processing reports.

The cross-platform check uses narrow, lineage-scoped numerical bounds for the
reference workflow's iterative numerical steps while keeping axes, identities,
schemas, labels, and lock fields strict. The measured rationale and exact
contracts are documented in
[the high-power reanalysis note](docs/4ATP_HIGH_POWER_REANALYSIS.md).

The release products are under
`data/processed/4atp/optimisation/750_5_5_H/`. Large scan-level and
per-spectrum tables are compressed as `.csv.gz` and deterministic ZIP archives;
smaller summaries and audit tables remain directly readable. The 24 files in
the two lineage packages have `regenerated_partial_provenance` status because
reproducible processing does not resolve the sample-input axis and label limits;
the six comparison files are separately labelled `audit_evidence`.

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
  scripts and used for numerical archaeology. Its original `np.argmin` tie
  behavior is retained for fidelity; audited high-power release runs use the
  explicit per-record cutoff lock instead.
- `legacy_sg2`, `legacy_sg3`, and `spyder_tuned`: named historical variants kept
  so their assumptions cannot be confused with the reference workflow.

The manuscript does not contain enough numerical processing parameters to claim
that `reference_2026` exactly regenerates every historical derivative. The
separate `legacy_individual` profile does reproduce all 955 paired spectra in
the five audited stability and optimisation families exactly. Results are in
`metadata/validation/package_reproduction_summary.csv`, with one row per file
in `metadata/validation/package_reproduction_metrics.csv`, and are interpreted
in the [data audit](docs/DATA_AUDIT.md).

For `750_5_5_H`, the controlled legacy rerun is the only comparison that
isolates the blank-only effect. `reference_2026` changes the grid, crop,
baseline/filter parameters, blank-subtraction stage, and post-blank baseline;
its difference is a workflow effect. It is a transparent modern reanalysis,
not an automatically more accurate or preferred result, and it requires
scientific review before quantitative interpretation.

## Repository map

| Path | Contents |
| --- | --- |
| `process_raman.py` | Single user-facing entry point |
| `src/auagbc_sers/` | Import, processing, manifest, export, and verification code |
| `configs/` | Portable run examples with explicit parameters |
| `data/published_snapshot/` | Article-facing summary data and manuscript values |
| `data/processed/4atp/optimisation/750_5_5_H/` | Separately labelled controlled-legacy, `reference_2026`, and comparison packages |
| `data/quarantine/computational_lineage_sources/4atp/optimisation/750_5_5_M/` | Unchanged vendor exports and the conflicting assembled blank retained for historical computation replay |
| `data/processed/4atp/optimisation/750_5_5_M/historical_computational_replay/` | Computation-only replay package and per-channel validation evidence |
| `data/quarantine/legacy_snapshot/` | Submitted CSV snapshot with unresolved provenance clearly isolated |
| `metadata/` | Checksums, origin matches, author-confirmed code crosswalks, conflicts, script inventory, and validation metrics |
| `docs/PAPER_DATA_MAP.md` | Figure/table-to-data map |
| `docs/HUMAN_DATA_GOVERNANCE.md` | Consent, ethics, pseudonymisation, and public-sharing evidence status |
| `docs/ETHICS_APPROVAL.md` | Scope and limitations of the later CFATA/CEID approval letter |
| `docs/4ATP_BLANK_AUDIT.md` | Historical blank origins, experiment-specific candidates, and unresolved decisions |
| `docs/CALIBRATION_CURVE_AUDIT.md` | Figure 3/4A scan lineage, recovered computation, fit comparison, and claim limits |
| `docs/4ATP_HIGH_POWER_REANALYSIS.md` | Three-lineage high-power reanalysis design, results, and interpretation limits |
| `docs/4ATP_MEDIUM_POWER_COMPUTATIONAL_REPLAY.md` | Medium-power source mapping, recovered algorithm, numerical bounds, and unresolved blank limitation |
| `docs/LICENSING.md` | Proposed path-level licensing arrangement and required decisions |
| `docs/RELEASE_CHECKLIST.md` | Items requiring author confirmation before an unqualified public release |
| `tests/` | Synthetic and regression tests |

## Citation and licence status

Citation metadata are provided in `CITATION.cff`. The code and data licences are
pending confirmation by the copyright holders; public access alone does not
grant a reuse licence. See the [licensing decision record](docs/LICENSING.md).
