"""Report rendering: human-readable text and JSON."""
from __future__ import annotations

import json

from .scan import Finding, ScanResult


def render_text(result: ScanResult) -> str:
    lines: list[str] = []
    lines.append(
        f"Scanned {result.context_files} files in build context "
        f"({result.ignored_files} excluded by .dockerignore), "
        f"{len(result.instructions)} COPY/ADD instruction(s)."
    )
    lines.append("")
    if not result.findings:
        lines.append("OK: no sensitive files would be copied into the image.")
    else:
        lines.append(f"LEAK: {len(result.findings)} instruction(s) would copy sensitive files:")
        for finding in result.findings:
            ins = finding.instruction
            lines.append("")
            lines.append(f"  [{ins.kind} line {ins.line}] {ins.raw}  (stage: {ins.stage})")
            for path, reason in finding.files:
                lines.append(f"    - {path}  ({reason})")
    if result.warnings:
        lines.append("")
        lines.append("Warnings:")
        for w in result.warnings:
            lines.append(f"  line {w.line}: {w.message}")
    return "\n".join(lines)


def render_json(result: ScanResult) -> str:
    payload = {
        "context_files": result.context_files,
        "ignored_files": result.ignored_files,
        "findings": [
            {
                "kind": f.instruction.kind,
                "line": f.instruction.line,
                "stage": f.instruction.stage,
                "instruction": f.instruction.raw,
                "files": [{"path": p, "reason": r} for p, r in f.files],
            }
            for f in result.findings
        ],
        "warnings": [{"line": w.line, "message": w.message} for w in result.warnings],
    }
    return json.dumps(payload, indent=2)
