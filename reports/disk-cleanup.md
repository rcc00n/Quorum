# Targeted disk audit and cleanup — 2026-10-21

Protected period: 2026-04-21 through today. One targeted audit covered Linux home/cache roots, Linux temporary directories, package caches, Docker images/cache/container references, Ollama's list and shallow Windows Downloads/temp listings. No personal-file contents or recursive Windows filesystem scan was needed.

## Exact before/after cleanup measurements

Measurements are from the same WSL filesystem immediately around the deletion, **after** extraction of the new platform. The initial audit before extraction reported 116,911,996,928 used bytes and 909,196,824,576 available bytes; extraction and normal activity explain the small difference before deletion.

| Measurement | Before cleanup | After cleanup |
|---|---:|---:|
| Used bytes | 116,943,491,072 (108.912 GiB) | 111,543,541,760 (103.883 GiB) |
| Available bytes | 909,165,330,432 (846.726 GiB) | 914,565,279,744 (851.755 GiB) |

**Available space gained: 5,399,949,312 bytes (5.029 GiB, approximately 5.40 GB).** Removed objects held 5,399,873,112 logical bytes / 5,399,953,408 allocated bytes. Filesystem changes can differ slightly from summed object sizes due to metadata and concurrent normal activity.

## Ranked candidates and protection decisions

Sizes below are pre-cleanup estimates; Docker shared-layer/cache figures overlap and must not be added together.

| Path / component | Size | Last modified / used | Safe to remove? | Expected recovery / action |
|---|---:|---|---|---|
| Docker images | 28 GB total; Docker labels 22 GB reclaimable | Mixed; unreferenced examples include 2026-05-28 and 2026-09-24 | No automatic cleanup: other environments/protected dates | 0 removed; 16 distinct images referenced by running **or stopped** containers preserved |
| Docker build cache | 20.39 GB; ~10.44 GB reported reclaimable | Includes entries created/last used 11 months ago; mixed shared entries | Requires approval and environment assessment | 0 removed; no blind prune |
| `~/.cache/pip/http` + `http-v2` | 7.176 GB logical | Mixed 2024–2026; newest 2026-09-24 / 2026-07-07 | Only individually age-verified disposable entries | **5.40 GB recovered** from selected large old objects/pairs; recent entries retained |
| `~/.local/lib` | ~7.00 GB allocated | Mixed; current installed dependencies | Preserve | 0 |
| `~/.vscode-server` | ~6.18 GB allocated | Mixed; remote tooling | Preserve working development access | 0 |
| `~/.cache/ms-playwright` | ~5.32 GB logical | Newest 2026-09-22; mixed older versions | Preserve current browser/test dependencies; age alone insufficient | 0 |
| `~/.npm/_cacache` | ~3.32 GB logical | Newest 2026-10-21 local time; mixed older entries | Current/recent entries protected; no broad cache clean | 0 removed; ~2.23 GB old metadata-eligible objects were not needed for the selected cleanup |
| `~/.gradle/caches` | ~0.537 GB logical | Newest 2025-03-12 | Old, but offline/build reuse uncertain; preserved | 0 |
| `~/.npm/_npx` | ~0.298 GB logical | Newest 2026-05-20 | Mixed current tooling; preserved | 0 |
| `~/.cache/pip-tools/http-v2` | ~0.070 GB logical | Newest 2025-09-25 | Rebuildable but smaller; left untouched after large selected cleanup | 0 |
| `/var/cache/apt/archives` | ~0.018 GB | Packages include 2026-10-21 | Recent protected cache packages | 0 |
| `/tmp`, `/var/tmp` | ~0.0024 GB regular files / no regular-file data | No age-eligible old regular-file content found | Preserve active/recent files; no verified abandoned build target | 0 |
| pnpm/yarn caches | No separate conventional cache found in targeted roots | — | No expansion of scan/deletion | 0 |

