# Windows / WSL2 / Docker memory diagnosis — 2026-10-21

## Outcome and the action actually performed

With explicit user approval, one Chrome window received the normal `CloseMainWindow()` request. It returned success. No process was forcibly killed. The browser continued releasing resources afterward: 32 processes initially, 20 immediately after closure, 16 at the final sample, with no remaining main windows. Background Chrome processes were preserved. No other application, container, database, antivirus or Ollama service was stopped/restarted. No files/models were deleted and no kernel cache was manually dropped.

| Measurement | Before | Immediately after graceful close | Final sample |
|---|---:|---:|---:|
| Windows available physical bytes | 977,637,376 (0.910 GiB) | 4,042,682,368 (3.765 GiB) | 4,930,535,424 (4.592 GiB) |
| Windows committed bytes | 26,086,223,872 | 21,942,460,416 | 20,736,712,704 |
| Windows commit limit bytes | 27,624,009,728 | 27,624,009,728 | 27,624,009,728 |
| Windows commit utilization | 94% | 79% | 75% |
| WSL available bytes | 4,871,458,816 (4.537 GiB) | 4,837,900,288 | 4,897,783,808 (4.561 GiB) |

Windows available physical memory increased by **3.681 GiB**. This is an observed difference, not a guaranteed amount attributable solely to a working-set sum; normal concurrent activity also occurs. Windows and WSL available memory are different accounting views and **must not be added**.

## Hardware and Windows consumers

DIMM capacity: **17,179,869,184 bytes = 16 GiB installed**. Windows usable physical total: 16,969,424,896 bytes = 15.804 GiB. Initial available physical memory was only 0.910 GiB and commit 94%, so adding several GiB of committed JVM heap was unsafe even though Linux had reclaimable cache.

Initial Chrome aggregate: **6,457,155,584 bytes = 6.014 GiB working set**, private/committed allocation 7,080,177,664 bytes = 6.594 GiB. Initial vmmemWSL: 4,503,810,048 bytes = 4.194 GiB working set, 8,490,504,192 bytes private allocation. Private memory is not equivalent to resident physical RAM. Summed working sets can include shared pages; neither sum is a precise physical-memory budget.

Immediately after close, Chrome still held 2,808,676,352 working-set bytes (2.616 GiB), Code 1,085,313,024 bytes (1.011 GiB), ChatGPT 923,176,960 bytes (0.860 GiB), vmmemWSL 4,471,959,552 bytes (4.165 GiB). No Docker Desktop/com.docker process appeared in the process-group query; the existing Linux Engine remains in use. Pagefile allocation at the final sample was 10,161 MiB, usage 7,536 MiB, historical peak 8,690 MiB; no pagefile setting was changed.

Initial top 20 Windows processes by working set (exact bytes, before approved Chrome closure):

| PID | Process | Working-set bytes | Private-memory bytes |
|---:|---|---:|---:|
| 7672 | vmmemWSL | 4,503,810,048 | 8,490,504,192 |
| 17812 | chrome | 824,856,576 | 958,869,504 |
| 5792 | chrome | 535,924,736 | 458,010,624 |
| 11748 | Code | 474,009,600 | 543,518,720 |
| 10924 | chrome | 470,745,088 | 469,368,832 |
| 2200 | chrome | 434,524,160 | 356,540,416 |
| 11276 | chrome | 338,518,016 | 320,360,448 |
| 15436 | chrome | 320,516,096 | 223,059,968 |
| 4808 | MsMpEng | 317,472,768 | 456,134,656 |
| 7064 | ChatGPT | 310,788,096 | 435,490,816 |
| 15528 | chrome | 307,781,632 | 451,178,496 |
| 15264 | chrome | 301,338,624 | 228,487,168 |
| 3872 | chrome | 295,313,408 | 317,501,440 |
| 12968 | chrome | 294,187,008 | 288,837,632 |
| 2132 | chrome | 270,430,208 | 335,990,784 |
| 18348 | chrome | 252,424,192 | 362,033,152 |
| 16156 | ChatGPT | 220,315,648 | 329,711,616 |
| 15248 | explorer | 218,353,664 | 280,555,520 |
| 15304 | chrome | 200,073,216 | 296,583,168 |
| 15948 | Telegram | 191,021,056 | 607,727,616 |

## Linux: application memory versus cache

WSL 3.0.1.0 / kernel 6.18.40.1, Ubuntu-20.04 WSL2. Docker/guest total memory: 8,223,322,112 bytes = **7.659 GiB**, 8 CPUs. No `.wslconfig` exists. Observed default VM allocation is approximately half the host RAM; this is a cap, not a reservation of physically resident RAM.

Initial Linux usage was about 2.9 GiB plus about 4.6 GiB buffers/cache. `/proc/meminfo` showed 2,501,976 KiB anonymous pages, 1,249,316 KiB buffers, 2,667,424 KiB cached pages and 927,372 KiB reclaimable slab. `MemAvailable` already estimates what applications can use after appropriate reclaim. Manual cache dropping would not create RAM and could slow existing workloads; it was not used.

