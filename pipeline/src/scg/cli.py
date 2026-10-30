import argparse
import sys
from pathlib import Path

from scg.validate import validate_extraction


def _validate_extraction(args: argparse.Namespace) -> int:
    failed = False
    for path in args.files:
        report = validate_extraction(Path(path))
        for w in report.warnings:
            print(f"warning: {w}")
        for e in report.errors:
            print(f"error: {e}")
        status = "ok" if report.ok else "FAILED"
        print(f"{path}: {report.records} records, {len(report.errors)} errors -> {status}")
        failed |= not report.ok
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scg")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate data files")
    vsub = validate.add_subparsers(dest="target", required=True)
    ext = vsub.add_parser("extraction", help="validate data/extracted/*.jsonl files")
    ext.add_argument("files", nargs="+")
    ext.set_defaults(func=_validate_extraction)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
