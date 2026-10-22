#!/usr/bin/env bash
set -euo pipefail
pin=1742dec56a66e58eef9dda2d2b865823758ca8cd
runtime="$(realpath -m -- "${METERLESS_HOME:-$HOME/.local/share/quorum/meterless}")"
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
case "$runtime/" in "$repo_root/"*) echo 'FAIL vendor checkout must be outside Quorum'; exit 1;; esac
if [[ ! -d "$runtime/.git" ]]; then
  git clone --filter=blob:none --sparse --no-checkout https://github.com/Meterless/Meterless.git "$runtime"
  git -C "$runtime" sparse-checkout set engines/hmem/reference engines/world-model/reference
  git -C "$runtime" checkout --detach "$pin"
fi
[[ "$(git -C "$runtime" remote get-url origin)" == https://github.com/Meterless/Meterless.git ]] || { echo 'FAIL unexpected vendor origin'; exit 1; }
[[ "$(git -C "$runtime" rev-parse HEAD)" == "$pin" ]] || { echo 'BLOCKED existing vendor checkout differs from pinned revision'; exit 2; }
cd -- "$runtime/engines/hmem/reference"
if [[ -x node_modules/.bin/tsx && -x node_modules/.bin/vitest ]]; then
  printf 'PASS existing Meterless reference dependencies reused\n'
  exit 0
fi
# Preserve a generated lock on subsequent installs. No install hooks, models or servers.
if [[ -f package-lock.json ]]; then
  npm ci --ignore-scripts --no-audit --no-fund
else
  npm install --ignore-scripts --no-audit --no-fund --save-exact tsx@4.23.0 vitest@2.1.9
fi
printf 'PASS Meterless reference dependencies installed outside Quorum\n'