Top Linux RSS included clamd 978,276 KiB, MainThread 323,324 KiB, Codex 271,056 KiB, MainThread 175,804 KiB, celery 148,220 KiB, gunicorn 141,236 KiB. RSS can share pages and should not be summed as unique RAM. These are existing workloads, not disposable task-owned tests.

Swap: /dev/sdc, 2 GiB; approximately 6,028 KiB used at the samples, with zero swap-in/swap-out in the short vmstat sample. Guest pressure PSI avg10/avg60/avg300 was zero; root/container cgroups showed no OOM kills. Root memory.current (~7.36 GB during the sample) includes file cache; memory.max/high/swap.max were unlimited within the VM. Container memory.current similarly includes cached files and differs from Docker's cache-adjusted stats.

## Existing Docker workloads preserved

All nine running containers have no explicit Docker memory/CPU cap (Memory=0, MemorySwap=0, NanoCPUs=0); they share the VM's real limit. Cgroup-v2 memory.max was max and OOM counters were zero. No settings were changed, since imposing limits could affect live applications.

| Container | Cache-adjusted docker stats memory | CPU at sample |
|---|---:|---:|
| infra-clamav-1 | 968.8 MiB | 0.01% |
| infra-api-1 | 252.7 MiB | 0.28% |
| infra-worker-1 | 251.3 MiB | 0.19% |
| morent-backend-1 | 133.3 MiB | 0.01% |
| car_rental_tool-db-1 | 43.96 MiB | 0.00% |
| morent-postgres-1 | 38.29 MiB | 0.00% |
| morent-nginx-1 | 10.5 MiB | 0.00% |
| infra-redis-1 | 9.438 MiB | 0.85% |
| morent-frontend-1 | 1.715 MiB | 0.00% |

Sum approximately 1,710 MiB / 1.670 GiB, excluding Docker daemon/host tooling and some cache accounting. ClamAV is the largest container consumer and a security component; it was not disabled. Low CPU does not prove a database/worker is disposable. All 19 running/stopped containers and persistent volumes remain intact. Docker image/build-cache sizes are disk usage, not RAM; no pruning was performed.

`ollama ps` was empty: no loaded model could be safely unloaded for material RAM recovery. Model files and offline availability remain unchanged. Task-owned diagnostic subprocesses exited normally; no persistent test process remained to kill.

## WSL configuration decision

**Do not increase the cap or restart WSL now.** The VM is not currently under Linux memory pressure, and the vendor minimum already passes. Giving it 9–12 GiB would allow greater competition with Windows without creating physical RAM. The earlier suggestion that 9 GiB was needed to pass a strict 8 GiB threshold is superseded by inspection of the actual bundle: its hard minimum is 6 GiB, recommendation 8 GiB.

A review-only [wslconfig.proposed](../docs/wslconfig.proposed) retains approximately the current allocation: memory=8GB, processors=8, swap=2GB. It is **not installed**, needs no current-file backup because `.wslconfig` is absent, and is not recommended as an immediate fix. Before any future installation, recheck and back up an existing file if one appears; a separate WSL restart approval would be required. More swap can absorb exceptional pressure but is slower disk-backed memory and is not a substitute for RAM; the current Linux swap is barely used, so no change is justified.

[Microsoft documentation](https://learn.microsoft.com/en-us/windows/wsl/wsl-config) states the default memory cap is 50% of host RAM; .wslconfig changes apply at VM startup, so shutdown interrupts all running distributions. Its current documented autoMemoryReclaim default is dropCache, with gradual/disabled alternatives. No explicit override exists here; effective internal automatic policy was not independently queried. Leave existing automatic behavior alone; no claim that manual reclaim or a configuration edit improved this result.

## Zetaris readiness and exact next action

The actual official bundle remains at `~/.local/share/quorum/zetaris-platform-bundle/zetaris-platform`. It documents ~3 GiB measured idle, default driver 2g/API 1g, minimum 6 GiB VM memory, recommended 8 GiB and 4 CPUs. Existing 8 CPUs and 7.659 GiB pass required CPU/memory checks (memory WARN). Static UI/REST/JDBC ports 3000/8888/8889/10000/4040 were free; occupied 5432 remains unrelated and the bundle uses an auto-assigned localhost PostgreSQL host port.

The official preflight actually ran after approved optimization: Docker/Compose/architecture/CPU/disk PASS, memory WARN, Azure Registry login FAIL. No registry pull/start was attempted. Linux has no hidden container/cgroup memory limit blocking it, but final available guest memory is **4.561 GiB**, below Quorum's separate conservative **5 GiB** startup-headroom gate. Windows now has **4.592 GiB** free, above the 4 GiB host gate. The host pressure improved substantially, but a reliable local startup is not yet certified, and local safeguards were not bypassed.

Next: obtain private Azure registry authentication and at least another ~0.44 GiB available guest headroom (or perform a separately reviewed startup-budget change based on measured runtime). Do not restart WSL or stop existing workloads to force this. If workloads cannot yield enough headroom safely, use an already-authorized sponsor-hosted Zetaris instance; no paid resource was created. Background Chrome processes are not forcibly terminated under the approved graceful-close action. No further disruptive action is authorized or necessary to apply an ineffective larger WSL cap.
