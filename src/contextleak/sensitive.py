"""What counts as a sensitive file: name-based heuristics for secrets."""
from __future__ import annotations

import fnmatch
import os

# (glob pattern, human-readable reason). Patterns match against the basename
# unless they contain a '/', in which case they match the full context path.
SENSITIVE_PATTERNS: list[tuple[str, str]] = [
    (".env", "environment file, usually holds secrets"),
    (".env.*", "environment file, usually holds secrets"),
    ("*.pem", "private key / certificate material"),
    ("*.key", "private key material"),
    ("*.pfx", "private key / certificate bundle"),
    ("*.p12", "private key / certificate bundle"),
    ("*.jks", "Java keystore"),
    ("id_rsa*", "SSH private key"),
    ("id_dsa*", "SSH private key"),
    ("id_ecdsa*", "SSH private key"),
    ("id_ed25519*", "SSH private key"),
    ("*credential*", "file name suggests stored credentials"),
    ("*secret*", "file name suggests stored secrets"),
    ("*token*", "file name suggests stored tokens"),
    (".npmrc", "may embed a registry auth token"),
    (".pypirc", "holds PyPI credentials"),
    ("*.tfvars", "Terraform variables, often contain secrets"),
    ("*.tfstate*", "Terraform state, contains secrets in plaintext"),
    ("kubeconfig*", "Kubernetes cluster credentials"),
    ("*service-account*", "cloud service-account credentials"),
    (".git", "full git history shipped into the image"),
    (".git/*", "full git history shipped into the image"),
]

# Exact basenames that are always sensitive regardless of directory.
SENSITIVE_BASENAMES = {
    ".env",
    ".npmrc",
    ".pypirc",
    ".git",
    "credentials",
    "secrets",
}


def classify(path: str) -> str | None:
    """Return the reason a context-relative path is sensitive, or None."""
    rel = path.replace(os.sep, "/").lstrip("/")
    base = rel.rsplit("/", 1)[-1]
    if base in SENSITIVE_BASENAMES:
        for pattern, reason in SENSITIVE_PATTERNS:
            if "/" not in pattern and fnmatch.fnmatchcase(base, pattern):
                return reason
        return "sensitive file name"
    for pattern, reason in SENSITIVE_PATTERNS:
        target = rel if "/" in pattern else base
        if fnmatch.fnmatchcase(target, pattern):
            return reason
    return None
