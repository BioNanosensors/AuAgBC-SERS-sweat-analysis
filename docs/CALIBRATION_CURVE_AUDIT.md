# Calibration-curve computational lineage and sensitivity audit

## Conclusion

The October 2025 processing chain used to create the preserved Figure 3 and
Figure 4A calibration tables has been recovered. All 210 prepared scan channels
and all four paper-facing calibration tables can be regenerated within the
declared cross-environment numerical tolerances.

That computational result does **not** validate the calibration as a uniform
`750_5_5_L` experiment. The scan-level source mapping shows mixed dates and
settings, exact reuse of source scans under nominally independent prepared
records, and a later-session high-power blank in place of a context-matched
low-power AuAgBC blank. The manuscript's reported `Y0`, `k`, and `R²` values
also are not reproduced by the supplied calibration summary and declared
model.

The defensible interpretation is therefore:

- the preserved spectra and tables have a recoverable computational lineage;
- signals near the three nominal characteristic 4-ATP bands can be retained
  as qualified apparent prepared-series evidence, but not as a validated
  concentration-response trend; and
- quantitative calibration, LOD, LOQ, and calibration-dependent blind-sample
  claims require corrected data or withdrawal.

No historical spectrum or paper-facing table was overwritten.

## Scope

The audit covers:

- 195 nominal 4-ATP sample scans: 13 concentrations × 3 prepared replicates ×
  5 accumulations;
- 15 nominal blank scans: 3 prepared replicates × 5 accumulations;
- the four tables under `data/published_snapshot/calibration_curve/`;
- the three paper parameter rows under
  `data/published_snapshot/paper_tables/calibration_parameters.csv`; and
- the model stated in the manuscript,
  `Y = Y0 × exp(k × log10(C/M))`.

Each prepared scan is bound to its SHA-256 hash, its best matching source file
and source column, the source date and setting, and any exact source-scan reuse
in `metadata/provenance/calibration_scan_lineage.csv`.

## What the scan lineage establishes

All 210 prepared scan intensities have an exact match in the supplied portable
master measurements. This establishes numerical origin, not correctness of
the prepared experimental label or preservation of its Raman axis.

The prepared Raman axes match the selected master source to `1 × 10⁻⁵ cm⁻¹`
for 165 records. Forty-five axes exceed that bound: 35 sample scans and ten
blank scans. The worst maximum absolute axis difference is approximately
`1.26216 cm⁻¹`. All 35 sample-axis conflicts occur within the same 44 sample
records that already conflict in date or setting; they are not an additional
35 independent records. The prepared axes are retained as historical inputs,
while any new source-verified analysis must use and document the source axes.

### Acquisition settings

| Source setting | Samples | Blanks | All records |
| --- | ---: | ---: | ---: |
| `750_5_5_L` | 156 | 0 | 156 |
| `750_5_5_H` | 20 | 15 | 35 |
| `750_5_5_M` | 14 | 0 | 14 |
| `500_5_5_L` | 5 | 0 | 5 |

Only 151 of 195 sample scans agree simultaneously with the intended 3 July
2024 date and `750_5_5_L` setting. In total, 44 sample scans disagree in date,
setting, or both. Eight of the thirteen concentrations are uniform for the
intended date and setting.

The complete source-date counts are:

| Source date | Records |
| --- | ---: |
| 3 July 2024 | 170 |
| 18 September 2024 | 5 |
| 24 September 2024 | 25 |
| 25 September 2024 | 5 |
| 30 September 2024 | 5 |

The 15 prepared blanks are all `750_5_5_H` records from 18, 25, or
30 September. They are not a date- and setting-matched blank for the intended
3 July low-power calibration.

### Statistical independence

The 210 prepared rows represent only 204 distinct exact source-scan identities.
Six source scan identities are each used twice, so 12 prepared rows participate
in exact reuse and six rows are duplicates beyond the distinct-identity count.
The remaining distinct identities are not thereby proven to be independent
experimental observations.

The reuse is structured:

- all five source scans from the second-source `10 µM` replicate are used as
  both prepared replicate 2 and prepared replicate 3; and
- prepared `1nM_rep3_acc1` and `1nM_rep3_acc2` both use the same source scan.

These records must not be counted as independent observations. The exact pairs
are listed in `metadata/provenance/calibration_source_reuse.csv`.

## Recovered historical computation

The recovered October 2025 recipe is recorded in
`configs/reanalysis/calibration_curve_historical_replay.json` and its ordered
210-row input contract is recorded in
`configs/reanalysis/calibration_curve_historical_replay_manifest.csv`.

The forensic generator is
`Scripts/Latest/4-ATP/Raman Portatil/raman_sers_pipeline_merged_spyder_UPDATED2.py`
with SHA-256
`ec6583400df1615d808f07299d6e2e1f8eeb4ae7f7340f796da2c45610443892`.
It is hash-inventoried in `metadata/legacy_script_inventory.csv` but is not
distributed because the historical file contains private absolute paths. The
portable recovered implementation is `scripts/audit_calibration_curve.py`.

