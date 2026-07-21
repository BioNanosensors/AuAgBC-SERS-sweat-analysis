# Data audit and provenance status

## Why this document exists

This repository was reconstructed from a prepared data archive, 69 historical
Python scripts, two master measurement collections, and the source of the
associated manuscript. The audit found that some prepared files cannot yet be
traced to the measurement described by their filename. Those files are retained
for transparency, but they are not presented as verified raw data.

No source measurement was edited, deleted, or silently relabelled during this
work. Files in `data/quarantine/legacy_snapshot/` preserve the submitted CSV
content and directory structure, except that private absolute computer paths
in four generated tables were replaced by repository-relative data paths.
SHA-256 checksums and the exact
sanitisation status are recorded in `metadata/dataset_manifest.csv`.

## Audit scope

The prepared archive contained 3,046 files: 2,783 CSV files, 261 PNG files, and
2 JSON files. The audit compared its spectrum columns against the two master
measurement collections and inspected all 69 historical processing scripts.

Of 1,456 prepared files classified as raw-like spectra, 1,433 contained at
least one intensity column that could be found in a master measurement file.
This is strong evidence for the numerical origin of the column, but it does not
by itself validate the prepared concentration, date, instrument setting, or
sample identity.

The prepared archive contains 248 duplicate-content groups involving 709 files,
equivalent to 461 redundant copies. In 103 raw-spectrum duplicate groups, the
same bytes occur under filenames that claim different concentrations.

## Status vocabulary

| Status | Meaning |
| --- | --- |
| `verified` | Identity, acquisition context, and processing lineage agree with an independent source. |
| `publication_snapshot` | A table or spectrum preserved because it was used to assemble the manuscript; this does not imply that its complete raw lineage is verified. |
| `regenerated` | Produced by the current pipeline from inputs named in a portable manifest. |
| `legacy_derived` | Produced by an historical script or workflow; retained as evidence. |
| `raw_unverified` | Numerically plausible raw data whose full experimental identity is not yet independently confirmed. |
| `provenance_conflict` | Filename or manifest metadata conflicts with the matching master measurement or with another copy of the same spectrum. |
| `orphan_derived` | A processed file has no same-stem raw input in its stated experiment folder. |
| `sanitized_copy` | Data values are unchanged, but a private absolute path was replaced with a portable path. |

## Findings that prevent an unqualified public release

### Calibration curve

The prepared calibration folder contains 210 single-scan CSV files: thirteen
4-ATP concentrations and a blank, each nominally arranged as three substrate
replicates with five scans. The manuscript identifies the final acquisition as
`750_5_5_L`.

Column-level matching shows that the set is not uniformly from that acquisition.
For example, the prepared `4ATP_1mM_rep3_acc1.csv` matches a 500 ms master
measurement, while other 1 mM files match the 750 ms low-power collection.
The fifteen prepared blank files are also copies of a human-sweat high-power
blank, not a confirmed 4-ATP calibration blank. Therefore the prepared raw
calibration set is classified as `provenance_conflict`.

The four calibration summary tables are preserved as
`publication_snapshot`. Their values can be aggregated internally, but that
does not resolve the identity of the underlying prepared raw files.

### Blind samples

The prepared set has nine nominal concentrations, three sample files per
concentration, and five scans per file. The master measurements retain coded
sample labels, but the code-to-concentration key was not found. Consequently,
the numerical spectra are recoverable but the nominal concentration assignment
is not independently verifiable. The same inappropriate blank described above
was copied into this experiment.

### Stability

The folders dated 19 May, 3 July, and 24 September 2024 correspond to elapsed
times of 0, 45, and 128 days. The manuscript calls the final point day 130.
The 19 May folder has 105 concentration disagreements against the best matching
master spectra and contains measurements copied from other dates and settings.
The 3 July and 24 September collections also contain repeated or relabelled
spectra, and the earlier two dates do not provide uniform three-substrate
coverage at every concentration in the master archive. These folders are kept
as `provenance_conflict`, even where the historical processing can be replayed.

### Optimisation

The 500 ms low-power and 750 ms high-power processed folders are reproduced
exactly by the recovered stand-alone v2 algorithm when it is run through this
repository's deterministic reader and pipeline. The raw labels still inherit
the duplicate-content issues described above. The 750 ms medium-power folder
contains 43 historical processed files whose stems do not match any raw file in
that folder; these are classified as `orphan_derived`. Modern summary outputs
for the 500 ms low-power and 750 ms medium-power sets are internally
reproducible to CSV rounding.

