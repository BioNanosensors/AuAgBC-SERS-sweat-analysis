# Human-data governance status

## Current status

This public repository contains pseudonymised Raman spectra from an exploratory
human-sweat study. The manuscript and thesis report three analysed volunteers.
The author subsequently confirmed that four volunteers were originally tested,
but acquisition volunteer 1 produced no usable signal and was excluded; the
three retained volunteers were intentionally renumbered for publication. The
audit found pseudonymous path/hash records for upstream acquisition-1
measurement attempts, but no distributed spectrum is presently evidenced as
acquisition volunteer 1. The no-usable-signal conclusion remains an author
confirmation rather than an inference from those metadata records.

The repository also contains copies and processed derivatives of a shared-blank
series reused historically in non-human experiments. Exact numerical matches
place ten of its fifteen channels in Test HS master folders and five in a Test
4-ATP master folder. Folder context is not proof of sample identity, so the
blank is classified as identity-unresolved rather than human-derived. Public
access is provided for transparent audit; it is not, by itself, evidence of
ethics approval, valid consent for open data sharing, anonymisation, or
permission for downstream reuse.

The associated manuscript and thesis state that signed informed consent was
obtained before collection and that no formal institutional ethics approval was
obtained for this proof-of-concept stage. The authors describe the measurements
only as preliminary technical observations and do not use them for clinical,
safety, prevalence, or diagnostic-performance claims.

A later CFATA/UNAM CEID letter, registration `CFATA/CEID/002-2026`, states that
the committee reviewed and approved on 25 June 2026 a broad human-research
protocol that expressly includes non-invasive sweat sampling and spectroscopic
analysis. The notification is dated 1 July 2026. Because the letter postdates
the 2024 acquisitions and does not explicitly address retrospective coverage or
public data sharing, the repository does not describe it as prospective
approval for those sessions or as permission for open reuse. See
`ETHICS_APPROVAL.md`.

## Evidence reviewed

The following private project records were reviewed without copying them into
this repository:

- the manuscript source and rendered manuscript;
- the rendered master's thesis;
- a blank informed-consent template dated 3 October 2024;
- a draft CFATA ethics-protocol form;
- the signed CFATA/CEID approval letter dated 1 July 2026; and
- the supplied Raman archives, manifests, and instrument metadata.

The consent template authorises donation of sweat and use of the sample for
research. It does not state that spectra or metadata may be placed in a public
repository, licensed for unrestricted downstream reuse, retained indefinitely,
or shared with exact acquisition timestamps. It also does not describe
anonymisation, confidentiality, withdrawal, or destruction of the linkage key.

Signed copies were not included in the records reviewed. On 21 July 2026, the
author confirmed that signed forms are retained privately for all three
manuscript-reported volunteers. Their exact wording and session coverage were
not reviewed, so permission for public data sharing remains unverified. The
author initially reported that no written ethics determination was available;
later the same day, the advisor supplied the CFATA/CEID approval letter. This
chronology and the document's identifier-minimised metadata are recorded in
`metadata/author_confirmations.csv` and
`metadata/ethics_approval_record.csv`.

## Protocol reconciliation required

The available consent template and the manuscript do not describe the same
collection procedure in every detail. The template refers to a 6 mm patch at the
temple, asepsis, and an example of five minutes of light exercise. The
manuscript/thesis refer to an approximately 8 mm substrate on the forehead,
washing with soap and water, and approximately 30 minutes of moderate exercise.
The template is dated after some portable acquisition timestamps. The authors
must identify the signed version used for each volunteer and session and explain
which protocol was actually followed.

## Pseudonymisation and re-identification considerations

No direct participant names, contact details, or demographics were found in the
released human-sweat CSV files. The instrument exports do retain coded volunteer
identifiers and exact acquisition dates/times. The outer filename, embedded
`Name`/`Tag`, master filename, and publication labels disagree for several
portable records. These data are therefore described as pseudonymised, not
proven anonymous.

Two processed human-sweat candidate files are byte-identical while carrying
different labels (dataset-manifest rows 1694 and 1700). The confirmed crosswalk
resolves them as acquisition- and publication-namespace aliases for the same
deidentified acquisition record. This record-level resolution does not disclose
or independently establish the participant's identity. The machine-readable
summary records the affected checksum and row numbers without repeating the
volunteer labels.