The `docker builder du` detail command was unavailable because the existing buildx plugin path is missing. No plugin was installed. `docker system df -v` supplied cache metadata instead. All 19 existing containers and 22 volumes were preserved; no database, running/stopped-container data, project, coursework, credential or personal file was removed.

## Exact cleanup targets

Only recognized pip HTTP cache object paths were deleted, not installed packages. Each file was a nonsymlink, single-link regular file whose **mtime, ctime and atime were all before 2026-04-21 UTC**. Ctime additionally protects recently created/copied files with old preserved mtime. V2 body/header pairs were removed only when both were old. Metadata/inode/device/size were rechecked immediately before unlink. No active pip/npm/yarn/pnpm operation was detected. Selected bodies were at least 100 MiB; small headers were removed only with their matching bodies. No broad `cache clean` was used.

| Exact removed path | Logical bytes | Last modified UTC |
|---|---:|---|
| `/home/raccoon/.cache/pip/http/5/d/f/8/5/5df858e76c1d399f758a0903abaee9a45a3fc2ad17cf3de552731274` | 797,223,543 | 2024-08-15 |
| `/home/raccoon/.cache/pip/http-v2/5/d/f/8/5/5df858e76c1d399f758a0903abaee9a45a3fc2ad17cf3de552731274.body` | 797,222,373 | 2024-08-17 |
| `/home/raccoon/.cache/pip/http-v2/5/d/f/8/5/5df858e76c1d399f758a0903abaee9a45a3fc2ad17cf3de552731274` | 1,159 | 2024-08-17 |
| `/home/raccoon/.cache/pip/http/3/c/8/2/7/3c827aae7500e30cec6930647f8971adb3eafb1cd65a44fcf02ba940` | 664,753,952 | 2024-08-15 |
| `/home/raccoon/.cache/pip/http-v2/3/c/8/2/7/3c827aae7500e30cec6930647f8971adb3eafb1cd65a44fcf02ba940.body` | 664,752,741 | 2024-08-17 |
| `/home/raccoon/.cache/pip/http-v2/3/c/8/2/7/3c827aae7500e30cec6930647f8971adb3eafb1cd65a44fcf02ba940` | 1,203 | 2024-08-17 |
| `/home/raccoon/.cache/pip/http/3/9/a/e/6/39ae6aa825aebb75b0193714975cbc9defffa90203c5342f2214137e` | 410,595,985 | 2024-08-15 |
| `/home/raccoon/.cache/pip/http-v2/3/9/a/e/6/39ae6aa825aebb75b0193714975cbc9defffa90203c5342f2214137e.body` | 410,594,774 | 2024-08-17 |
| `/home/raccoon/.cache/pip/http-v2/3/9/a/e/6/39ae6aa825aebb75b0193714975cbc9defffa90203c5342f2214137e` | 1,201 | 2024-08-17 |
| `/home/raccoon/.cache/pip/http/d/4/c/3/e/d4c3ec899ac2836a7f89ffad88e243bf35b92f56ff0b61ad0f5badf5` | 209,353,476 | 2024-08-15 |
| `/home/raccoon/.cache/pip/http-v2/d/4/c/3/e/d4c3ec899ac2836a7f89ffad88e243bf35b92f56ff0b61ad0f5badf5.body` | 209,352,266 | 2024-08-17 |
| `/home/raccoon/.cache/pip/http-v2/d/4/c/3/e/d4c3ec899ac2836a7f89ffad88e243bf35b92f56ff0b61ad0f5badf5` | 1,199 | 2024-08-17 |
| `/home/raccoon/.cache/pip/http/6/e/f/7/a/6ef7ae373253a3997ffc8ac7b70e67716f79d6365ffa5c28f40f349a` | 195,959,497 | 2024-08-15 |
| `/home/raccoon/.cache/pip/http-v2/6/e/f/7/a/6ef7ae373253a3997ffc8ac7b70e67716f79d6365ffa5c28f40f349a.body` | 195,958,278 | 2024-08-17 |
| `/home/raccoon/.cache/pip/http-v2/6/e/f/7/a/6ef7ae373253a3997ffc8ac7b70e67716f79d6365ffa5c28f40f349a` | 1,210 | 2024-08-17 |
| `/home/raccoon/.cache/pip/http/d/8/8/d/f/d88df6fd35db2b3889f6d022cc638ec172d9b07105a54f437fef17ab` | 176,250,625 | 2024-08-15 |
| `/home/raccoon/.cache/pip/http-v2/d/8/8/d/f/d88df6fd35db2b3889f6d022cc638ec172d9b07105a54f437fef17ab.body` | 176,249,402 | 2024-08-17 |
| `/home/raccoon/.cache/pip/http-v2/d/8/8/d/f/d88df6fd35db2b3889f6d022cc638ec172d9b07105a54f437fef17ab` | 1,211 | 2024-08-17 |
| `/home/raccoon/.cache/pip/http/d/d/8/8/4/dd884c1d55d2bfa13200f58081e79f3f708e7f1df45f78c917300cd7` | 124,163,147 | 2024-08-15 |
| `/home/raccoon/.cache/pip/http-v2/d/d/8/8/4/dd884c1d55d2bfa13200f58081e79f3f708e7f1df45f78c917300cd7.body` | 124,161,928 | 2024-08-17 |
| `/home/raccoon/.cache/pip/http-v2/d/d/8/8/4/dd884c1d55d2bfa13200f58081e79f3f708e7f1df45f78c917300cd7` | 1,210 | 2024-08-17 |
| `/home/raccoon/.cache/pip/http/b/e/4/8/c/be48c6af34ce9a2c153618ab623be22a96ef71c547ea2621dbcd141a` | 121,636,372 | 2024-08-15 |
| `/home/raccoon/.cache/pip/http-v2/b/e/4/8/c/be48c6af34ce9a2c153618ab623be22a96ef71c547ea2621dbcd141a.body` | 121,635,161 | 2024-08-17 |
| `/home/raccoon/.cache/pip/http-v2/b/e/4/8/c/be48c6af34ce9a2c153618ab623be22a96ef71c547ea2621dbcd141a` | 1,199 | 2024-08-17 |

