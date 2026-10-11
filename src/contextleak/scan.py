"""Orchestration: walk the context, apply .dockerignore, trace COPY/ADD."""
from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass, field

from .dockerfile import CopyInstruction, parse_dockerfile
from .dockerignore import IgnoreMatcher
from .sensitive import classify


@dataclass
class Finding:
    instruction: CopyInstruction
    files: list[tuple[str, str]]  # (context-relative path, reason)


@dataclass
class Warning:
    line: int
    message: str


@dataclass
class ScanResult:
    context_files: int
    ignored_files: int
    instructions: list[CopyInstruction] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    warnings: list[Warning] = field(default_factory=list)


def _walk_context(root: str) -> list[str]:
    rels: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        # Never treat the .dockerignore / Dockerfile themselves as findings,
        # but they do travel in the context. Keep them; classify() won't flag.
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            rels.append(rel)
    return rels


def _glob_match(pattern: str, rel: str) -> bool:
    """Docker COPY glob semantics: pattern is context-root anchored."""
    pat = pattern.strip()
    while pat.startswith("./"):
        pat = pat[2:]
    pat = pat.lstrip("/")
    if pat in ("", "."):
        return True  # "COPY .": the whole context
    if not any(c in pat for c in "*?["):
        # Plain path: matches the file itself, or everything under a directory.
        return rel == pat or rel.startswith(pat.rstrip("/") + "/")
    return fnmatch.fnmatchcase(rel, pat)


def scan(
    context_dir: str,
    dockerfile_path: str | None = None,
    ignore_file: str | None = None,
) -> ScanResult:
    root = os.path.abspath(context_dir)
    if not os.path.isdir(root):
        raise FileNotFoundError(f"not a directory: {context_dir}")

    dockerfile = dockerfile_path or os.path.join(root, "Dockerfile")
    with open(dockerfile, "r", encoding="utf-8", errors="replace") as fh:
        parsed = parse_dockerfile(fh.read())

    matcher = IgnoreMatcher.from_file(
        ignore_file or os.path.join(root, ".dockerignore")
    )

    all_files = _walk_context(root)
    included = [f for f in all_files if not matcher.is_excluded(f)]
    included_set = set(included)

    result = ScanResult(
        context_files=len(all_files),
        ignored_files=len(all_files) - len(included),
        instructions=parsed.instructions,
    )

    for ins in parsed.instructions:
        if ins.from_stage:
            continue  # copies from a previous stage, not from the build context
        leaked: list[tuple[str, str]] = []
        for src in ins.sources:
            if src.startswith(("http://", "https://", "git@", "github.com")):
                continue  # ADD of a remote URL: nothing from the local context
            hits = [f for f in included if _glob_match(src, f)]
            if not hits:
                # The instruction names something dockerignore (or absence) removed.
                missing = [f for f in all_files if _glob_match(src, f)]
                if missing:
                    result.warnings.append(
                        Warning(
                            line=ins.line,
                            message=(
                                f"{ins.kind} {src!r} matches only files excluded "
                                "by .dockerignore (or missing) — the build would "
                                "fail or copy nothing"
                            ),
                        )
                    )
                continue
            for f in sorted(hits):
                reason = classify(f)
                if reason:
                    leaked.append((f, reason))
        if leaked:
            # De-duplicate while preserving order.
            seen: set[str] = set()
            uniq = [(f, r) for f, r in leaked if not (f in seen or seen.add(f))]
            result.findings.append(Finding(instruction=ins, files=uniq))
    return result
