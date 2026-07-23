# Medium-power 4-ATP computational-lineage replay

## Scope

This record concerns only the portable-Raman 4-ATP optimisation labelled
`750_5_5_M`. It documents a recovered source-to-output mapping and a
machine-scale numerical replay of the 43 preserved historical processed files.

The replay establishes **computational lineage only**: the identified source
columns and recovered algorithm can generate the stored numerical arrays within
the declared tolerances. It does not establish that every experimental label is
correct, that the source files were the scientifically intended inputs, or that
the historical blank was valid for a medium-power measurement.

The following distinctions are mandatory:

| Record | Question answered | Scientific status |
| --- | --- | --- |
| Paper-facing optimisation table | What values were retained for the manuscript? | `publication_snapshot`; not replaced by this replay |
| Preserved 43 historical processed files | What processed files were supplied in the historical archive? | `provenance_conflict`; preserved unchanged |
| Historical computational replay | Can the preserved arrays be regenerated from explicitly mapped source columns and a recovered algorithm? | `audit_evidence`; computation-only |
| Setting-matched medium-power reanalysis | What would the result be with a verified `750_5_5_M` AuAgBC blank? | Not available; no such blank was identified |

There is deliberately no `reference_2026` medium-power package. Creating one
without a setting- and material-matched blank would convert a documented gap
into an undocumented assumption.

## Recovered source set

The historical processed directory contains 43 files and 225 intensity
channels:

- 39 AuAgBC/AAB 4-ATP files, representing 13 concentrations, three substrate
  replicates, and five technical scan channels per replicate: 195 channels;
- three BC 4-ATP files at 1 mM, with five technical scan channels each:
  15 channels; and
- one assembled `AAB_Blank.csv` file with 15 channels.

The exact computational sources are retained under
`data/quarantine/computational_lineage_sources/4atp/optimisation/750_5_5_M/`.
They consist of 42 unchanged vendor exports and the unchanged assembled
15-channel blank. `resolved_manifest.csv` maps every source column to one
historical output column and records the source and historical-file hashes.

The 210 split spectra already present under
`data/quarantine/legacy_snapshot/Optimisation/750_5_5_M/` are not substituted
for these sources. That prepared folder contains 195 AAB and 15 blank spectra,
contains no BC source partners, and does not preserve the exact vendor Raman
axes used by the 43 historical processed files. The absence of same-stem pairs
in the prepared folder was real; the earlier inference that no computational
lineage could be recovered was too broad.

### Historical blank context

The assembled `AAB_Blank.csv` is not an independent medium-power blank
acquisition. Its 15 intensity channels are the same mixed high-power composite
previously traced to three five-channel source exports. Ten channels match
columns stored in two Test HS high-power exports and five match columns stored
in one Test 4-ATP high-power export. Storage context is not proof of sample
identity.

The recovered script used only the first intensity channel of the assembled
file as the reference subtracted from all 210 nonblank AAB and BC channels. The
15 blank channels themselves were processed without subtracting that reference.
This discovery explains the historical numbers; it does not make the first
channel a valid `750_5_5_M` analytical blank.

The assembled blank and the historical derivatives therefore remain
`provenance_conflict`. The exhaustive blank audit still reports no explicitly
labelled AuAgBC-without-4-ATP export acquired at `750_5_5_M`.

## Recovered processing chain

The replay pins the following historical operations:

1. Read each vendor CSV with `pandas.read_csv(..., header=99)`. The true vendor
   table header is on physical line 20; this historical parser setting instead
   treats physical line 100, the 80th spectral row, as the column header. It
   therefore retains the final 432 of the 512 instrument points. This is a
   recovered historical quirk, not a recommended import rule.
2. For each nonblank channel, subtract the first intensity channel of the
   assembled blank row by row. Do not align or interpolate the axes.
3. Apply a first iARPLS baseline with difference order 2, at most 50
   iterations, and tolerance 0.001:
   - lambda 3000 for AuAgBC/AAB 4-ATP;
   - lambda 1000 for BC 4-ATP; and
   - lambda 700 for assembled-blank channels.
4. Compute the FFT of the first-baseline-corrected intensity, retain the
   positive-frequency half, detect peaks, and calculate the magnitude threshold
   at the 10th percentile for nonblank samples or the 5th percentile for blank
   channels.
