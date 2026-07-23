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
| `raw_author_confirmed` | Unchanged raw source whose material/sample identity is author-confirmed and whose acquisition metadata matches one explicitly named condition; it must not be generalized to other conditions. |
| `publication_snapshot` | A table or spectrum preserved because it was used to assemble the manuscript; this does not imply that its complete raw lineage is verified. |
| `regenerated` | Produced by the current pipeline from inputs named in a portable manifest whose provenance supports the stated scope. |
| `regenerated_partial_provenance` | Produced reproducibly by the current pipeline, but at least one named input retains a documented provenance limitation; this is not equivalent to verified. |
| `legacy_derived` | Produced by an historical script or workflow; retained as evidence. |
| `raw_unverified` | Numerically plausible raw data whose full experimental identity is not yet independently confirmed. |
| `provenance_conflict` | Filename or manifest metadata conflicts with the matching master measurement or with another copy of the same spectrum. |
| `orphan_derived` | A processed file has no same-stem raw input in its stated experiment folder. |
| `sanitized_copy` | Data values are unchanged, but a private absolute path was replaced with a portable path. |
| `audit_evidence` | Machine-readable audit or numerical-validation evidence; it is not an experimental spectrum status. |

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
that the material label is wrong. A subsequent collection-wide audit inspected
all 1,623 portable CSV paths (1,263 unique file hashes), found 116 blank-like
paths, and compared 426 unique blank scan signatures against every portable
scan channel. It found no explicitly labelled AuAgBC blank at `500_5_5_L`,
`750_5_5_L`, or `750_5_5_M` and no exact blank-channel copy under a nonblank
identity. Four contextually plausible but mismatched candidates remain
unassigned. See `docs/4ATP_BLANK_AUDIT.md` and the four machine-readable tables
under `metadata/provenance/`.

The calibration lineage is now resolved at source-column level for all 210
prepared scans. The mapping identifies 195 nominal sample scans and 15 nominal
blanks, but only 151 sample scans agree simultaneously with the intended
3 July 2024 date and `750_5_5_L` setting. Forty-four sample scans disagree in
date, setting, or both. The source-setting counts are 156 `750_5_5_L`, 35
`750_5_5_H`, 14 `750_5_5_M`, and five `500_5_5_L`; the 35 high-power records
include all 15 blanks. Only eight of the thirteen concentrations are uniformly
from the intended date and setting.

The 210 prepared rows represent 204 distinct exact source-scan identities.
Twelve rows participate in six exact source-scan reuse groups: all five scans
from one `10 µM` source replicate are reused as two prepared replicates, and
two prepared `1 nM` accumulations use the same source scan. These entries are
not independent observations, and distinct exact identities do not by
themselves establish independence for the remaining records.

Although every prepared intensity vector has an exact source-column match,
45/210 prepared Raman axes differ from the selected source by more than
`1 × 10⁻⁵ cm⁻¹`: 35 sample axes and ten blank axes. The worst maximum absolute
axis difference is approximately `1.26216 cm⁻¹`. The 35 affected samples are a
subset of the 44 date/setting conflicts. This axis evidence is retained
separately from the exact-intensity result.

The October 2025 processing chain has been recovered and replayed without
overwriting the historical snapshot. All 210 processed scan channels pass a
cross-environment maximum-absolute-difference tolerance of `2 × 10⁻⁴`; the
worst observed difference is `1.03203 × 10⁻⁴`. Six aggregate-table checks also
pass their declared tolerances. This establishes computational lineage for the
four calibration tables preserved as `publication_snapshot`.

It does not validate the quantitative model. Fitting the supplied summary to
the manuscript's stated `Y = Y0 × exp(k × log10(C/M))` model does not reproduce
the paper's `Y0`, `k`, or `R²` values for any of the three bands. The recovered
historical script also used `3 × SD` and `10 × SD` thresholds, whereas the
manuscript describes blank mean plus three or ten SD. Neither calculation is a
valid analytical LOD or LOQ because the required context-matched low-power
AuAgBC blank is absent. Calibration-dependent blind predictions therefore
remain historical results requiring reanalysis, not independently validated
quantification.

The full source mapping, recovered recipe, numerical bounds, model
sensitivities, parameter comparison, and claim classifications are documented
in [the calibration-curve audit](CALIBRATION_CURVE_AUDIT.md). The four
paper-facing tables remain `publication_snapshot`; the new lineage and replay
files are `audit_evidence`.

### Blind samples

