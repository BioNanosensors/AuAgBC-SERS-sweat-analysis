# Release checklist

The repository is publicly visible as a transparent work in progress. Unchecked
items below remain limitations; public visibility does not mark them resolved.

## Completed in this reconstruction

- [x] Preserve source archives unchanged outside the repository.
- [x] Inventory every prepared file and historical Python script.
- [x] Hash retained data files with SHA-256.
- [x] Compare raw-like spectrum columns with both master measurement trees.
- [x] Separate publication snapshots, regenerated outputs, and unresolved data.
- [x] Replace private absolute paths in repository copies.
- [x] Consolidate the processing routines behind one command-line interface.
- [x] Record processing parameters and input checksums in output provenance.
- [x] Add automated tests for readers, processing steps, and end-to-end runs.

## Governance evidence review completed

- [x] Locate and compare the manuscript and thesis human-participant statements.
- [x] Review the available blank consent template without publishing it.
- [x] Confirm that the available template permits research use but does not
  explicitly permit public data sharing or open downstream reuse.
- [x] Record that signed forms were not present in the reviewed files and the
  author's subsequent confirmation that they are retained privately.
- [x] Confirm that a signed consent form is also retained privately for excluded
  acquisition volunteer 1; do not publish any signed form or participant
  identity.
- [x] Preserve the audit chronology: the author initially reported no written
  ethics determination, then supplied a later CFATA/CEID approval letter.
- [x] Review and hash the private signed approval letter without publishing its
  committee-member signatures.
- [x] Record its decision, registration number, dates, protocol scope, and
  explicit limitations in `ETHICS_APPROVAL.md`.
- [x] Record that `V` and `P` are operator/date-dependent prefixes in the same
  pseudonymous coding system and that a private crosswalk is retained.
- [x] Confirm the deidentified acquisition crosswalk V2/P2, V3/P3, and V4/P4
  and the intended publication renumbering to V1, V2, and V3.
- [x] Confirm that embedded `V2S2` for `AA_HS_V1S1_H` is a metadata error and
  that V2S1 is the canonical acquisition session.
- [x] Record the deidentified crosswalk, record-level label evidence, and
  header-only publication corrections in machine-readable metadata.
- [x] Verify that no distributed spectrum is presently evidenced as excluded
  acquisition volunteer 1; upstream path/hash metadata for measurement attempts
  remains visible for audit.
- [x] Publish a conservative machine-readable inventory of known human-sweat
  records and downstream lineage.
- [x] Correct the unsupported all-human shared-blank description: ten channels
  match columns in Test HS master folders and five match columns in a Test
  4-ATP master folder; sample identity remains unresolved.
- [x] Record and resolve the byte-identical processed candidates at
  dataset-manifest rows 1694 and 1700 as acquisition/publication aliases.
- [x] Document the repository's current no-licence status and proposed scope.
- [x] Trace all 120 prepared 4-ATP blank copies to three five-channel master
  exports and publish an experiment-by-experiment candidate assessment.
- [x] Confirm that `AABC` means AAB/AuAgBC and that the separate 24 September
  `750_5_5_H` file is an analyte-free AuAgBC blank; distribute its unchanged
  source bytes for the matching high-power optimisation only.
- [x] Select the current 24 September concentration-labelled Blind snapshot for
  release and verify that all 135 nonblank columns have agreeing same-date,
  same-setting concentration-labelled master matches.
- [x] Preserve the historical `750_5_5_H` optimisation lineage made with the
  mixed 15-spectrum composite, without overwriting its spectra or paper-facing
  summary.
- [x] Add a controlled `legacy_individual` rerun with the author-confirmed
  five-channel blank so the blank-only effect can be audited separately.
- [x] Add a separately labelled `reference_2026` high-power reanalysis and
  comparison package; record that its differences include multiple workflow
  changes and cannot be attributed only to the blank.
- [x] Retain `raw_unverified` on the 195 prepared sample inputs and apply
  `regenerated_partial_provenance` to their new derivatives; record the
  approximately 0.39937 cm⁻¹ prepared-versus-vendor axis difference.
- [x] Record that the confirmed blank is one export with five technical scans,
  not five or three independent blank substrates.
- [x] Use `100 µM` for `0.0001 M` in the new lineage while preserving the
  historical paper-facing `100 mM` header typo unchanged.
- [x] Recover an explicit source-column mapping for all 43 historical
  `750_5_5_M` processed files: 39 AAB, three BC, and one 15-channel assembled
  blank file, covering 225 channels.
- [x] Replay all 225 medium-power historical channels with exact parsed
  Raman-shift arrays and machine-scale intensity bounds, and publish the
  per-channel metrics and source-hash-bound FFT decisions as `audit_evidence`.
- [x] Record that the replay proves computation only: the workflow used the
  first channel of the mixed high-power assembled blank, so the blank and
  historical outputs remain `provenance_conflict`.
- [x] Keep the replay separate from the publication snapshot and decline to
  publish a `reference_2026` medium-power result without a setting-matched
  AuAgBC blank.