## Ollama: every installed model preserved

Removed models: **none**. No `ollama rm`, blob deletion, service restart or configuration change was performed. `ollama list` remains reachable for offline use; `ollama ps` initially showed no loaded model.

Preserved exact names:

- `qwen3:8b` — required exam model, protected regardless of age.
- `gpt2.5-reversed:latest`
- `huihui_ai/qwen2.5-coder-abliterate:7b` (shares the same model ID as the preceding alias).
- `dolphin-llama3:latest`
- `nomic-embed-text:latest`
- `deepseek-r1:8b`
- `deepseek-coder-v2:16b`

`qwen3.5:9b` was not installed; nothing was downloaded or substituted. Other models were shown as modified three months ago, inside the protected period, so none was considered disposable.

## Windows: read-only candidates, approval required

No Windows file was deleted or application/setting changed. The largest recent dataset, photo archive and video in Downloads were treated as protected personal/user data, not removal targets; their names are omitted from this public report.

Only these obvious older installer files are potential review candidates, **not approved deletions**:

| Exact Windows path | Bytes | Last modified | Decision / potential recovery |
|---|---:|---|---|
| `C:\Users\Vadim\Downloads\mysql-workbench-community-8.0.46-winx64.msi` | 261,623,808 | 2026-02-13 | Ask approval first; ~249.5 MiB if no longer needed |
| `C:\Users\Vadim\Downloads\UbisoftConnectInstaller.exe` | 259,065,496 | 2026-01-09 | Ask approval first; ~247.1 MiB if no longer needed |

Unknown archives, university ZIPs, new Zetaris installer, all user data and Windows application/profile directories were preserved. No AppData/Program Files modifications or WSL VHD compaction/reset was performed. Reclaiming Linux blocks does **not** guarantee immediate reduction of the Windows-hosted virtual disk file; disk cleanup also does not increase available RAM.
