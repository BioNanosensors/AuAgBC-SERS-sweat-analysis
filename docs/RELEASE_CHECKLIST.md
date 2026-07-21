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
- [x] Record the absence of a located formal approval, exemption, waiver,
  signed-form set, deidentification procedure, or data-sharing determination.
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
- [ ] Confirm the proof-of-concept volunteer mapping.
- [ ] Locate the signed consent forms for the manuscript-reported three
  volunteers and confirm which version and collection session each covers;
  never publish the signed forms.
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
Human-sweat data and known derivatives must remain outside any open-data licence
until their governance is resolved. The copyright holders must make and document
the final choice; see `LICENSING.md`.
