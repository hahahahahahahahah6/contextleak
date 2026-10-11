"""Smoke tests for contextleak. All fixture secrets are fake."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from contextleak import scan
from contextleak.cli import main as cli_main
from contextleak.dockerignore import IgnoreMatcher

FAKE_ENV = "API_KEY=fake-test-key-123\nDB_PASSWORD=fake-test-password\n"
FAKE_PEM = "-----BEGIN PRIVATE KEY-----\nFAKE\n-----END PRIVATE KEY-----\n"


def make_tree(files: dict[str, str]) -> str:
    root = tempfile.mkdtemp(prefix="contextleak-test-")
    for rel, content in files.items():
        full = os.path.join(root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(content)
    return root


class TestDockerignoreMatcher(unittest.TestCase):
    def test_star_does_not_cross_slash(self):
        m = IgnoreMatcher(["*.env"])
        self.assertTrue(m.is_excluded(".env"))
        self.assertFalse(m.is_excluded("config/.env"))

    def test_doublestar_crosses_slash(self):
        m = IgnoreMatcher(["**/.env"])
        self.assertTrue(m.is_excluded(".env"))
        self.assertTrue(m.is_excluded("config/.env"))
        self.assertTrue(m.is_excluded("a/b/.env"))

    def test_negation_reincludes(self):
        m = IgnoreMatcher(["*.env", "!.env.production"])
        self.assertTrue(m.is_excluded(".env"))
        self.assertFalse(m.is_excluded(".env.production"))

    def test_directory_pattern_excludes_contents(self):
        m = IgnoreMatcher([".git"])
        self.assertTrue(m.is_excluded(".git/HEAD"))
        self.assertTrue(m.is_excluded(".git/objects/ab/cd"))

    def test_last_match_wins(self):
        m = IgnoreMatcher(["!keep.env", "*.env"])
        self.assertTrue(m.is_excluded("keep.env"))
        m2 = IgnoreMatcher(["*.env", "!keep.env"])
        self.assertFalse(m2.is_excluded("keep.env"))


class TestScan(unittest.TestCase):
    def test_env_copied_by_copy_dot(self):
        root = make_tree(
            {
                "Dockerfile": "FROM python:3.12\nCOPY . /app\n",
                ".env": FAKE_ENV,
                "app.py": "print('hi')\n",
            }
        )
        result = scan(root)
        self.assertEqual(len(result.findings), 1)
        paths = [p for p, _ in result.findings[0].files]
        self.assertIn(".env", paths)
        self.assertEqual(cli_exit(root), 1)

    def test_dockerignore_blocks_env(self):
        root = make_tree(
            {
                "Dockerfile": "FROM python:3.12\nCOPY . /app\n",
                ".dockerignore": ".env\n",
                ".env": FAKE_ENV,
                "app.py": "print('hi')\n",
            }
        )
        result = scan(root)
        self.assertEqual(result.findings, [])
        self.assertEqual(cli_exit(root), 0)

    def test_dockerignore_missing_still_leaks(self):
        # .dockerignore exists but ignores the wrong pattern -> leak remains
        root = make_tree(
            {
                "Dockerfile": "FROM node:20\nCOPY . /app\n",
                ".dockerignore": "node_modules\n",
                ".env": FAKE_ENV,
                "server.js": "console.log(1)\n",
            }
        )
        result = scan(root)
        self.assertEqual(len(result.findings), 1)
        self.assertIn(".env", [p for p, _ in result.findings[0].files])

    def test_pem_via_add_directory(self):
        root = make_tree(
            {
                "Dockerfile": "FROM alpine\nADD certs/ /certs/\n",
                "certs/server.pem": FAKE_PEM,
                "certs/README.md": "docs\n",
            }
        )
        result = scan(root)
        self.assertEqual(len(result.findings), 1)
        paths = [p for p, _ in result.findings[0].files]
        self.assertIn("certs/server.pem", paths)

    def test_copy_from_stage_not_flagged(self):
        root = make_tree(
            {
                "Dockerfile": (
                    "FROM golang AS builder\nCOPY . /src\n"
                    "FROM alpine\nCOPY --from=builder /src/app /app\n"
                ),
                ".env": FAKE_ENV,
            }
        )
        result = scan(root)
        # Only the first-stage COPY . (context copy) is a finding; the
        # --from=builder copy must not be treated as a context leak.
        self.assertEqual(len(result.findings), 1)
        self.assertIsNone(result.findings[0].instruction.from_stage)

    def test_git_directory_flagged(self):
        root = make_tree(
            {
                "Dockerfile": "FROM python:3.12\nCOPY . /app\n",
                ".git/HEAD": "ref: refs/heads/main\n",
                "app.py": "print('hi')\n",
            }
        )
        result = scan(root)
        paths = [p for p, _ in result.findings[0].files]
        self.assertIn(".git/HEAD", paths)

    def test_json_output_shape(self):
        root = make_tree(
            {
                "Dockerfile": "FROM python:3.12\nCOPY . /app\n",
                ".env": FAKE_ENV,
            }
        )
        proc = subprocess.run(
            [sys.executable, "-m", "contextleak", "--json", root],
            capture_output=True,
            text=True,
            cwd=os.path.join(os.path.dirname(__file__), ".."),
            env={**os.environ, "PYTHONPATH": os.path.join(os.path.dirname(__file__), "..", "src")},
        )
        payload = json.loads(proc.stdout)
        self.assertIn("findings", payload)
        self.assertEqual(len(payload["findings"]), 1)
        self.assertEqual(payload["findings"][0]["files"][0]["path"], ".env")


def cli_exit(root: str) -> int:
    return cli_main([root])


if __name__ == "__main__":
    unittest.main(verbosity=2)