- [x] Map all 210 prepared calibration scans to exact source intensity columns,
  source dates, settings, and hashes; record that 44/195 sample scans conflict
  with the intended date or setting.
- [x] Record that 45/210 prepared calibration axes differ from their
  exact-intensity source match beyond `1 × 10⁻⁵ cm⁻¹`, including 35 sample
  scans and ten blanks.
- [x] Identify six exact calibration source-scan reuse groups involving 12
  prepared rows and record that the affected prepared entries are not
  independent observations.
- [x] Recover the October 2025 Figure 3/4A processing chain and replay all 210
  processed scan channels and six aggregate-table comparisons within declared
  cross-environment tolerances.
- [x] Publish the calibration replay manifest, processing configuration,
  source-hash-bound FFT decisions, per-channel metrics, table metrics, model
  sensitivities, parameter comparison, and claim assessment as
  `audit_evidence`.
- [x] Test the supplied summary against the manuscript's declared exponential
  model and record that none of the three paper `Y0`/`k`/`R²` rows is
  reproduced.
- [x] Mark every calibration LOD/LOQ sensitivity value non-reportable because
  no context-matched low-power AuAgBC blank is available; retain the numerical
  values only as diagnostics.
- [x] Register all 12 calibration audit/report artifacts as checksum-bound
  `audit_evidence` and regenerate them after provenance/validation resets in a
  complete repository rebuild.
- [x] Verify the complete calibration replay on the canonical Windows release
  stack and on both supported Linux compatibility lanes, including the oldest
  tested Python 3.10 dependency patch stack.
- [x] Make a complete repository rebuild rerun the five-family package
  validation so its 955-row exact-reproduction evidence is not dropped.

## Required before an unqualified public data release

- [ ] Correctly reacquire/recover the calibration inputs or explicitly withdraw
  the uniform-acquisition, independent-replicate, quantitative model, LOD/LOQ,
  and calibration-dependent prediction claims documented in
  `CALIBRATION_CURVE_AUDIT.md`.
- [ ] Resolve or explicitly withdraw the conflicting stability labels
  documented in `DATA_AUDIT.md`.
- [ ] Supply the 10 September decoding key before releasing that historical
  coded experiment or presenting the selected 24 September snapshot as its
  decoded blinded-validation result.
- [x] Exhaustively search the supplied portable master collection for the
  missing `500_5_5_L`, `750_5_5_L`, and `750_5_5_M` AuAgBC blanks; record the
  negative result, portable search counts, hashes, and contextual candidates in
  `4ATP_BLANK_AUDIT.md` and machine-readable provenance tables. Benchtop files
  were rejected for this purpose because they use a different instrument and
  Raman grid.
- [ ] Obtain evidence outside the supplied collections for the unresolved
  low- and medium-power blanks, or scientifically document withdrawal or
  reanalysis of the affected comparisons. The author's uncertain recollection
  is not file-level evidence, and the historical high-power composite must not
  be reused as if independently acquired for every experiment. The recovered
  `750_5_5_M` computation does not satisfy this item because it identifies use
  of the conflicting historical composite rather than a valid medium-power
  blank.
- [ ] Confirm the AEF extraction and acquisition-time scaling rule.
- [ ] Complete scientific review before presenting the high-power
  `reference_2026` reanalysis as more accurate, preferred, or suitable for new
  quantitative claims; until then keep it explicitly separate from the
  paper-facing historical lineage.
- [ ] Privately verify which signed consent version and collection session
  covers each of the four originally tested volunteers; never publish the
  signed forms.
- [ ] Reconcile the consent-template and manuscript collection protocols.
- [ ] Obtain written CFATA/CEID clarification of whether
  `CFATA/CEID/002-2026` applies retrospectively to the 2024 collection and to the
  present public-data release, including any required restriction.
- [ ] Confirm whether consent covers public sharing of pseudonymised spectra,
  exact timestamps, and downstream reuse; otherwise re-consent or restrict the
  affected material.
- [ ] Inform the journal editor of the 2024 collection, absence of formal prior
  approval, and subsequent 2026 approval; retain the editor's written
  determination.
- [ ] Choose a code licence and a data licence; no licence is granted merely by making a repository public.
- [ ] Correct the manuscript's repository URL and future-tense Data Availability
  wording to `https://github.com/BioNanosensors/AuAgBC-SERS-sweat-analysis`.
- [ ] Add the article DOI once assigned.
- [ ] Create a tagged release and archive that release in a DOI-issuing repository such as Zenodo.

## Suggested licences for the authors to consider

This is not a licence grant. A common arrangement is an OSI-approved licence
such as MIT or BSD-3-Clause for code and CC BY 4.0 for data and documentation.
Human-sweat candidates and identity-unresolved blank artifacts and derivatives
must remain outside any open-data licence until their governance or identity is
resolved. The copyright holders must make and document the final choice; see
`LICENSING.md`.