The author confirmed that `V` and `P` are alternative prefixes in the same
pseudonymous acquisition-code system; a different operator and acquisition date
led to a different prefix choice. Same-numeric codes identify the same
acquisition volunteer: V2/P2, V3/P3, and V4/P4. For publication, those retained
volunteers were intentionally renumbered V1, V2, and V3, respectively. The
private identity key remains unpublished; only this deidentified code crosswalk
is recorded in `metadata/proof_of_concept_code_crosswalk.csv`.

The author also confirmed that the embedded `V2S2` value associated with
`AA_HS_V1S1_H` is a metadata mistake and that the canonical acquisition session
is V2S1. Historical source bytes remain unchanged; the correction is recorded
only in `metadata/provenance/proof_of_concept_label_evidence.csv`. Header-only
publication corrections and their unchanged numerical-body hashes are recorded
in `metadata/provenance/publication_header_corrections.csv`.

The repository verifier performs a limited direct-identifier scan for email
addresses and private computer-home paths. It does not establish anonymisation
and does not test participant-code linkage, exact dates, free-text names, or
re-identification risk.

## Machine-readable lineage inventory

`metadata/human_data_lineage.csv` is generated by
`scripts/report_human_data_lineage.py`. It is identifier-minimised: it omits
volunteer labels, acquisition dates, embedded `Name`/`Tag` values, master paths,
and repository paths. The `dataset_manifest_row` column provides an auditable
join to the full public manifest. It records a conservative lower bound of:

1. 18 direct files labelled `human_sweat` in the processing manifest;
2. 18 processed proof-of-concept human-sweat candidates;
3. three mixed human/artificial-sweat paper summaries;
4. 120 zero-difference copies of the identity-unresolved shared blank across
   eight record groups: 80 linked to Test HS master folders and 40 linked to a
   Test 4-ATP master folder; and
5. 630 non-human-experiment derivatives with an unresolved blank input: 420
   linked to Test HS folder context and 210 to Test 4-ATP folder context.

The report deliberately separates `artifact_sample_identity` from
`master_folder_context` and does not infer identity from spectral similarity.
Its `lineage_group_id` groups records by the exact-content or exact-match
evidence used for that relation; it does not prove a common participant,
acquisition, or sample identity. Some blind-sample and stability derivatives may
use the same blank without an explicit manifest note, so the inventory must not
be interpreted as exhaustive.

Verify the committed report with:

```text
python scripts/report_human_data_lineage.py --check
```

## Required decisions and evidence

The human-data release item remains unresolved until the authors document all
of the following:

1. Private verification of the exact signed consent version and collection
   session covered for each manuscript-reported volunteer.
2. Confirmation that a signed consent form is also retained for the excluded
   acquisition volunteer 1; no signed form or participant identity should be
   published.
3. Whether the signed wording permits public sharing of pseudonymised spectra,
   exact acquisition timestamps, and downstream reuse.
4. Written CFATA/CEID clarification of whether `CFATA/CEID/002-2026` applies to
   the completed 2024 collection and present public-data release, including any
   required restriction.
5. Written disclosure to the journal editor of the 2024 collection chronology,
   absence of formal prior approval, and subsequent 2026 approval, together
   with the editor's determination.
6. A pseudonym-only mapping from each raw file and checksum to the correct
   publication trace, with no names or other re-identifying information added to
   the repository.
7. Who controls the confirmed existing participant linkage key, how it is
   protected, and whether exact dates/times can be removed from a public
   derivative.
8. Reconciliation of the consent-template and manuscript collection protocols.

If open sharing is not covered, the authors should seek participant re-consent
and institutional guidance. If that is not possible, the public release should
be limited to material the institution confirms can be shared, with restricted
or controlled access for affected raw spectra. Because the repository has
already been public, changing visibility later cannot recall copies already
downloaded.

## External policy references

- [RSC author responsibilities and human/animal welfare policy](https://www.rsc.org/publishing/journals/processes-and-policies/author-responsibilities)
- [RSC data-sharing policy](https://www.rsc.org/publishing/publish-with-us/publish-a-journal-article/data-sharing)
- [UNAM guidance on informed-consent content](https://www.zaragoza.unam.mx/wp-content/2023/Cuerpos_Colegiados/Comite_etico_investigacion/Lineamientos_elaboracion_Carta_Consentimiento_FESZ.pdf)

The institutional ethics body and journal editor, rather than this repository,
must make the applicable ethics and publication determinations.
