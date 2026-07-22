# 4-ATP blank-file audit

## Outcome

The fifteen files named as blanks in each prepared 4-ATP record group are not
independent, experiment-matched blank measurements. They are repeated copies of
five channels from each of three high-power portable exports acquired on 18,
25, and 30 September 2024. The same composite was copied into eight calibration,
blind, optimisation, and stability record groups (120 prepared files in total).

This identifies the inputs used by the historical processing, but it does not
make them scientifically appropriate blanks. The manuscript and thesis define
the analytical blank as an AuAgBC substrate without 4-ATP. They also specify
`750_5_5_L` (750 ms, five averages, five data counts, 5 mW) as the final
portable 4-ATP condition. A blank can therefore be accepted only when its
material, session or batch, instrument, integration time, averaging, data count,
laser power, and experimental matrix are supported by the record.

No supplied file yet satisfies those criteria for the low-power calibration,
blind, or stability experiments, or for the 500 ms low-power and 750 ms
medium-power optimisation experiments. One separate file is now confirmed for
the 750 ms high-power optimisation experiment:

`Test 4-ATP/24-09-24/Blank/Blanck_AABC_750_5_5_H.csv`

Its SHA-256 is
`e36f0ad7a57ebab8cba038309284305cfecc98d1586499fe73e266e301257dd9`.
On 22 July 2026, the author confirmed that `AABC` means the same AuAgBC/AAB
material and that this file is an AuAgBC substrate without 4-ATP. Its date and
all nominal acquisition settings match the high-power optimisation. An exact,
unchanged copy is distributed at
`data/raw/4atp/optimisation/750_5_5_H/Blanck_AABC_750_5_5_H.csv`.
It contains five scans from one export; it is not evidence for three
independently prepared blank substrates.

This confirmation does not retroactively validate the historical processed
optimisation files. Those files are exactly reproducible with the mixed
15-spectrum composite documented below, which shows what the historical script
used. Reprocessing the high-power experiment with the confirmed blank is a
scientifically corrected run and is expected to differ from that preserved
publication history; the two lineages must remain separately labelled.

No historical file has been deleted, renamed, relabelled, or replaced as a
result of this audit.

## Author resolutions on 22 July 2026

- `AABC` is confirmed as the same material code as AAB/AuAgBC.
- `Blanck_AABC_750_5_5_H.csv` is confirmed as an analyte-free AuAgBC blank and
  is accepted only for the matching 24 September high-power optimisation.
- The author selected the currently prepared 24 September concentration-labelled
  Blind snapshot for release, not the historical coded 10 September experiment.
- The author recalls that additional setting-matched blanks probably existed
  but cannot identify them. That recollection is not treated as file-level
  evidence, so no low- or medium-power blank is inferred or relabelled.

## Method-definition evidence

The submitted manuscript source states that portable 4-ATP measurements used
785 nm excitation, 750 ms integration, five averages, five data counts, and
5 mW laser power; it defines the blank as AuAgBC without 4-ATP. The supporting
information defines `L`, `M`, and `H` as 5, 10, and 15 mW and identifies
`750_5_5_L` as the selected analytical condition. The thesis separately
repeats the blank definition and the 5 mW 4-ATP condition. These statements were
also checked visually on article PDF page 4, supporting-information PDF pages 2
and 4, and thesis printed pages 37, 50, and 51. Hashes for the exact manuscript
archive, rendered-PDF archive, and thesis PDF reviewed are recorded in
`metadata/source_archives.csv`; those source documents are not redistributed in
this repository.

## Historical composite traced exactly

All fifteen intensities match the following master-export channels exactly.
The Raman-axis differences for prepared replicates 2 and 3 affect ten of the
fifteen positions in each record group, or 80 of the 120 prepared copies. Their
intensity columns still match the identified master channels exactly.

| Prepared replicate | Exact master export | Embedded acquisition | Axis maximum absolute difference (cm-1) | Scientific assessment |
| --- | --- | --- | ---: | --- |
| 1, scans 1-5 | `Test HS/25-09-24/Blank/AAB_Blank_750_5_5_H.csv` | 25 September 2024, `750_5_5_H` | 0.000000500 | Historical input; wrong context for low-power 4-ATP work |
| 2, scans 1-5 | `Test HS/30-09-24/Blank/AAB_Blank_750_5_5_H.csv` | 30 September 2024, `750_5_5_H` | 0.053573088 | Historical input; wrong context and prepared axis differs |
| 3, scans 1-5 | `Test 4-ATP/18-09-24/Blank/AAB_Blank_750_5_5_H.csv` | 18 September 2024, `750_5_5_H` | 0.161017464 | Historical input; wrong session/power and prepared axis differs |

