# Manuscript-to-data map

This map links the scientific claims and figures to the retained publication
snapshot. It also records where the raw lineage is incomplete. Paths are
repository-relative and use normalised names in `data/published_snapshot/`.

| Manuscript item | Repository data | Interpretation and status |
| --- | --- | --- |
| Figure 3, 4-ATP concentration series | `calibration_curve/final_spectra_by_accumulation_wide.csv` and `calibration_curve/replicate_mean_sd_by_shift.csv` | Publication snapshot. The underlying prepared calibration set contains acquisition-setting and blank conflicts. |
| Figure 4A, calibration models | `calibration_curve/calibration_at_selected_shifts.csv` and `calibration_curve/summary_by_concentration.csv` | Publication snapshot. Summary aggregation is internally reproducible; raw identity is not fully verified. |
| Figure 4B and blind-validation table | `blind_samples/blind_predictions.csv` | Publication snapshot. The master measurements use coded labels and the decoding key is missing. |
| Figure 5 and stability table | Historical stability spectra in `data/quarantine/legacy_snapshot/Stability/` | Publication snapshot only. Several files conflict with master concentration/date/setting metadata; the last interval is 128 calendar days, reported approximately as day 130. |
| Figure 6, artificial and human sweat | `proof_of_concept/portable_sweat_summary.csv`, `proof_of_concept/benchtop_sweat_summary.csv`, and `proof_of_concept/benchtop_vs_portable_normalized.csv` | Publication snapshot. The separate portable and benchtop summaries use V2-V4, but the normalized comparison retains legacy V1-V3 headers. The numerical traces are shifted consistently between those label sets, but the intended final labels require author confirmation. Some raw portable filenames also conflict with internal instrument metadata. |
| Supplementary Figures S3-S5, acquisition optimisation | `optimisation/4atp_500_5_5_l.csv`, `optimisation/4atp_750_5_5_h.csv`, and `optimisation/4atp_750_5_5_m.csv` | Publication snapshot. The first and third summaries are internally reproducible from modern derivative tables; the 750-M historical processed folder contains orphan derivatives. |
| Supplementary Figure S6, silicon calibration | `spectrometer_calibration/si_original.csv` and `spectrometer_calibration/si_calibrated.csv` | Verified transformation: intensity retained and Raman shift offset by approximately +0.240026 cm-1. |
| Supplementary Figure S8, analytical enhancement | `analytical_enhancement/aef_summary.csv` | Publication snapshot. The stored values do not directly reproduce the manuscript intensities near 1590 cm-1; an undocumented selection or scaling remains. |

The associated article is *Miniaturised Setup for Surface-Enhanced Raman
Spectroscopy in Sweat Analysis* (manuscript identifier
`SD-ART-05-2026-000093`). Figure images are not duplicated here because the
repository provides the tabular sources intended to regenerate scientific
plots.
