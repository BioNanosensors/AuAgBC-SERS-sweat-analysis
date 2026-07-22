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
The fifteen prepared blank files form a mixed-context high-power series: ten
channels exactly match columns stored in two Test HS master exports and five
match columns stored in a Test 4-ATP master export. Storage context is not proof
of sample identity, and none is a confirmed setting-matched low-power blank for
the final calibration. Therefore the prepared raw calibration set is classified
as `provenance_conflict`. This corrects the earlier unsupported all-human
summary; the explicit correction is recorded in
`metadata/provenance_corrections.csv`.

A focused blank audit found a same-date, low-power `BC Blank` file, but the
manuscript and thesis define the analytical blank as AuAgBC without 4-ATP, not
bare bacterial cellulose. It therefore cannot be substituted without evidence
that the material label is wrong. See `docs/4ATP_BLANK_AUDIT.md` and the two
machine-readable tables under `metadata/provenance/`.

The four calibration summary tables are preserved as
`publication_snapshot`. Their values can be aggregated internally, but that
does not resolve the identity of the underlying prepared raw files.

### Blind samples

The prepared set has nine nominal concentrations, three sample files per
concentration, and five scans per file. The master measurements retain coded
sample labels, but the code-to-concentration key was not found. Consequently,
the numerical spectra are recoverable but the nominal concentration assignment
is not independently verifiable. The same identity-unresolved,
setting-mismatched blank series described above was copied into this experiment.

In addition, all 135 prepared nonblank channels match concentration-labelled
24 September low-power measurements, while none matches the original coded
10 September blind experiment. The intended release dataset must be selected
before its correct blank can be established.

### Stability

The folders dated 19 May, 3 July, and 24 September 2024 correspond to elapsed
times of 0, 45, and 128 days. The manuscript calls the final point day 130.
The 19 May folder has 105 concentration disagreements against the best matching
master spectra and contains measurements copied from other dates and settings.
The 3 July and 24 September collections also contain repeated or relabelled
spectra, and the earlier two dates do not provide uniform three-substrate
coverage at every concentration in the master archive. These folders are kept
as `provenance_conflict`, even where the historical processing can be replayed.
No setting- and material-matched AuAgBC blank was found for the intended
low-power stability points. A folder-local high-power AuAgBC candidate could
apply only to a confirmed same-batch high-power subset, not to the mixed day-1
family; its embedded timestamp is after midnight on 20 May.

### Optimisation

The 500 ms low-power and 750 ms high-power processed folders are reproduced
exactly by the recovered stand-alone v2 algorithm when it is run through this
repository's deterministic reader and pipeline. The raw labels still inherit
the duplicate-content issues described above. The 750 ms medium-power folder
contains 43 historical processed files whose stems do not match any raw file in
that folder; these are classified as `orphan_derived`. Modern summary outputs
for the 500 ms low-power and 750 ms medium-power sets are internally
reproducible to CSV rounding.

The only date- and setting-compatible blank candidate with an AuAgBC-like label
found for these three optimisation sets is
`Test 4-ATP/24-09-24/Blank/Blanck_AABC_750_5_5_H.csv` for the high-power set.
It remains provisional until the author confirms that `AABC` means AuAgBC/AAB
and that the substrate contained no 4-ATP. No matched AuAgBC blank was found for
the 500 ms low-power or 750 ms medium-power set.

### Analytical enhancement factor

The prepared AEF summary is preserved, but its intensities near 1590 cm-1 do not
directly reproduce the intensities stated in the manuscript. An acquisition-time
or peak-selection transformation appears to be missing from the historical
record. The reported AEF should not be regenerated until that rule is confirmed.

### Proof of concept

Six portable human-sweat source files contain differences between their outer
filenames and embedded instrument `Name`/`Tag` fields. The author-confirmed
crosswalk resolves these as acquisition-code versus publication-code namespaces,
except for one embedded session value that the author confirmed is a metadata
mistake. Historical source bytes remain unchanged, and the resolutions are
recorded in `metadata/provenance/proof_of_concept_label_evidence.csv`.

Four volunteers were originally tested. The author reports that acquisition
volunteer 1 produced no usable signal and was excluded; acquisition V2/P2,
V3/P3, and V4/P4 were intentionally renumbered as publication V1, V2, and V3.
The three Figure 6 data tables now consistently use publication V1-V3 headers.
Only the two affected headers were changed; every numerical-body byte is
unchanged, with before/after
hashes recorded in
`metadata/provenance/publication_header_corrections.csv`. The upstream inventory
contains pseudonymous path/hash records for acquisition-1 measurement attempts,
but no distributed spectrum is presently evidenced as acquisition V1/P1.

One ten-channel artificial-sweat file repeats channels 1-5 as channels 6-10.

### Human-data governance

The manuscript and thesis report that signed informed consent was obtained from
three volunteers and that no formal institutional ethics approval was obtained
before this proof-of-concept work. A later CFATA/CEID letter states that the
committee reviewed and approved on 25 June 2026, under registration
`CFATA/CEID/002-2026`, a broad protocol that includes non-invasive sweat
spectroscopy; the notification is dated 1 July 2026. It postdates the 2024
acquisitions and does not explicitly address retrospective coverage or public
data sharing.

The author subsequently confirmed that signed forms are retained privately for
all four originally tested volunteers, including excluded acquisition volunteer
1. The author also confirmed that `V` and `P` are operator/date-dependent
prefixes within the same pseudonymous acquisition-code system. The confirmed
code-only crosswalk and publication renumbering are
recorded without exposing the private participant linkage key.

The available consent template permits research use of donated sweat but does
not explicitly permit public repository sharing, open reuse, or disclosure of
exact acquisition timestamps. Signed forms were not included in the records
reviewed but are author-confirmed as retained privately. The scope limitations
of the later approval are detailed in `docs/ETHICS_APPROVAL.md`.

Instrument exports retain pseudonymous volunteer codes and exact dates/times.
The author-confirmed crosswalk resolves the known acquisition/publication label
aliases, but the material is still described as pseudonymised rather than proven
anonymous. See
`docs/HUMAN_DATA_GOVERNANCE.md` and
`metadata/human_data_lineage_summary.json` for the current evidence status and
known downstream lineage. Two byte-identical processed candidates at
dataset-manifest rows 1694 and 1700 are now documented as acquisition- and
publication-namespace aliases for the same deidentified record.

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
2. confirmation of the provisional 24 September high-power blank and the still
   missing or unidentified AuAgBC blanks at `500_5_5_L`, `750_5_5_L`, and
   `750_5_5_M`, as detailed in `4ATP_BLANK_AUDIT.md`;
3. the intended 750 ms low-power calibration file list, especially mixed 500 ms
   records;
4. the day-1 stability manifest and the intended three substrate replicates;
5. the exact intensity extraction and time-scaling used for the reported AEF;
6. complete executable raw-to-publication lineage for every proof-of-concept
   summary trace beyond the confirmed code and label crosswalk; and
7. the intended code and data licences.

Until these are resolved, the honest scientific state is a citable publication
snapshot plus an auditable quarantine—not a claim that every prepared filename
is ground truth.
