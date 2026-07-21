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

## Required before an unqualified public data release

- [ ] Resolve or explicitly withdraw the conflicting calibration and stability labels documented in `DATA_AUDIT.md`.
- [ ] Supply the blind-sample decoding key.
- [ ] Identify the correct 4-ATP blank files.
- [ ] Confirm the AEF extraction and acquisition-time scaling rule.
- [ ] Confirm that a signed consent form is retained for excluded acquisition
  volunteer 1; never publish the signed form.
- [ ] Privately verify which signed consent version and collection session
  covers each manuscript-reported volunteer; never publish the signed forms.
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
