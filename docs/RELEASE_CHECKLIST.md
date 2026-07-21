# Release checklist

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

## Required before an unqualified public data release

- [ ] Resolve or explicitly withdraw the conflicting calibration and stability labels documented in `DATA_AUDIT.md`.
- [ ] Supply the blind-sample decoding key.
- [ ] Identify the correct 4-ATP blank files.
- [ ] Confirm the AEF extraction and acquisition-time scaling rule.
- [ ] Confirm the proof-of-concept volunteer mapping.
- [ ] Obtain any required human-participant/data-sharing approval for deidentified raw sweat spectra.
- [ ] Choose a code licence and a data licence; no licence is granted merely by making a repository public.
- [ ] Add the article DOI once assigned.
- [ ] Create a tagged release and archive that release in a DOI-issuing repository such as Zenodo.

## Suggested licences for the authors to consider

This is not a licence grant. A common arrangement is an OSI-approved licence
such as MIT or BSD-3-Clause for code and CC BY 4.0 for data and documentation.
The copyright holders must make and document the final choice.
