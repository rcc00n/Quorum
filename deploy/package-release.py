#!/usr/bin/env python3
"""Package only portal code and its external standalone build; never repository secrets."""

from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

repo = Path(__file__).resolve().parents[1]
revision = subprocess.check_output(
    ["git", "rev-parse", "HEAD"], cwd=repo, text=True
).strip()
label = sys.argv[1] if len(sys.argv) > 1 else revision[:12]
if not re.fullmatch(r"[a-zA-Z0-9_-]+", label):
    raise SystemExit("Use a simple release label")
root = Path.home() / ".local/share/quorum"
build = root / "portal-web-build/.next"
release = root / "releases" / label
if release.exists():
    raise SystemExit("Release exists; choose a new label")
release.mkdir(parents=True)
shutil.copytree(build / "standalone", release / "web")
shutil.copytree(build / "static", release / "web/.next/static")
shutil.copytree(
    repo / "backend",
    release / "backend",
    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".env*"),
)
shutil.copytree(repo / "deploy", release / "deploy")
(release / "REVISION").write_text(revision + "\n")
archive = root / (label + ".tar.gz")
with tarfile.open(archive, "w:gz") as tar:
    tar.add(release, arcname=label)
print(archive)
