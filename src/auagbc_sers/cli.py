"""Command-line interface used by the repository-level process_raman.py."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .errors import RamanPipelineError
from .io import inspect_spectrum_file
from .pipeline import process_job, verify_run
from .profiles import PROFILE_NAMES, get_profile


def _json_dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def _inspect(args: argparse.Namespace) -> int:
    target = Path(args.path).expanduser().resolve()
    if not target.exists():
        raise RamanPipelineError(f"Inspection path does not exist: {target}")
    if target.is_file():
        paths = [target]
    else:
        iterator = target.rglob("*.csv") if not args.no_recursive else target.glob("*.csv")
        paths = sorted(iterator, key=lambda path: path.relative_to(target).as_posix().casefold())
    results = []
    errors = []
    for path in paths:
        try:
            item = inspect_spectrum_file(path)
            if target.is_dir():
                item["file"] = path.relative_to(target).as_posix()
            results.append(item)
        except RamanPipelineError as exc:
            errors.append(
                {
                    "file": path.relative_to(target).as_posix() if target.is_dir() else str(path),
                    "error": str(exc),
                }
            )
    report = {
        "inspection_root": str(target),
        "csv_files_scanned": len(paths),
        "spectrum_files": len(results),
        "non_spectrum_or_invalid_files": len(errors),
        "files": results,
        "errors": errors,
    }
    rendered = _json_dump(report)
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        print(f"Inspection report written to {output}")
    else:
        print(rendered, end="")
    return 1 if args.strict and errors else 0


def _process(args: argparse.Namespace) -> int:
    run = process_job(
        args.config_or_manifest,
        output_root=args.output,
        input_root=args.input_root,
        profile_name=args.profile,
        force=args.force,
    )
    for warning in run.get("warnings", []):
        print(f"WARNING: {warning}", file=sys.stderr)
    summary = {
        "status": run["status"],
        "run_id": run["run_id"],
        "output_root": run["runtime_output_root"],
        "profile": run["configuration"]["profile"],
        "counts": run["counts"],
        "provenance": str(Path(run["runtime_output_root"]) / "run.json"),
    }
    print(_json_dump(summary), end="")
    return 0


def _verify(args: argparse.Namespace) -> int:
    report = verify_run(
        args.run_json,
        input_root=args.input_root,
        verify_inputs=not args.outputs_only,
    )
    print(_json_dump(report), end="")
    return 0


def _profiles(_args: argparse.Namespace) -> int:
    report = {name: get_profile(name) for name in PROFILE_NAMES}
    print(_json_dump(report), end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="process_raman.py",
        description=(
            "Inspect, process, and checksum-verify Raman/SERS spectra without deriving scientific identity from filenames."
        ),
        epilog=(
            "Manifest CSV columns: file, sample_type, concentration_molar, replicate, accumulation, instrument, and "
            "acquisition are required (concentration/acquisition cells may be explicitly empty). file must be relative "
            "to input_root. Optional intensity_column selects one wide-data column; otherwise every usable intensity "
            "column is expanded. Optional baseline_lambda overrides a profile per row. All other columns are preserved "
            "as metadata. For archive runs, include record_group and group blank/grid/aggregation by it."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Detect spectrum structure and preserved vendor metadata without processing.",
    )
    inspect_parser.add_argument("path", help="Spectrum CSV or directory to inspect recursively.")
    inspect_parser.add_argument("--no-recursive", action="store_true", help="Inspect only CSVs directly in a directory.")
    inspect_parser.add_argument("--strict", action="store_true", help="Return a non-zero status if any CSV is not a spectrum.")
    inspect_parser.add_argument("--output", help="Optional JSON report path; stdout is used otherwise.")
    inspect_parser.set_defaults(handler=_inspect)

    process_parser = subparsers.add_parser(
        "process",
        aliases=["run", "batch"],
        help="Run a YAML/JSON job or an archive-wide CSV manifest.",
    )
    process_parser.add_argument("config_or_manifest", help="Job YAML/JSON or spectrum manifest CSV.")
    process_parser.add_argument("--output", help="Override output_root (required for a direct CSV manifest).")
    process_parser.add_argument("--input-root", help="Override input_root; manifest file paths remain relative to it.")
    process_parser.add_argument("--profile", choices=PROFILE_NAMES, help="Override profile (required for direct CSV).")
    process_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite this run's named outputs in a non-empty folder; unrelated files are never deleted.",
    )
    process_parser.set_defaults(handler=_process)

    verify_parser = subparsers.add_parser("verify", help="Recalculate SHA-256 checksums recorded in run.json.")
    verify_parser.add_argument("run_json", help="run.json or the run directory containing it.")
    verify_parser.add_argument("--input-root", help="New input root if the repository was moved after processing.")
    verify_parser.add_argument("--outputs-only", action="store_true", help="Do not check source/configuration files.")
    verify_parser.set_defaults(handler=_verify)

    profiles_parser = subparsers.add_parser("profiles", help="Print all resolved built-in profile parameters.")
    profiles_parser.set_defaults(handler=_profiles)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except RamanPipelineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
