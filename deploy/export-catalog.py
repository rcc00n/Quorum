#!/usr/bin/env python3
"""Export a reviewed team-branch registry to an external, read-only portal catalog."""

import ast
import csv
import io
import json
from pathlib import Path
import subprocess
import sys

ref, destination = sys.argv[1:]
root = Path(__file__).resolve().parents[1]
output = Path(destination).expanduser().resolve()
if output.is_relative_to(root):
    raise SystemExit("Catalog runtime data must stay outside the public repository")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=root, text=True)


revision = git("rev-parse", "--verify", ref).strip()
module = ast.parse(git("show", f"{revision}:collectors/run.py"))
topics = next(
    ast.literal_eval(node.value)
    for node in module.body
    if isinstance(node, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == "TOPICS" for t in node.targets)
)
sources = []
for row in csv.DictReader(
    io.StringIO(git("show", f"{revision}:collectors/sources.csv"))
):
    source = {key: row[key] for key in ("id", "name", "domain")}
    for key in ("allsides", "mbfc", "adfontes", "audience"):
        source[key] = float(row[key]) if row[key] else None
    sources.append(source)
catalog = {
    "revision": revision,
    "topics": [{"id": key, "name": value["name"]} for key, value in topics.items()],
    "sources": sources,
}
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(catalog, indent=2) + "\n")
print(
    f"Exported {len(topics)} topic definitions and {len(sources)} source definitions from {revision}; no operational readiness asserted"
)