The processing sequence is:

1. align all spectra to the common intersection grid using the median native
   median step, then crop below `341.6070517 cm⁻¹`;
2. apply iARPLS with `lambda=3000`, second-difference penalty,
   `tol=0.001`, and `max_iter=50`;
3. select a Butterworth cutoff from the FFT at percentile 60 and apply an
   order-2 low-pass filter;
4. apply a second iARPLS baseline with `lambda=600`;
5. subtract the processed pointwise mean of all 15 historical blank scans from
   every sample scan; and
6. apply ASLS with `lambda=5,000,000`, `p=0.001`, second-difference penalty,
   `tol=0.001`, and `max_iter=50`.

Peak heights are then selected near:

- `392.32 ± 10 cm⁻¹`;
- `1078.50 ± 7 cm⁻¹`; and
- `1589.62 ± 8 cm⁻¹`.

The 210 FFT branch choices are bound to prepared-file hashes in
`metadata/processing_locks/calibration_curve_historical_replay_fft_cutoffs.csv`.
Each lock stores both the selected FFT index and the normalized Butterworth
cutoff. Verification checks the source hash, grid bounds, index, and their
internal consistency, then uses the committed cutoff directly. Whether a fresh
`find_peaks` call rediscovers the same index is reported only as a runtime
diagnostic, so small numerical differences between computers cannot silently
choose—or invalidate—the historical filter branch.

## Numerical replay result

The recovered common grid has 416 Raman-shift points. All 210 processed scan
channels pass the declared cross-environment maximum absolute difference of
`2 × 10⁻⁴`.

| Check | Result |
| --- | ---: |
| Scan channels passing | 210 / 210 |
| Worst scan RMSE | `5.5147 × 10⁻⁵` |
| Worst scan maximum absolute difference | `1.03203 × 10⁻⁴` |
| Aggregate-table checks passing | 6 / 6 |
| Replicate mean/SD maximum absolute difference | `3.53249 × 10⁻⁵` |
| Final wide-table maximum absolute difference | `1.03203 × 10⁻⁴` |
| Summary peak-table maximum absolute difference | `9.0089 × 10⁻⁶` |
| Selected-shift intensity/SD maximum absolute difference | `1.56107 × 10⁻⁵` |

The selected-shift CV comparison has a maximum absolute difference of
`0.0230918` percentage points. CV is a ratio and amplifies very small
cross-environment baseline differences when a mean is near zero; its declared
tolerance is `0.05` percentage points.

Per-channel and per-table evidence is stored in:

- `metadata/validation/calibration_replay_metrics.csv`; and
- `metadata/validation/calibration_table_replay_metrics.csv`.

Passing this replay demonstrates a computational route consistent with the
generation of the preserved tables. It does not make the mixed experimental
inputs scientifically uniform.

## Calibration-model result

The supplied summary was fitted to the manuscript model using deterministic
multi-start nonlinear least squares. Multiple starts are necessary because the
single initializer recovered from the historical script can enter a poorer
local solution for a non-monotonic filtered subset. The audit records the
formal local covariance-based relative standard errors, fitted concentration
range, starting-point diagnostic, and whether an inverted threshold falls
inside that range. These standard errors, convergence flags, and fit-quality
flags describe numerical behaviour of an unweighted fit to nominal
concentration means; they are not experimental uncertainty estimates or
evidence of scientific validity.

Cross-environment verification permits at most `0.02%` relative and
`2 × 10⁻⁴` absolute drift in these numerical fit diagnostics. Scenario
identifiers, record counts, fit-status labels, reporting status, and the
three parameter-reproduction classifications must remain exact.
Only calculated continuous fit, covariance, RSS-ratio, and diagnostic
threshold-inversion columns receive the relative allowance; numeric row keys,
concentration bounds, and manuscript input constants remain exact.

For the complete supplied prepared set and historical mixed blank, the result
is:

| Band (cm⁻¹) | Paper `Y0` | Replayed `Y0` | Paper `k` | Replayed `k` | Paper `R²` | Replayed `R²` |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 392 / 392.32 | 5,700 | 44,751.91 | 0.3 | 0.258371 | 0.92 | 0.825638 |
| 1078 / 1078.50 | 25,000 | 90,704.03 | 0.5 | 0.398770 | 0.99 | 0.926303 |
| 1590 / 1589.62 | 58,000 | 28,845.75 | 0.5 | 0.337789 | 0.98 | 0.885473 |

All three paper rows are classified
`not_reproduced_from_supplied_calibration_summary`. Numerical similarity of an
individual non-reportable diagnostic threshold inversion to a reported LOD or
LOQ does not resolve the parameter mismatch or the blank conflict.

The exact comparison is in
`metadata/validation/calibration_parameter_comparison.csv`.

## Why the LOD and LOQ are not reportable

