"""contextleak: check which sensitive files your Docker build context would leak.

Verifies the *actual* behavior of .dockerignore against the COPY/ADD
instructions in your Dockerfile and reports the sensitive files
(.env, keys, credentials, ...) that would be shipped into the image.
"""
from __future__ import annotations

import argparse
import os
import sys

from .report import render_json, render_text
from .scan import scan

__version__ = "0.1.0"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="contextleak",
        description=(
            "Simulate .dockerignore matching against a Dockerfile's COPY/ADD "
            "instructions and report sensitive files that would leak into the image."
        ),
    )
    p.add_argument(
        "context",
        nargs="?",
        default=".",
        help="build context directory (default: current directory)",
    )
    p.add_argument(
        "-f",
        "--dockerfile",
        default=None,
        help="path to the Dockerfile (default: <context>/Dockerfile)",
    )
    p.add_argument(
        "--ignore-file",
        default=None,
        help="path to the ignore file (default: <context>/.dockerignore)",
    )
    p.add_argument("--json", action="store_true", help="emit JSON instead of text")
    p.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = scan(args.context, args.dockerfile, args.ignore_file)
    except (FileNotFoundError, OSError) as exc:
        print(f"contextleak: error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(render_json(result))
    else:
        print(render_text(result))
    return 1 if result.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
