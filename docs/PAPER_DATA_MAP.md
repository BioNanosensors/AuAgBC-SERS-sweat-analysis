# Manuscript-to-data map

This map links the scientific claims and figures to the retained publication
snapshot. It also records where the raw lineage is incomplete. Paths are
repository-relative and use normalised names in `data/published_snapshot/`.

| Manuscript item | Repository data | Interpretation and status |
| --- | --- | --- |
| Figure 3, 4-ATP concentration series | `calibration_curve/final_spectra_by_accumulation_wide.csv` and `calibration_curve/replicate_mean_sd_by_shift.csv` | Publication snapshot. A dedicated replay regenerates all 210 processed scan channels and the aggregate tables within declared cross-environment tolerances. This establishes computation only: 44/195 samples conflict with the intended date or setting, 45/210 prepared axes differ from their exact-intensity source match beyond `1 × 10⁻⁵ cm⁻¹`, 12 prepared rows participate in exact source-scan reuse, and all 15 blanks are later high-power records. See `CALIBRATION_CURVE_AUDIT.md`. |
| Figure 4A, calibration models | `calibration_curve/calibration_at_selected_shifts.csv` and `calibration_curve/summary_by_concentration.csv` | Publication snapshot. The supplied summary does not reproduce the paper's `Y0`, `k`, or `R²` for any of the three bands under the manuscript's stated model. LOD/LOQ are not reportable because a context-matched low-power AuAgBC blank is unavailable. |
| Figure 4B and blind-validation table | `blind_samples/blind_predictions.csv` | Publication snapshot. The author selected the prepared 24 September concentration-labelled set, whose 135 nonblank columns have agreeing same-date and same-setting master matches. It is not the historical coded 10 September experiment and cannot independently substantiate that blinded-validation lineage without the missing decoding key. Its quantitative interpretation also depends on calibration parameters and thresholds that are not presently validated. |
| Figure 5 and stability table | Historical stability spectra in `data/quarantine/legacy_snapshot/Stability/` | Publication snapshot only. Several files conflict with master concentration/date/setting metadata; the last interval is 128 calendar days, reported approximately as day 130. |
| Figure 6, artificial and human sweat | `proof_of_concept/portable_sweat_summary.csv`, `proof_of_concept/benchtop_sweat_summary.csv`, and `proof_of_concept/benchtop_vs_portable_normalized.csv` | Publication snapshot. All three tables use the confirmed publication labels V1-V3. Acquisition V2/P2, V3/P3, and V4/P4 map to publication V1, V2, and V3. The two formerly V2-V4 summary headers were corrected without changing any numerical-body byte; the code crosswalk, raw-label evidence, and before/after hashes are retained in `metadata/`. Executable raw-to-summary lineage remains incomplete. |
| Supplementary Figures S3-S5, acquisition optimisation | `optimisation/4atp_500_5_5_l.csv`, `optimisation/4atp_750_5_5_h.csv`, and `optimisation/4atp_750_5_5_m.csv` | Publication snapshot. The `750_5_5_M` historical processed arrays now have a recovered 43-file/225-channel computational replay, but that workflow uses the first channel of a mixed high-power assembled blank rather than a confirmed medium-power blank. The replay is audit evidence and does not replace or validate the paper-facing table. The `100 mM` header at the `0.0001 M` position is a preserved historical typo; the correct label is `100 µM`. |
| Supplementary Figure S6, silicon calibration | `spectrometer_calibration/si_original.csv` and `spectrometer_calibration/si_calibrated.csv` | Verified transformation: intensity retained and Raman shift offset by approximately +0.240026 cm-1. |
| Supplementary Figure S8, analytical enhancement | `analytical_enhancement/aef_summary.csv` | Publication snapshot. The stored values do not directly reproduce the manuscript intensities near 1590 cm-1; an undocumented selection or scaling remains. |

The associated article is *Miniaturised Setup for Surface-Enhanced Raman
Spectroscopy in Sweat Analysis* (manuscript identifier
`SD-ART-05-2026-000093`). Figure images are not duplicated here because the
repository provides the tabular sources intended to regenerate scientific
plots.

## Calibration replay is not calibration validation

The files under `metadata/provenance/`,
`metadata/processing_locks/`, `metadata/validation/`, and
`configs/reanalysis/` that begin with `calibration_` were added after the
paper-facing snapshot was assembled. They document source-column lineage,
source reuse, the recovered October 2025 processing chain, cross-environment
replay metrics, model sensitivity, and claim disposition.

All 210 scan channels and six aggregate-table comparisons pass their declared
replay bounds. The publication snapshot is therefore computationally
recoverable. The replay does not correct the mixed source settings, provide the
missing low-power AuAgBC blank, restore independence to reused source scans, or
reproduce the manuscript's three parameter rows. It must not be cited as a
validated LOD/LOQ or as support for calibration-dependent quantitative blind
predictions. See [the full calibration audit](CALIBRATION_CURVE_AUDIT.md).

## High-power reanalysis is not a replacement paper source

The new packages under
`data/processed/4atp/optimisation/750_5_5_H/controlled_legacy_confirmed_blank/`
and `data/processed/4atp/optimisation/750_5_5_H/reference_2026/` were generated
after the paper-facing snapshot was assembled. They are not claimed as inputs
to Supplementary Figures S3-S5 and do not overwrite the historical table.

The controlled legacy package changes only from the historical mixed
15-spectrum blank composite to the one author-confirmed five-channel blank. The
`reference_2026` package also changes multiple processing operations, so its
difference is a workflow effect and cannot be attributed solely to the blank.
The comparison tables are under
`data/processed/4atp/optimisation/750_5_5_H/comparison/`.

Both packages are labelled `regenerated_partial_provenance` because the 195
prepared sample intensities match vendor exports but their Raman axes differ by
approximately 0.39937 cm⁻¹. The blank contains five technical scans from one
export, not independent substrate replicates. `reference_2026` requires
scientific review and is not automatically the more accurate or preferred
lineage. See [the full reanalysis record](4ATP_HIGH_POWER_REANALYSIS.md).

## Medium-power computational replay is not a corrected paper source

The package under
`data/processed/4atp/optimisation/750_5_5_M/historical_computational_replay/`
was generated after the publication snapshot was assembled. It maps 225 source
columns to all 43 preserved historical processed files and demonstrates a
numerically exact replay within explicit machine-scale bounds.

The recovered historical workflow subtracts the first channel of an assembled
mixed high-power blank. No setting-matched `750_5_5_M` AuAgBC blank was
identified. The package is therefore `audit_evidence`, the source vendor
exports remain `raw_unverified`, and the assembled blank and historical outputs
remain `provenance_conflict`. The replay neither replaces
`optimisation/4atp_750_5_5_m.csv` nor establishes a verified
source-to-publication lineage. See
[the full computational-lineage replay record](4ATP_MEDIUM_POWER_COMPUTATIONAL_REPLAY.md).
