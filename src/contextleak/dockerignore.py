"""Simulate Docker's .dockerignore matching (Go filepath.Match semantics).

Rules (matching Docker's documented behavior):
- Patterns are anchored to the build-context root (unlike .gitignore).
- ``*`` matches any sequence of non-separator characters; ``**`` matches any
  sequence including separators; ``?`` matches one non-separator char.
- Lines starting with ``!`` negate (re-include) a previous match.
- Blank lines and ``#`` comments are ignored; ``\\#`` / ``\\!`` escape the
  first character.
- A pattern matching a directory excludes everything beneath it.
- The LAST matching pattern decides.
"""
from __future__ import annotations

import os
import re


def _translate(pattern: str) -> str:
    """Translate one anchored dockerignore pattern into a regex string."""
    out: list[str] = []
    i, n = 0, len(pattern)
    while i < n:
        ch = pattern[i]
        if ch == "*":
            if i + 1 < n and pattern[i + 1] == "*":
                j = i + 2
                while j < n and pattern[j] == "/":
                    j += 1
                # "**/" matches zero or more directories; trailing "**" matches all
                out.append("(?:.*/)?" if j > i + 2 else ".*")
                i = j
            else:
                out.append("[^/]*")
                i += 1
        elif ch == "?":
            out.append("[^/]")
            i += 1
        elif ch == "[":
            j = i + 1
            if j < n and pattern[j] in ("!", "^"):
                j += 1
            if j < n and pattern[j] == "]":
                j += 1
            while j < n and pattern[j] != "]":
                j += 1
            if j < n:
                cls = pattern[i + 1 : j].replace("!", "^", 1) if pattern[i + 1 : i + 2] == "!" else pattern[i + 1 : j]
                out.append("[" + cls + "]")
                i = j + 1
            else:
                out.append(re.escape(ch))
                i += 1
        else:
            out.append(re.escape(ch))
            i += 1
    return "".join(out)


class IgnoreMatcher:
    """Compiled .dockerignore patterns with Docker's last-match-wins rule."""

    def __init__(self, lines: list[str]) -> None:
        self._rules: list[tuple[bool, re.Pattern[str]]] = []
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            negate = False
            if line.startswith("\\") and len(line) > 1 and line[1] in ("#", "!"):
                line = line[1:]
            elif line.startswith("!"):
                negate = True
                line = line[1:].strip()
            if not line:
                continue
            # Trailing slashes carry no meaning in dockerignore; strip them.
            line = line.rstrip("/") or "/"
            try:
                rx = re.compile(_translate(line) + r"\Z")
            except re.error:
                continue
            self._rules.append((negate, rx))

    @classmethod
    def from_file(cls, path: str) -> "IgnoreMatcher":
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError:
            lines = []
        return cls(lines)

    def is_excluded(self, rel: str) -> bool:
        """True if ``rel`` (context-relative, '/' separators) is ignored."""
        rel = rel.replace(os.sep, "/").lstrip("/")
        result = False
        for negate, rx in self._rules:
            hit = rx.match(rel) is not None
            if not hit:
                parent = os.path.dirname(rel)
                while parent:
                    if rx.match(parent):
                        hit = True
                        break
                    parent = os.path.dirname(parent)
            if hit:
                result = not negate
        return result