The manuscript describes thresholds based on blank mean plus three or ten blank
standard deviations. The recovered historical script instead inverted
`3 × SD` and `10 × SD` without adding the blank mean. The audit calculates both
forms so the discrepancy is visible.

Neither form is a valid analytical LOD or LOQ here because:

- the 15 historical blank scans are later-session, high-power records;
- no context-matched `750_5_5_L` AuAgBC blank without 4-ATP was found in the
  supplied measurement collections;
- several sample concentrations use other dates or settings; and
- exact source reuse reduces the number of independent observations.

The 15 values used for the historical blank mean and SD are pooled
scan/accumulation-level peak values from three later exports, not 15
independently prepared blanks: ten trace to `Test HS` exports and five to a
`Test 4-ATP` export. Each five-scan counterfactual uses one such export. The
resulting SD therefore combines within-export scan variability with
between-session/study-context differences and is not an independent blank
preparation estimate.

The response handling is also asymmetric. Calibration samples undergo the
historical blank subtraction before the final ASLS baseline, while the blank
spectra used for threshold statistics are retained without that subtraction
before their final baseline. Inverting either threshold formula is therefore a
literal computational diagnostic on non-equivalent response handling, not a
second valid LOD method.

Every threshold row in
`metadata/validation/calibration_model_sensitivity.csv` is therefore marked
`not_reportable_missing_context_matched_low_power_blank`. Values are retained
only as computational sensitivity diagnostics.

## Sensitivity analyses

The audit evaluates four record selections against the recovered historical
blank operation:

1. all 195 prepared sample records;
2. only the eight concentrations that are completely uniform for the intended
   date and setting;
3. only complete five-scan prepared replicates that are individually uniform
   for the intended date and setting; and
4. one prepared occurrence per unique source scan.

Here, `n_scan_records` counts accumulation-level prepared records and
`n_nominal_prepared_replicate_groups` counts nominal
concentration-by-prepared-replicate groups; neither field claims independent
biological or substrate replicates. Likewise, exact source deduplication only
removes known byte-level reuse.

For all prepared records it also compares:

- no blank subtraction;
- the five scans assigned to historical blank replicate 1 only;
- the five scans assigned to historical blank replicate 2 only; and
- the five scans assigned to historical blank replicate 3 only.

These 24 fits quantify dependence on record selection and the known wrong
blank. None is a replacement calibration. In particular, the no-blank and
five-scan blank variants are counterfactuals, not evidence for a correct blank.
For each five-scan variant, the reported blank mean, SD, and `n_blank_scans`
use that same five-scan subset. The no-subtraction counterfactual has
`n_blank_scans = 0` and leaves its threshold-derived LOD/LOQ fields empty,
because it does not define a blank population.

These selections diagnose separate defects and are not cumulative
corrections. The context-uniform selections can still contain exact source
reuse, including affected `10 uM` and `1 nM` entries, while the unique-source
selection still contains mixed dates and acquisition settings. None is a clean
calibration cohort.

## Disposition of paper-facing claims

| Claim | Audit classification |
| --- | --- |
| The supplied prepared scans generated the preserved Figure 3/4A processed tables | Supportable as computational lineage |
| The calibration is a uniform 3 July `750_5_5_L` experiment | Contradicted by scan lineage |
| Every prepared scan preserves its exact-intensity source Raman axis | Contradicted for 45/210 records |
| Every prepared replicate/accumulation is an independent source scan | Contradicted by exact source reuse |
| LOD/LOQ use a context-matched low-power AuAgBC blank | Unsupported; blank missing |
| The paper's `Y0`, `k`, and `R²` follow from the supplied summary and stated model | Not reproduced |
| Calibration-dependent blind predictions are independently validated quantification | Requires reanalysis |
| The processed series contains responses near the three 4-ATP bands | Supportable with acquisition and independence qualifications |

The machine-readable assessment is
`metadata/validation/calibration_claim_assessment.csv`.

## Required scientific resolution

At least one of the following is required before quantitative calibration,
LOD, LOQ, or calibration-dependent prediction claims are presented as
validated:

1. recover or reacquire a confirmed AuAgBC-without-4-ATP blank at the matching
   low-power setting and document independent blank preparation;
2. identify a genuinely uniform calibration acquisition with independent
   replicates and rebuild the models; or
3. explicitly withdraw the quantitative claims and retain the current data only
   as a qualified historical/qualitative record.

If the paper parameters came from a different data subset or external fitting
project, that exact input table, transformation, weighting, exclusions,
software settings, and output should be deposited before those values are
reinstated.

## Reproduce or verify the audit

Install the pinned release environment described in the repository README.
Then run:

```text
python scripts/audit_calibration_curve.py
python scripts/audit_calibration_curve.py --check
```

The first command regenerates the audit evidence. The second recomputes it and
checks the committed lineage, FFT locks, replay metrics, model sensitivities,
parameter comparison, claim assessment, configuration, and summary.
