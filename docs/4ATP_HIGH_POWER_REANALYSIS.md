# High-power 4-ATP reanalysis

## Scope

This record concerns only the portable-Raman 4-ATP optimisation acquired at
`750_5_5_H` on 24 September 2024. It documents a new, setting-matched blank and
two deliberately separate reanalyses. It does not change the paper-facing
historical data, and it does not supply a blank for any low- or medium-power
experiment.

The central rule is that three lineages must not be merged or described as if
they answered the same question:

| Lineage | Blank and processing | Question answered | Location |
| --- | --- | --- | --- |
| Preserved historical snapshot | Mixed 15-spectrum composite and the recovered historical `legacy_individual` chain | What inputs and algorithm generated the supplied historical derivatives? | `data/quarantine/legacy_snapshot/Optimisation/750_5_5_H/` and the paper-facing summary in `data/published_snapshot/optimisation/4atp_750_5_5_h.csv` |
| Controlled legacy rerun | One author-confirmed, five-channel blank; otherwise the same `legacy_individual` chain | How much does changing only the blank alter the historical sample results? | `data/processed/4atp/optimisation/750_5_5_H/controlled_legacy_confirmed_blank/` |
| `reference_2026` reanalysis | The same confirmed blank and sample selection, but the current reference workflow | How much does the complete current workflow alter the controlled-legacy results? | `data/processed/4atp/optimisation/750_5_5_H/reference_2026/` |

The corresponding pairwise audit tables are in
`data/processed/4atp/optimisation/750_5_5_H/comparison/`.

Neither new lineage overwrites, replaces, or silently revises the historical
snapshot or the paper-facing optimisation table.

## Input evidence and its limits

The confirmed blank is the unchanged export
`data/raw/4atp/optimisation/750_5_5_H/Blanck_AABC_750_5_5_H.csv`, with SHA-256
`e36f0ad7a57ebab8cba038309284305cfecc98d1586499fe73e266e301257dd9`.
The author confirmed that `AABC` denotes the same AuAgBC/AAB material and that
the substrate contained no 4-ATP. Its date and nominal settings match this
high-power experiment.

The file is **one physical export with five technical scan channels**. Those
channels improve estimation of the blank spectrum, but they are not five
substrates and are not evidence for three independently prepared blank
replicates.

The 195 prepared sample spectra represent 13 concentrations, three substrate
replicates, and five technical scans per substrate. Their intensity values
match columns in the 39 corresponding vendor exports. Their prepared Raman axes,
however, differ from the vendor-export axes by approximately 0.39937 cm⁻¹.
Consequently, these sample inputs remain `raw_unverified`; intensity matching
does not independently verify every prepared axis or experimental label.

Outputs from either new lineage therefore carry the status
`regenerated_partial_provenance`: they are reproducibly regenerated from named
inputs, but the sample-input provenance limitation remains. The status is not a
synonym for `verified`.

## Why both reruns are necessary

The controlled legacy rerun changes only the blank selection. It retains the
historical native grid, raw mean-blank subtraction, first iARPLS baseline,
order-3 FFT-selected Butterworth filter, second iARPLS baseline, and lack of
normalization. The manifest records the historical first-baseline values
explicitly as 3000 for samples and 8000 for blank channels, avoiding reliance
on the misspelled source name `Blanck`. Comparing it with the preserved
historical sample spectra isolates the **blank-only effect**.

The `reference_2026` profile changes several operations at once: it uses an
increasing intersection grid and a crop starting near 341.607 cm⁻¹, applies
fixed current baseline parameters, uses an order-2 FFT-selected filter with
different percentiles, subtracts the processed mean blank, and applies an
additional post-blank AsLS baseline. Comparing `reference_2026` with the
controlled legacy rerun therefore measures a **workflow effect**, not a second
blank-only effect.

The historical-to-`reference_2026` difference combines both effects and must
not be attributed solely to the confirmed blank.

## Reproduce and verify

The persistent release is generated and exactly checked only in the canonical
environment: Windows x64, Python 3.12.13, and the exact direct-package
constraints in `requirements-release.txt`. From the repository root, install
it first:

```text
python -m pip install -e ".[test]" -c requirements-release.txt
```

The generator and exact check refuse a different operating system, machine
architecture, Python, or direct-package version. This restriction is necessary
because the FFT cutoff branch is sensitive to platform-level numerical
differences. Regenerate the two lineages and their compact audit packages with:

```text
python scripts/reprocess_4atp_750_5_5_h.py
```

Verify that the committed manifests and compact products match a fresh run
without replacing them with:

```text
python scripts/reprocess_4atp_750_5_5_h.py --check
```

Package metadata records the pinned direct-package versions, the constraints-
file hash, and SHA-256 identities for the generator and all `auagbc_sers`
modules used. Both regeneration and `--check` freshly replay the historical
mixed-composite run and require all 210 preserved spectra to agree within an
absolute tolerance of `1e-9`; this keeps the “blank-only” comparison
self-checking as the code evolves.

The release directories contain compact machine-readable summaries. The full
long-form scan table is stored as `spectra_scan.csv.gz`, while the 200 individual
two-column spectra are members of `processed_spectra.zip`. Smaller
concentration, peak, comparison, and provenance tables remain ordinary CSV or
JSON so that they can be inspected directly. Both compression formats are
deterministic and change storage size, not numerical content.

## Checked numerical audit results

The following values come from the regenerated and checked package. RMSE is in
processed-intensity units. NRMSE is `RMSE / (maximum − minimum)` of the left-hand
lineage, multiplied by 100. Full-precision values are in
`comparison/comparison_summary.json` and the associated CSV tables.

| Comparison and level | Median RMSE | Median Pearson `r` | Median NRMSE |
| --- | ---: | ---: | ---: |
| Historical → controlled legacy, 195 sample scans: blank-only effect | 369.74 | 0.98988 | 3.444% |
| Historical → controlled legacy, 13 concentration means: blank-only effect | 340.41 | 0.99902 | 2.073% |
| Controlled legacy → `reference_2026`, 195 sample scans: workflow effect | 2086.82 | 0.51231 | 21.743% |
| Controlled legacy → `reference_2026`, 13 concentration means: workflow effect | 4106.09 | 0.18751 | 24.698% |

At concentration level, the current workflow-effect audit gives a median peak
change of -82.156% near 392 cm⁻¹ and +45.685% near 1589 cm⁻¹, relative to the
controlled legacy rerun.

Before processing, the confirmed mean blank versus the historical mixed
composite has RMSE 930.58, a confirmed-minus-historical mean bias of +789.78,
and Pearson `r = 0.998993`. The high correlation shows similar shape, while the
positive bias and RMSE show that the two references are not interchangeable.

These results show that the blank-only change is substantially smaller than the
full workflow change under the reported metrics. They do **not** show that
`reference_2026` is automatically more accurate, scientifically preferable, or
closer to an unknown ground truth. The large workflow-dependent peak changes
require scientific review before this profile is used for quantitative claims.

All 200 controlled-legacy records also preserve the warning that their Raman-
shift spacing is non-uniform (relative SD 0.221), so the legacy FFT filter uses
the median spacing. This is an explicit historical-method assumption, not a
claim that the grid is uniform; its count is recorded in
`controlled_legacy_confirmed_blank/package_metadata.json`.

The `reference_2026` run records a separate `pybaselines` numerical-library warning:
almost all baseline points were below the data during iARPLS processing,
suggesting that its tolerance or iteration limit may be too strict.
The run completed and the warning is preserved in
`reference_2026/package_metadata.json`; it is another reason to require
scientific review rather than treating this profile as automatically preferred.

## Concentration label correction

For the new manifests and regenerated outputs, `0.0001 M` is labelled
`100 µM`. The paper-facing historical table
`data/published_snapshot/optimisation/4atp_750_5_5_h.csv` contains the header
`100 mM` at that position. That historical typo is retained unchanged to
preserve the submitted snapshot; it must not be copied into the new lineage.

## What this reanalysis does not establish

- It does not validate the mixed 15-spectrum historical composite as an
  experiment-matched blank.
- It does not convert the 195 prepared sample spectra from `raw_unverified` to
  verified raw data.
- It does not establish independent blank-substrate variability from one
  five-channel export.
- It does not validate or modify low- or medium-power 4-ATP experiments.
- It does not make `reference_2026` the preferred scientific result without
  domain review.
- It does not replace any spectrum or table used to prepare the paper.

See [the focused blank audit](4ATP_BLANK_AUDIT.md) for candidate selection and
[the data audit](DATA_AUDIT.md) for repository-wide provenance limitations.
