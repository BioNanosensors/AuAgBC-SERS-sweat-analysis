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
medium-power optimisation experiments. One file is a strong provisional match
for the 750 ms high-power optimisation experiment, pending author confirmation:

`Test 4-ATP/24-09-24/Blank/Blanck_AABC_750_5_5_H.csv`

Its SHA-256 is
`e36f0ad7a57ebab8cba038309284305cfecc98d1586499fe73e266e301257dd9`.
It was acquired on the same date with the same nominal setting, but the record
must still confirm that `AABC` means the same AuAgBC/AAB material and that the
substrate contained no 4-ATP. It contains five scans from one export; it is not
evidence for three independently prepared blank substrates.

No historical file has been deleted, renamed, relabelled, or replaced as a
result of this audit.

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
| Prepared blind snapshot | 24 September 2024, `750_5_5_L`, AuAgBC without 4-ATP | Same-date AuAgBC-like candidate is `750_5_5_H` | No confirmed blank |
| Original coded blind experiment | 10 September 2024, low-power samples | Same-date file is `AABC Blank_750_5_5_H.csv`; its embedded tag says `AAG` | No confirmed blank; dataset choice and metadata conflict remain |
| Optimisation, 500 ms low power | 3 July 2024, `500_5_5_L` | No setting-matched AuAgBC blank found | No confirmed blank |
| Optimisation, 750 ms high power | 24 September 2024, `750_5_5_H` | `Blanck_AABC_750_5_5_H.csv` matches date and setting | Provisional; material and absence of 4-ATP need confirmation |
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

## Blind-sample fork that must be resolved first

The prepared Blind folder does not contain the original coded 10 September
blind experiment. All 135 prepared nonblank channels match concentration-labelled
low-power spectra from 24 September; none is an exact match to the coded
10 September measurements. Blank selection depends on which of those two
datasets is intended for release. The current prepared snapshot must not be
described as the decoded coded experiment without the missing decoding record.

## Confirmations still needed

1. Confirm whether `AABC` is an alias or typographical variant of AAB/AuAgBC.
2. Confirm whether `Blanck_AABC_750_5_5_H.csv` is an AuAgBC substrate with no
   4-ATP, acquired as the blank for the 24 September high-power optimisation.
3. Choose whether the Blind release should represent the original 10 September
   coded experiment or the current 24 September concentration-labelled snapshot.
4. Locate or identify any AuAgBC-without-4-ATP measurements acquired at
   `500_5_5_L`, `750_5_5_L`, or `750_5_5_M`, including files stored under an
   unexpected name.

Until those points are resolved, the historical composite remains quarantined
and no candidate is promoted into `data/raw/` as a verified 4-ATP blank.

## Reproducing this audit check

The two evidence tables are checked without third-party dependencies:

```text
python scripts/verify_4atp_blank_audit.py
```

The check validates the declared hashes and decisions and cross-checks all 120
prepared blank records against the existing column-level provenance table.
