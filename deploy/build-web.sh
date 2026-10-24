#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
build_root=${QUORUM_WEB_BUILD:-$HOME/.local/share/quorum/portal-web-build}
mkdir -p "$build_root"
python3 - "$repo/web" "$build_root" <<'PY'
from pathlib import Path
import shutil,sys
source,dest=(Path(p).resolve() for p in sys.argv[1:])
if dest.is_relative_to(source.parent) or source.is_relative_to(dest):
    raise SystemExit('Build directory must be outside the repository and its parents')
marker=dest/'.quorum-web-build'
if any(dest.iterdir()) and not marker.exists():
    raise SystemExit('Refusing an existing directory without the Quorum build marker')
marker.touch()
for p in source.iterdir():
    if p.name in ('node_modules','.next'): continue
    if p.is_dir():
        if (dest/p.name).exists(): shutil.rmtree(dest/p.name)
        shutil.copytree(p,dest/p.name)
    else: shutil.copy2(p,dest/p.name)
PY
cd "$build_root"
if [[ ! -d node_modules ]] || ! cmp -s package-lock.json .quorum-installed-lock; then
  npm ci --no-audit --no-fund
  cp package-lock.json .quorum-installed-lock
fi
NEXT_TELEMETRY_DISABLED=1 npm run build
npm run typecheck