5. Select the detected peak whose magnitude is closest to that threshold. Use
   its frequency divided by the maximum positive frequency as the normalized
   cutoff for a third-order Butterworth low-pass filter, then apply `filtfilt`.
6. Apply a second iARPLS baseline with lambda 80, difference order 2, at most
   50 iterations, and tolerance 0.001.
7. Write the filtered-minus-second-baseline intensity. No Savitzky-Golay step
   is applied.

The blank selection, per-material first-baseline lambdas, FFT percentiles,
filter order, and lack of interpolation are explicit configuration values. They
must not be inferred from filenames in a release replay.

## FFT decision lock

The historical closest-to-percentile FFT rule has floating-point midpoint
branches that can select different bins on different numerical platforms.
`metadata/processing_locks/optimisation_750_5_5_m_historical_replay_fft_cutoffs.csv`
therefore binds one selected FFT bin to each of the 225 exact source hashes and
intensity columns.

Thirteen channels have candidates equivalent at a scale of 32 machine epsilons.
For five channels, the bin required to replay the preserved output differs from
the result of the current unpinned `numpy.argmin` branch. Those five entries are
labelled as forensic overrides.

When checking across the two validated CPython patch releases, the unpinned
`numpy.argmin` winner may differ only within the exact recomputed and declared
epsilon-scale candidate set. Generation remains strict. Verification still
requires that complete set to match exactly and uses the same source-bound
selected bin. The committed package bytes remain exactly hash-verified, but
environment-sensitive regenerated intensity and ZIP bytes are not claimed to
be identical. A runtime choice outside the declared set is a hard failure.

The lock records historical branch choices. It is not evidence that the cutoff
is scientifically optimal, and it must not be reused as a parameter set for a
new medium-power analysis.

## Numerical validation

The persistent package compares each regenerated channel directly with its
mapped historical channel:

- files compared: 43 of 43;
- channels compared: 225 of 225;
- points per channel: 432;
- Raman-shift arrays: exactly equal after numerical CSV parsing;
- intensity relative tolerance: 0;
- required maximum absolute difference: at most `1e-6`;
- required RMSE: at most `1e-7`;
- worst observed maximum absolute difference: approximately `2.292e-7`; and
- worst observed RMSE: approximately `6.294e-8`.

All 225 channels pass both intensity bounds. The axis, source/output mapping,
headers, schemas, file set, channel set, and FFT-lock identities are checked
exactly.

This result is described as a **numerically exact replay within explicit
machine-scale bounds**, not as byte identity. Decimal serialization and
platform-level iterative-solver arithmetic can change final text bytes without
changing the demonstrated computational relationship. The preserved historical
files and their SHA-256 hashes remain the authoritative historical bytes.

## Persistent package

| Path | Contents and status |
| --- | --- |
| `data/quarantine/computational_lineage_sources/4atp/optimisation/750_5_5_M/` | Forty-two unchanged vendor exports (`raw_unverified`) and the unchanged assembled blank (`provenance_conflict`) |
| `configs/reanalysis/optimisation_750_5_5_m_historical_replay.json` | Explicit recovered computation |
| `configs/reanalysis/optimisation_750_5_5_m_historical_replay_sources.csv` | Per-file source and historical-reference hashes, acquisition metadata, and conservative provenance statuses |
| `configs/reanalysis/optimisation_750_5_5_m_historical_replay_manifest.csv` | One explicit source-to-output row per channel |
| `metadata/processing_locks/optimisation_750_5_5_m_historical_replay_fft_cutoffs.csv` | Source-hash-bound FFT decisions for all 225 channels |
| `data/processed/4atp/optimisation/750_5_5_M/historical_computational_replay/resolved_manifest.csv` | Resolved 225-channel source, parameter, and output mapping |
| `data/processed/4atp/optimisation/750_5_5_M/historical_computational_replay/replay_metrics.csv` | Per-channel numerical comparison with the preserved historical files |
| `data/processed/4atp/optimisation/750_5_5_M/historical_computational_replay/replayed_spectra.zip` | Deterministic archive of the 43 regenerated files |
| `data/processed/4atp/optimisation/750_5_5_M/historical_computational_replay/package_metadata.json` | Counts, hashes, code identity, environment, tolerances, worst-case metrics, and interpretation limits |

