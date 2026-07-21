> **Superseded package result (20 July 2026).** This exploratory report used a separate data-frame replay. Its conclusion that 27 large differences demonstrate provenance mismatches is not supported by the released workflow. The deterministic package replay later reproduced all 955 paired spectra exactly (RMSE and maximum absolute difference both zero). See `package_reproduction_summary.csv`, `package_reproduction_metrics.csv`, and `../../docs/DATA_AUDIT.md`. The report below is retained only as evidence of the historical FFT cutoff's sensitivity to approximately 1e-12 parsing and summation differences.

# Numerical reproduction audit

Runtime: Python 3.12.10; NumPy 2.5.0; pandas 3.0.3; SciPy 1.18.0; pybaselines 1.2.1.

`strict` means `numpy.allclose(rtol=1e-9, atol=1e-9)`. `near` means
`numpy.allclose(rtol=1e-7, atol=1e-7)`. Byte/array identity is not expected after
decimal CSV serialization; no pair was bit-for-bit array-equal.

## Portable v2 profile

Verified recipe: subtract the pointwise mean of all 15 raw blank files from each
nonblank spectrum; do not subtract the mean from blank spectra; iARPLS baseline
(`lambda=3000` for 4-ATP, `lambda=8000` for blanks; difference order 2,
maximum 50 iterations, tolerance 0.001); FFT peak-selected third-order
Butterworth low-pass (10th percentile for samples, 5th percentile for blanks);
then a second iARPLS baseline with `lambda=80`. No Savitzky-Golay pass.

| Family | Feasible pairs | Strict | Near | Material discrepancies | Worst absolute error |
|---|---:|---:|---:|---:|---:|
| Stability/03_07_24 | 165 | 159 | 159 | 6 | 4,078.97 |
| Stability/19_05_24 | 160 | 153 | 155 | 5 | 768.865 |
| Stability/24_09_24 | 210 | 202 | 205 | 5 | 462.289 |
| Optimisation/500_5_5_L | 210 | 199 | 207 | 3 | 8,076.48 |
| Optimisation/750_5_5_H | 210 | 195 | 202 | 8 | 13,197.50 |
| **Total** | **955** | **908** | **928** | **27** | **13,197.50** |

The 27 material failures are isolated files rather than a profile-wide failure;
the median RMSE in every family is between `2.80e-12` and `2.94e-11`. Their
large errors therefore indicate raw/processed provenance mismatches, not floating
point drift. Exact file-level metrics are in `v2_profile_pair_metrics.csv`.

`Optimisation/750_5_5_M` has 210 Stability-style raw files but 43 processed files
with entirely different AAB/BC names and multi-column 432-point schemas. There
are zero feasible name-paired raw/processed spectra in that folder, so none of
those 43 outputs can be regenerated from the curated raw folder.

## Other legacy families

- **Blind samples:** the 27 paired AAB sample files contain five intensity
  columns each (135 spectra). The exact legacy strategy is the first raw blank,
  `blank_rep1_acc1.csv`, cropped at the same legacy index 80 and subtracted from
  every sample column; then `lambda=3000`, FFT percentile 10, Butterworth order
  3, and second baseline `lambda=80`, with no Savitzky-Golay pass. This gives
  123/135 strict and 130/135 near matches. The five material failures are listed
  in `blind_sample_full_profile_metrics.csv`. The 15 separately curated blank
  outputs are 420-point legacy products and are not reproduced by this profile.
- **Calibration curve:** all 210 outputs contain only 420 points, exactly raw
  rows 92 through 511. The closest legacy sample recipe uses the single
  `blank_rep1_acc1.csv`, `lambda=3000`, FFT percentile 10, order 3, second
  baseline `lambda=80`, and no Savitzky-Golay pass. For the sampled spectrum it
  gives RMSE 1.07185 and maximum error 3.86795 (`r=0.999975`), but is not an exact
  match. The best sampled blank result has RMSE 50.4694. These outputs cannot be
  claimed as exactly regenerable from the curated raw folder/current runtime.
- **Analytical Enhancement:** the closest legacy-script family uses the single
  AAB blank, first iARPLS `lambda=3000` for AAB 4-ATP and `lambda=500` for Al
  4-ATP, FFT percentile 10/order 3, second baseline `lambda=80`, and
  Savitzky-Golay `(25, 2)`. It does not reproduce the six curated outputs (mean
  RMSE 368.23; maximum absolute error 5,123.82), indicating a different/missing
  blank or raw-column provenance.
- **Proof of concept, benchtop:** 10 names can be paired, covering 23 intensity
  columns; no blank file is present. The best tested legacy variant adds
  Savitzky-Golay `(25, 2)`, but remains non-exact (mean RMSE 146.21; maximum
  absolute error 2,044.14). There are additional raw/processed filename
  mismatches, so the folder cannot be regenerated as curated.
- **Proof of concept, portable:** only five names pair, covering 25 intensity
  columns, and no blank is present. The best aggregate candidate is the
  portable `lambda=700` AAB-AS/HS chain plus Savitzky-Golay `(25, 3)` and a third
  `lambda=80` baseline, but remains non-exact (mean RMSE 172.43; maximum absolute
  error 1,408.88). The folder cannot be regenerated as curated.

## Repository implication

No complete processed folder is currently fully regenerable. The five large
portable v2 folders and the Blind-sample AAB subset contain strong reproducible
majorities and can be rebuilt after quarantining the listed discrepancies. The
750_5_5_M, Calibration, Analytical Enhancement, and Proof-of-concept processed
folders require corrected raw provenance and/or the missing exact blank before a
scientific repository should assert full reproducibility.
