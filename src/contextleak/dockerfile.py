"""Parse the COPY / ADD instructions of a Dockerfile (multi-stage aware)."""
from __future__ import annotations

import json
import shlex
from dataclasses import dataclass, field


@dataclass
class CopyInstruction:
    kind: str  # "COPY" or "ADD"
    stage: str  # stage name / base image, or "stage-N"
    line: int  # 1-based line number in the Dockerfile
    raw: str
    sources: list[str] = field(default_factory=list)
    dest: str = ""
    from_stage: str | None = None


@dataclass
class ParsedDockerfile:
    instructions: list[CopyInstruction]


def _join_continuations(text: str) -> list[tuple[int, str]]:
    """Join backslash-continued lines; returns (line_number, joined_line)."""
    out: list[tuple[int, str]] = []
    buf = ""
    start = 0
    for lineno, raw in enumerate(text.splitlines(), 1):
        stripped = raw.rstrip()
        if stripped.endswith("\\") and not stripped.endswith("\\\\"):
            if not buf:
                start = lineno
            buf += stripped[:-1] + " "
            continue
        line = (buf + stripped) if buf else raw
        out.append((start or lineno, line))
        buf, start = "", 0
    if buf:
        out.append((start, buf))
    return out


def _parse_sources(tokens: list[str]) -> list[str]:
    """Handle both shell form and JSON-array form sources."""
    if len(tokens) == 1 and tokens[0].lstrip().startswith("["):
        try:
            arr = json.loads(tokens[0])
            if isinstance(arr, list) and all(isinstance(x, str) for x in arr):
                return list(arr)
        except json.JSONDecodeError:
            pass
    return tokens


def parse_dockerfile(text: str) -> ParsedDockerfile:
    instructions: list[CopyInstruction] = []
    stage = "stage-0"
    stage_idx = 0
    for lineno, line in _join_continuations(text):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        try:
            tokens = shlex.split(s, posix=True)
        except ValueError:
            continue
        if not tokens:
            continue
        keyword = tokens[0].upper()
        if keyword == "FROM":
            stage_idx += 1
            rest = tokens[1:]
            name = None
            for i, tok in enumerate(rest):
                if tok.upper() == "AS" and i + 1 < len(rest):
                    name = rest[i + 1]
                    break
            stage = name or f"stage-{stage_idx}"
            continue
        if keyword not in ("COPY", "ADD"):
            continue
        rest = tokens[1:]
        from_stage = None
        args: list[str] = []
        for tok in rest:
            if tok.startswith("--"):
                if tok.startswith("--from="):
                    from_stage = tok[len("--from=") :]
                continue
            args.append(tok)
        if len(args) < 2:
            continue  # malformed; Docker itself would reject it
        sources = _parse_sources(args[:-1])
        instructions.append(
            CopyInstruction(
                kind=keyword,
                stage=stage,
                line=lineno,
                raw=line.strip(),
                sources=sources,
                dest=args[-1],
                from_stage=from_stage,
            )
        )
    return ParsedDockerfile(instructions)
