# Contributing data corrections

Corrections are welcome, especially when they improve the link between a
prepared spectrum and its original instrument export. Scientific identity must
not be inferred from similarity alone.

For a data correction, provide:

1. the affected repository-relative path and its SHA-256 checksum;
2. the original instrument-export path or laboratory-record identifier;
3. sample type, concentration in mol L-1, replicate/disc, scan or accumulation,
   instrument, acquisition date, and acquisition setting;
4. whether the change corrects metadata only or replaces numerical values; and
5. a short reason and the name of the person confirming the laboratory record.

Do not overwrite a quarantined file. Add a verified replacement, update the
manifest, and keep the previous checksum in the provenance record. Generated
outputs must be recreated by the current command-line pipeline; do not edit
processed intensities manually.

For code changes, add or update a test and run:

```text
python -m pip install -e ".[test]"
python -m pytest
```

The data and code licences are intentionally pending author confirmation. A
contribution does not change that status.