### Analytical enhancement factor

The prepared AEF summary is preserved, but its intensities near 1590 cm-1 do not
directly reproduce the intensities stated in the manuscript. An acquisition-time
or peak-selection transformation appears to be missing from the historical
record. The reported AEF should not be regenerated until that rule is confirmed.

### Proof of concept

Ten portable source files have a mismatch between the outer filename and the
instrument metadata fields (`Name` or `Tag`), shifting volunteer identifiers.
One ten-channel artificial-sweat file repeats channels 1-5 as channels 6-10.
The final manuscript summaries select artificial sweat and volunteers V2-V4;
the raw collection also contains V1/P1-labelled material.

### Hand-held spectrometer calibration

This is the cleanest pair in the archive. The calibrated silicon spectrum keeps
the intensity column unchanged and applies an approximately +0.240026 cm-1
shift to the Raman axis. Both source and calibrated files are retained.

## Processing reproduction

The audit identified several incompatible historical pipelines rather than one
definitive script. A common historical portable workflow was:

1. crop the spectrum;
2. subtract a raw blank;
3. estimate a first iARPLS baseline with a sample-dependent lambda;
4. apply a low-pass Butterworth filter with a cutoff inferred from the FFT;
5. estimate a second iARPLS baseline; and
6. save a two-column spectrum.

The unified package reproduces every paired spectrum in the stability and
500/750-H optimisation folders, including the numerical values as parsed from
CSV:

| Family | Paired spectra | Exact numerical matches | Missing outputs | Extra outputs |
| --- | ---: | ---: | ---: | ---: |
| Stability, 3 July 2024 | 165 | 165 | 0 | 0 |
| Stability, 19 May 2024 | 160 | 160 | 0 | 0 |
| Stability, 24 September 2024 | 210 | 210 | 0 | 0 |
| Optimisation, 500 ms low power | 210 | 210 | 0 | 0 |
| Optimisation, 750 ms high power | 210 | 210 | 0 | 0 |
| **Total** | **955** | **955** | **0** | **0** |

An earlier exploratory audit, retained under `metadata/validation/`, reported
27 apparent material discrepancies. That comparison used a separate
data-frame-based replay. Differences of approximately 1e-12 in parsing or
summation could change which discrete FFT peak was selected as the Butterworth
cutoff and send the historical algorithm down a different branch. A
package-native replay using the same deterministic reader as the released
workflow resolves all 27: 955 of 955 pairs have zero RMSE and zero maximum
absolute difference. The older reports remain as development evidence of this
numerical sensitivity; they are superseded for package-reproduction claims and
must not be interpreted as provenance conflicts.

For blind samples, a different legacy strategy using a single blank reproduces
123 of 135 sample columns at 1e-9 and 130 at 1e-7; five material discrepancies
remain, and the fifteen separately prepared blank outputs are unresolved.

The legacy profiles do not exactly reproduce the calibration, AEF, or
proof-of-concept processed folders. They were made with other historical
variants or missing inputs. The current package therefore exposes named,
explicit profiles and records every parameter instead of guessing silently from
a filename.

See `metadata/validation/package_reproduction_summary.csv` for family counts and
`metadata/validation/package_reproduction_metrics.csv` for all 955 file-level
comparisons. An exact reproduction proves how a prepared derivative was
calculated; it does not prove that the raw file was labelled correctly.

## Information still needed from the laboratory record

Before describing every raw file as verified, the following should be supplied
or confirmed:

1. the blind-sample code-to-concentration key;
2. the correct 4-ATP blank measurements for calibration, blind, optimisation,
   and stability experiments;
3. the intended 750 ms low-power calibration file list, especially mixed 500 ms
   records;
4. the day-1 stability manifest and the intended three substrate replicates;
5. the exact intensity extraction and time-scaling used for the reported AEF;
6. the volunteer filename-to-instrument-metadata mapping; and
7. the intended code and data licences.

Until these are resolved, the honest scientific state is a citable publication
snapshot plus an auditable quarantine—not a claim that every prepared filename
is ground truth.