The prepared set has nine nominal concentrations, three sample files per
concentration, and five scans per file. All 135 nonblank channels match
concentration-labelled 24 September `750_5_5_L` master measurements, with every
prepared concentration agreeing with its match. None matches the original coded
10 September blind experiment. On 22 July 2026, the author selected the current
24 September concentration-labelled snapshot for release rather than the coded
10 September collection. The unavailable decoding key is therefore not needed
for this selected release scope, although it would still be required to release
or substantiate the historical coded experiment.

The same setting-mismatched historical blank composite described above was
copied into the prepared Blind folder. The author-confirmed 24 September AuAgBC
blank is high power and therefore is not a valid blank for the selected
low-power Blind snapshot.

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
repository's deterministic reader and pipeline. Their raw labels still inherit
the duplicate-content issues described above.

The 750 ms medium-power prepared folder contains 210 split spectra, whereas its
historical processed directory contains 43 multi-column AAB, BC, and blank
files with different names and 225 total intensity channels. The earlier
same-stem audit correctly found no pairs inside the prepared folder, but its
conclusion that no computational lineage could be recovered was too broad. An
explicit mapping to 42 vendor exports and one assembled 15-channel blank now
reproduces all 43 historical files. Every Raman-shift array is equal after
numerical parsing; all 225 intensity channels pass `RMSE <= 1e-7` and maximum
absolute difference `<= 1e-6`.

This is a computational-lineage result, not experimental validation. The
recovered workflow subtracts the first channel of the assembled historical
blank from all 210 nonblank channels. That assembled file is the mixed
high-power composite traced elsewhere in this audit, not a setting-matched
`750_5_5_M` AuAgBC blank. The source vendor exports remain `raw_unverified`,
the assembled blank and preserved 43 outputs remain `provenance_conflict`, and
the replay package is `audit_evidence`. See
[the medium-power computational-lineage replay record](4ATP_MEDIUM_POWER_COMPUTATIONAL_REPLAY.md).

Modern summary outputs for the 500 ms low-power and 750 ms medium-power sets
remain internally reproducible to CSV rounding, but summary reproducibility
does not establish a verified raw-to-publication lineage.

The date- and setting-compatible high-power blank found for these optimisation
sets is
`Test 4-ATP/24-09-24/Blank/Blanck_AABC_750_5_5_H.csv` for the high-power set.
The author confirmed on 22 July 2026 that `AABC` means AuAgBC/AAB and that this
file is an AuAgBC substrate without 4-ATP. It is now the confirmed blank for the
matching 24 September `750_5_5_H` optimisation condition and is distributed
unchanged under `data/raw/`. No matched AuAgBC blank was found for the 500 ms
low-power or 750 ms medium-power set. The supplied portable collection has now
been exhausted for these settings; resolution requires new laboratory evidence,
a newly supplied source file, or withdrawal and reanalysis of the affected
claim.

Recovery of the medium-power computation does not change the blank search
result. No matched AuAgBC blank was found for the 500 ms low-power or 750 ms
medium-power set. A corrected medium-power reanalysis therefore still requires
new laboratory evidence, a newly supplied source file, a repeat experiment, or
a scientifically documented withdrawal or qualification of the affected
claim. No `reference_2026` medium-power package is published.

The high-power condition now has three strictly separate lineages:

1. the preserved historical snapshot, generated with the mixed 15-spectrum
   composite and retained as historical-lineage evidence;
2. a controlled `legacy_individual` rerun using the one confirmed five-channel
   blank, which holds the historical algorithm fixed and isolates the
   blank-only effect; and
3. a `reference_2026` reanalysis using the confirmed blank but changing the
   grid, crop, baseline/filter settings, blank-subtraction stage, and post-blank
   baseline, which measures a wider workflow effect.

The 195 prepared sample spectra match vendor-export intensities, but their
prepared Raman axes differ from the 39 vendor originals by approximately
0.39937 cm⁻¹. They remain `raw_unverified`; both new output lineages are
therefore `regenerated_partial_provenance`. The confirmed blank is one export
with five technical scans, not independent blank substrates.

The checked numerical audit shows a smaller blank-only change than the full
workflow change. RMSE is reported in processed-intensity units; NRMSE is RMSE
divided by the left-lineage intensity range and multiplied by 100. At scan
level, the median RMSE, Pearson `r`, and NRMSE are
369.74, 0.98988, and 3.444% for historical → controlled legacy, compared with
2086.82, 0.51231, and 21.743% for controlled legacy → `reference_2026`. At
concentration level, the corresponding median values are 340.41, 0.99902, and
2.073% for the blank-only comparison, while the workflow comparison has median
RMSE 4106.09, `r = 0.18751`, and NRMSE 24.698%. Full-precision values and the regenerated check
are documented in [the high-power reanalysis record](4ATP_HIGH_POWER_REANALYSIS.md).

