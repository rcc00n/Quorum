# Computer performance maintenance — 2026-10-21

The user authorized broader performance cleanup, then explicitly approved offline WSL VHD compaction and a temporary interruption of existing containers/WSL after saving work. Personal data, coursework, models, databases and volumes remain protected.

## Completed online actions

- Disabled only three current-user startup entries: WallpaperEngine, the GoogleChromeAutoLaunch entry and MicrosoftEdgeAutoLaunch entry. Original registry values and a targeted restoration script are private outside Git under `~/.local/share/quorum/performance-backups/20261022T020504Z/`. Other autoruns, security/audio services and personal-file synchronization were preserved.
- Registry readback confirmed all three targeted startup entries absent. This changes automatic startup, not installed apps or user files.
- A persistent Chrome background-mode policy could not be written: Windows returned UnauthorizedAccessException. No successful policy change is claimed; no registry permission/security bypass was attempted. Existing settings remain otherwise intact.
- Requested non-forced termination of background Chrome with no visible windows. The native command did not fully succeed; no `/F` or Stop-Process was used. Observed process count went from 16 to 12 and working set from 1,571,495,936 to 1,016,557,568 bytes, without attributing all concurrent changes solely to the request.
- Ran supported online filesystem TRIM as root inside the existing WSL distro. It completed successfully without deleting files or restarting workloads. The reported 896.9 GiB is the range of unused virtual blocks, **not Windows disk space recovered**. C: free space did not materially increase.

## Measurements before offline maintenance

| Metric | Before online work | After online work |
|---|---:|---:|
| Windows available bytes | 4,643,598,336 | 5,049,139,200 |
| Windows committed bytes | 20,854,292,480 | 20,339,351,552 |
| Windows commit utilization | 75% | 73% |
| C: free bytes | 20,732,207,104 | 20,730,482,688 |
| C: total bytes | 510,757,171,200 | unchanged |

These are snapshots affected by ordinary concurrent activity, not a controlled benchmark. SSD reports Healthy/OK. A short CPU sample found developer tools and diagnostic PowerShell activity; no persistent runaway CPU/disk load was established. Power mode was already maximum performance and was not changed. Extra virtual memory is disk-backed commit capacity, not additional physical RAM.

## Approved offline work

The Ubuntu VHD file is 129,487,601,664 bytes (~120.6 GiB); Linux used approximately 104 GiB, so a portion of the difference may be reclaimable. Exact recovery is not promised. Existing TRIM did not automatically shrink the non-sparse Windows file. Optimize-VHD is unavailable; native DiskPart is available but needs Windows elevation/UAC.

The reviewable `scripts/windows-maintenance.ps1` requires explicit -Apply and elevation. It snapshots all container states and restart policies to a private Windows-local folder, disables restart policies temporarily, stops only initially running containers with unlimited graceful-stop time (no forced timeout kill), syncs Linux, shuts down WSL, checks no distro restarted, attaches the VHD read-only, compacts/detaches, then restarts Docker and restores the exact originally running container IDs and restart policies. Its final status/log must be inspected before claiming success. A container snapshot is configuration evidence, not a backup of all persistent data. No data or volume deletion is part of this procedure.

**Offline result: pending.** The script is prepared/validated; a completed status, actual VHD size/free-space comparison and restored workload verification are still required. UAC must be accepted by the user on Windows. No Windows reboot or WSL memory-limit increase is included.