Every replay-package artifact is classified as `audit_evidence`. The generated
spectra are included to make the comparison inspectable; their presence under
`data/processed/` does not promote them to corrected or scientifically
validated medium-power results.

The 43 historical files remain unchanged under
`data/quarantine/legacy_snapshot/Optimisation/750_5_5_M/Processed Spectra/` and
retain `provenance_conflict`.

## Reproduce and verify

Install the pinned release dependencies from the repository root:

```text
python -m pip install -e ".[test]" -c requirements-release.txt
```

Regenerate the deterministic replay package:

```text
python scripts/replay_4atp_750_5_5_m.py
```

Generation also refreshes the stable 4-ATP suffix of
`metadata/dataset_manifest.csv` and verifies all 92 source, historical-reference,
lock, and package rows against their current hashes, sizes, roles, and
conservative statuses. Publication is staged as a complete directory; if
post-publication validation or metadata refresh fails, the previous package and
metadata bytes are restored.

In the canonical generation environment, freshly replay all 225 channels and
require every regenerated package byte to match without replacing the release:

```text
python scripts/replay_4atp_750_5_5_m.py --check
```

For the separately declared compatible Windows environment, run:

```text
python scripts/replay_4atp_750_5_5_m.py --cross-environment-check
```

This second mode does not compare environment-sensitive regenerated intensity
or compressed bytes. It independently requires the committed five-file package
to retain its exact hashes, sizes, internal payload hashes, file set, ZIP
metadata, member hashes, schemas, mappings, headers, and Raman axes. It then
requires a fresh replay from the exact hash-verified sources to reproduce all
225 historical channels within the same `RMSE <= 1e-7`, maximum absolute
difference `<= 1e-6`, and relative tolerance `0` contract.

Both checks fail if a source or historical hash changes, a source column is
reordered or missing, the unique historical blank reference changes, any FFT
lock is absent or stale, the 43-file/225-channel/432-point contract changes, an
axis differs, an intensity exceeds either numerical bound, or a persistent
package file is absent from `metadata/dataset_manifest.csv`. The exact mode
additionally fails if any regenerated package byte differs.

## Relationship to the manuscript

The paper-facing table remains
`data/published_snapshot/optimisation/4atp_750_5_5_m.csv`. The replay package
was created after the publication snapshot was assembled. It does not overwrite
that table, establish that the 43 historical processed files were the sole
inputs to the paper summary, or convert the replayed spectra into replacement
paper data.

The replay can support the narrow statement that the historical processed
arrays have a recovered executable lineage. It cannot support a statement that
the medium-power experiment has a verified raw-to-publication lineage.

## What this replay does not establish

- It does not validate the mixed high-power assembled blank for a
  `750_5_5_M` experiment.
- It does not prove that the first assembled-blank channel was scientifically
  preferable to the other 14 channels.
- It does not verify every sample identity, concentration label, substrate
  label, replicate assignment, or acquisition record.
- It does not transform the vendor exports from `raw_unverified` to verified
  raw data.
- It does not transform the assembled blank or historical processed files from
  `provenance_conflict` to a less restrictive status.
- It does not show that the recovered processing method or locked FFT bins are
  scientifically optimal.
- It does not provide a current corrected reanalysis or a replacement
  medium-power analytical blank.
- It does not validate the separate `_out_raman` summary tables, which are
  outside this package's 43-file scope.
- It does not change any value or label in the paper-facing publication
  snapshot.

## Scientific action still required

Scientific resolution still requires one of the following:

1. contemporaneous evidence identifying a setting- and material-matched
   AuAgBC-without-4-ATP blank already present in the source collection;
2. a newly supplied original `750_5_5_M` blank export with laboratory evidence
   connecting it to the experiment;
3. a scientifically reviewed reanalysis or repeat experiment with an
   appropriate blank; or
4. withdrawal or qualification of claims that depend on treating the
   historical mixed high-power composite as a valid medium-power blank.

Until then, the correct public description is: **computational lineage
recovered; experimental blank validity unresolved**.