The reference result is not automatically more accurate or scientifically
preferred. Neither new lineage overwrites the paper-facing historical data.

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

On the canonical generation computer, the unified package reproduced every
paired spectrum in the stability and 500/750-H optimisation folders, including
the numerical values as parsed from CSV:

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
package-native replay using the same reader as the released workflow resolves
all 27 on the canonical computer: 955 of 955 pairs have zero RMSE and zero
maximum absolute difference. The automatic legacy cutoff rule itself is not
cross-hardware deterministic when a percentile falls exactly between two FFT
peak magnitudes. The high-power audited release therefore uses the explicit,
source-hash-bound 610-row cutoff lock in
`metadata/processing_locks/optimisation_750_5_5_h_fft_cutoffs.csv`; its replay
does not rerun that ambiguous selection. The other legacy-family results remain
numerical-archaeology evidence from the canonical run, not a claim of
bit-identical behavior on every CPU. The older reports remain as development
evidence of this sensitivity and must not be interpreted as provenance
conflicts.

The locked cutoff also exposed much smaller reference-only differences on the
GitHub Windows runner, consistent with variation in the iterative baseline
solver: 171 of 88,200 scan points differed beyond the generic bound, with a
worst absolute delta of `0.000140786` intensity units. The release checker
applies a documented `2e-4`
absolute bound only to reference intensity and directly propagated difference
fields, plus a `1e-4` relative bound to CV near zero. Axes, identities, schemas,
labels, and cutoff-lock fields remain strict. See
[`4ATP_HIGH_POWER_REANALYSIS.md`](4ATP_HIGH_POWER_REANALYSIS.md) for the measured
contract and public CI evidence.

For blind samples, a different legacy strategy using a single blank reproduces
123 of 135 sample columns at 1e-9 and 130 at 1e-7; five material discrepancies
remain, and the fifteen separately prepared blank outputs are unresolved.

The generic legacy profiles do not exactly reproduce the AEF or
proof-of-concept processed folders. They were made with other historical
variants or missing inputs. The calibration is now handled by its separate
recovered October 2025 replay: all 210 scan channels and six aggregate-table
checks pass declared cross-environment tolerances, but the mixed acquisition
contexts, source reuse, missing low-power blank, and non-reproduced paper model
parameters remain scientific conflicts. The current package therefore exposes
named, explicit profiles and records every parameter instead of guessing
silently from a filename.

See `metadata/validation/package_reproduction_summary.csv` for family counts and
`metadata/validation/package_reproduction_metrics.csv` for all 955 file-level
comparisons. An exact reproduction demonstrates a computational route
consistent with a prepared derivative; it does not prove that the raw file was
labelled correctly.

### High-power 4-ATP controlled and reference packages

The reproducible high-power reanalyses are distributed separately under
`data/processed/4atp/optimisation/750_5_5_H/` as
`controlled_legacy_confirmed_blank/`, `reference_2026/`, and `comparison/`.
Large scan-level tables use compressed `.csv.gz` files and the 200 individual
two-column spectra in each lineage use a deterministic ZIP archive; compact
summaries, peak tables, and comparison records remain directly readable.

Run or verify them with:

```text
python scripts/reprocess_4atp_750_5_5_h.py
python scripts/reprocess_4atp_750_5_5_h.py --check
```

The new manifests use the correct equivalence `0.0001 M = 100 µM`. The
paper-facing optimisation snapshot contains `100 mM` at that header position;
the typo remains unchanged there to preserve historical bytes and is not
propagated into regenerated data.

## Information still needed from the laboratory record

Before describing every raw file as verified, the following should be supplied
or confirmed:

1. the blind-sample code-to-concentration key only if the historical 10 September
   coded experiment is to be released or used to substantiate the original
   blinded-validation lineage;
2. external laboratory evidence or a newly supplied source file for the still
   missing or unidentified AuAgBC blanks at `500_5_5_L`, `750_5_5_L`, and
   `750_5_5_M`, or a decision to withdraw and reanalyse the affected claims, as
   detailed in `4ATP_BLANK_AUDIT.md`;
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
