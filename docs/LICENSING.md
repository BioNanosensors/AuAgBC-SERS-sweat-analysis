# Licensing decision record

## Current status

No project licence is currently granted for this repository. Default copyright
rules therefore apply, while GitHub's platform terms still permit viewing and
forking public repositories through GitHub. Public visibility must not be
described as an open-source or open-data licence.

The article's open-access licence and the repository licences are separate
decisions. A journal licence does not automatically license the underlying code,
raw spectra, metadata, or quarantined files.

## Proposed path-based arrangement

The following is a recommendation for the copyright holders to confirm; it is
not yet a licence grant.

| Material | Proposed licence | Required confirmation |
| --- | --- | --- |
| `src/`, `scripts/`, `tests/`, `process_raman.py`, and code-like configuration | MIT | All relevant code copyright holders approve. |
| Documentation, confirmed non-human spectra, confirmed non-human processed tables, and metadata authored for this project | CC BY 4.0 | Authors/institution confirm ownership and authority to license; unresolved shared-blank material is excluded. |
| Human-sweat candidates, mixed human-sweat summaries, identity-unresolved shared-blank copies, and derivatives using that blank | No open licence until governance or sample identity is resolved | Consent and institutional determination cover public sharing and reuse, or the blank is independently established as non-human. |
| Third-party software dependencies | Their own upstream licences | No dependency source is vendored; dependency notices remain authoritative. |

An alternative permissive code licence such as BSD-3-Clause is also suitable.
The choice should follow the authors' and UNAM's ownership requirements.
Ownership of the GitHub organisation does not, by itself, establish ownership
of every file in the repository. Likewise, CC BY 4.0 permits commercial use and
adaptation; it must not be applied to material that is authorised only for
research use.

The proposed CC BY scope is subordinate to the exclusions in
`metadata/human_data_lineage.csv`: every listed manifest row/checksum remains
outside the proposed open-data licence until its applicable governance or sample
identity issue is resolved. This precedence avoids treating a non-human
experiment derivative as confirmed non-human when its blank input is still
unresolved.

## Decisions required before adding licence files

1. Daniela Patiño-Vélez and Eden Morales-Narváez confirm which materials they
   created and whether UNAM, a funder, collaborator, or laboratory also holds
   relevant rights.
2. The authors confirm that no instrument-vendor, collaborator, or third-party
   dataset terms restrict redistribution of the exported spectra or metadata.
3. The authors confirm that the maintained code was not materially copied from
   historical scripts whose authors have not authorised relicensing.
4. Human-data governance is resolved as documented in
   `HUMAN_DATA_GOVERNANCE.md`.
5. A path-level licence notice explicitly states any exclusions; a top-level
   licence must not imply that excluded human data are openly licensed.
6. `CITATION.cff`, README wording, package metadata, and the eventual DOI archive
   are updated consistently with the chosen licences.

Useful licence texts and guidance:

- [MIT License](https://opensource.org/license/mit)
- [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/)
- [GitHub guidance on licensing a repository](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository)
- [RSC open-access information](https://www.rsc.org/publishing/open-access)
