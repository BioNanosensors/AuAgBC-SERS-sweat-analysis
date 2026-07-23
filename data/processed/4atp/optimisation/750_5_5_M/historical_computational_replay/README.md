# 4-ATP 750_5_5_M historical computational replay

Status: **audit evidence only**.

This package reproduces the arithmetic that generated the preserved legacy
medium-power outputs. It covers 43 exact source files,
225 spectral channels, 43 replayed CSV files, and 432
points per channel.

The replay is not a scientifically corrected reanalysis. The historical
calculation subtracted the first channel of an assembled blank embedded-labelled
`AAB_Blank_750_5_5_H`. That blank is not a confirmed `750_5_5_M` blank and its
context remains a provenance conflict.

The replay uses the recovered positional CSV crop, row-wise blank subtraction,
two iARPLS stages, a third-order Butterworth low-pass filter, and source-bound
FFT-bin locks. Those locks document computational history; they are not
recommended scientific processing parameters.

Verification contract:

- Raman axes must be exactly equal to the historical references.
- Intensity RMSE must be no greater than `1e-7`.
- Maximum absolute intensity difference must be no greater than `1e-6`.
- Relative tolerance is zero.

Observed in the validated package:

- Worst RMSE: `6.2941675603483758e-08`.
- Worst maximum absolute difference: `2.2915082809049636e-07`.

The replay proves how the stored numbers were computed. It does not prove that
the inputs, labels, replicates, or mixed high-power blank were scientifically
valid for the medium-power experiment.
