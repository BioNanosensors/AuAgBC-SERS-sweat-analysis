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
- [x] Record the author's confirmation that no written ethics approval,
  exemption, waiver, or other determination was obtained.
- [x] Record that `V` and `P` are operator/date-dependent prefixes in the same
  pseudonymous coding system and that a private crosswalk is retained.
- [x] Publish a conservative machine-readable inventory of known human-sweat
  records and downstream lineage.
- [x] Correct the unsupported all-human shared-blank description: ten channels
  match columns in Test HS master folders and five match columns in a Test
  4-ATP master folder; sample identity remains unresolved.
- [x] Record the byte-identical processed candidates carrying conflicting
  volunteer labels (dataset-manifest rows 1694 and 1700).
- [x] Document the repository's current no-licence status and proposed scope.

## Required before an unqualified public data release

- [ ] Resolve or explicitly withdraw the conflicting calibration and stability labels documented in `DATA_AUDIT.md`.
- [ ] Supply the blind-sample decoding key.
- [ ] Identify the correct 4-ATP blank files.
- [ ] Confirm the AEF extraction and acquisition-time scaling rule.
- [ ] Confirm whether paper Volunteer 2 equals acquisition V2/P2, Volunteer 3
  equals V3/P3, and Volunteer 4 equals V4/P4 using the retained private key.
- [ ] Confirm whether the normalized Figure 6 comparison should retain legacy
  V1-V3 headers or be relabelled to the V2-V4 publication convention.
- [ ] Privately verify which signed consent version and collection session
  covers each manuscript-reported volunteer; never publish the signed forms.
- [ ] Reconcile the consent-template and manuscript collection protocols.
- [ ] Obtain a written CFATA/UNAM ethics determination for the original collection
  and present public-data release, including any approval, exemption, waiver, or
  required restriction.
- [ ] Confirm whether consent covers public sharing of pseudonymised spectra,
  exact timestamps, and downstream reuse; otherwise re-consent or restrict the
  affected material.
- [ ] Inform the journal editor that no formal prior institutional approval was
  obtained and retain the editor's written determination.
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