The complete, machine-readable mapping is in
`metadata/provenance/shared_blank_origin_summary.csv`. Exact reproduction of a
historical processed spectrum using these inputs establishes computational
lineage only; it does not validate the blank's experimental identity.

The submitted material also included an assembled fifteen-channel
`AAB_Blank.csv` with SHA-256
`ea9fa6fde91eca76dc1d2c281a7cd2aa0a544ba204293438f7523f3b5121bf77`.
Its instrument header claims a 25 July high-power acquisition, but its intensity
columns are the same mixed September composite traced above. It is an assembled
historical input, not an independent blank acquisition.

## Assessment by experiment

| Experiment or release scope | Required context | Best evidence found | Current decision |
| --- | --- | --- | --- |
| Calibration curve | 3 July 2024, `750_5_5_L`, AuAgBC without 4-ATP | Same-date `BC Blank 750_5_5_L.csv` matches the setting but is labelled bare BC | No confirmed blank |
| Author-selected prepared blind snapshot | 24 September 2024, `750_5_5_L`, AuAgBC without 4-ATP | Same-date analyte-free AuAgBC candidate is `750_5_5_H` | Release scope confirmed; no setting-matched blank |
| Historical coded blind experiment, not selected | 10 September 2024, low-power samples | Same-date file is `AABC Blank_750_5_5_H.csv`; its embedded tag says `AAG` | Not selected for release; blank remains unresolved |
| Optimisation, 500 ms low power | 3 July 2024, `500_5_5_L` | No setting-matched AuAgBC blank found | No confirmed blank |
| Optimisation, 750 ms high power | 24 September 2024, `750_5_5_H` | `Blanck_AABC_750_5_5_H.csv` matches date, material, analyte-free identity, and settings | Confirmed context match |
| Optimisation, 750 ms medium power | 24 September 2024, `750_5_5_M` | No medium-power AuAgBC blank found | No confirmed blank |
| Stability, day 1 | 19 May 2024; intended `750_5_5_L` | A folder-local AuAgBC blank exists only at high power and has a 20 May timestamp; the prepared family also mixes dates/settings | No blank valid for the complete family |
| Stability, day 45 | 3 July 2024, `750_5_5_L` | Same-date low-power file is labelled bare BC | No confirmed blank |
| Stability, day 128 | 24 September 2024, `750_5_5_L` | Same-date AuAgBC-like candidate is high power | No confirmed blank |

Full paths, hashes, acquisition checks, and reasons are in
`metadata/provenance/4atp_blank_family_assessment.csv`.

## Other unresolved candidate

`Parámetros heterogéneos de medición/Primeras mediciones/24-06-24/Blank/AAB_blank.csv`
is a genuine five-channel AAB-labelled blank export acquired with 750 ms, five
averages, and five data counts. Its SHA-256 is
`ef476bb3b3ae59196766ddc529c2c3d12ad80d2dbc520def8a1bb7b03c429fbc`.
Neither its filename nor its instrument header records laser power, and the same
session contains measurements explicitly labelled low, medium, and high power.
Its power cannot be inferred from date or folder context. It is also from a
different date than the final experiments, so it remains an unresolved
candidate rather than a replacement.

## Blind release selection

The prepared Blind folder does not contain the original coded 10 September
blind experiment. All 135 prepared nonblank channels match concentration-labelled
low-power spectra from 24 September; every prepared concentration agrees with
its matching master spectrum, and none is an exact match to the coded
10 September measurements. The author selected this current 24 September
snapshot for release. The 10 September decoding key is therefore not required
for the selected release scope, but it would still be required before the
historical coded experiment could be released or used to substantiate the
original blinded-validation lineage.

## Blank files still needed

The remaining task is to locate or identify any AuAgBC-without-4-ATP
measurements acquired at `500_5_5_L`, `750_5_5_L`, or `750_5_5_M`, including
files stored under an unexpected name. The author's uncertain recollection that
such files probably existed is recorded, but it is not sufficient to select a
file.

The historical composite remains quarantined. Only the separately confirmed
`750_5_5_H` source is promoted into `data/raw/`, and it must not be substituted
for the still-missing low- or medium-power blanks.

## Reproducing this audit check

The two evidence tables are checked without third-party dependencies:

```text
python scripts/verify_4atp_blank_audit.py
```

The check validates the declared hashes and decisions and cross-checks all 120
prepared blank records against the existing column-level provenance table.
