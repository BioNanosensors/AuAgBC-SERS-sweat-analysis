# controlled_legacy_confirmed_blank

This controlled package uses the confirmed blank with the recovered legacy_individual chain. Comparing it with the preserved historical outputs isolates the blank-only effect.

`spectra_scan.csv.gz` contains every processed scan in long form. `processed_spectra.zip` contains 200 two-column CSV members. The resolved manifest paths refer to members inside that ZIP. Aggregates, peaks, the processing report, and source metadata remain directly readable. `run.json` is omitted because it contains execution timestamps and an OS-specific platform string. `package_metadata.json` retains the exact Python/dependency versions, code-file hashes, deterministic method and count metadata, run-level warnings, per-record warning counts, and captured numerical-library warnings.
