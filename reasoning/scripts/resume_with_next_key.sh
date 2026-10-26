#!/usr/bin/env bash
# One live run of one topic-day with key rotation, by hand: starts the run on the first key and, whenever it stops with
# exit 3 (route drained), resumes it (--resume) on the next key. Stops at exit 0, at any other exit code, or when the
# keys run out. For several topics at once use scripts/run_editions.py (dry checks, budgets, status files).
#
#   bash reasoning/scripts/resume_with_next_key.sh --topic climate-policy --date 2026-10-26 \
#        [--attempt 1] [--out reasoning/snapshots/_private] [--log FILE] \
#        [--keys MODEL_API_KEY,MODEL_API_KEY_2,MODEL_API_KEY_3] [--resume] \
#        [--env-file .env] [--python PATH] [--workdir reasoning] [-- <extra run.py arguments, e.g. --quiet>]
#
#   # a run started elsewhere on MODEL_API_KEY drained (exit 3): continue it on the next keys
#   bash reasoning/scripts/resume_with_next_key.sh --topic russia-ukraine-war --date 2026-10-24 --attempt 7 \
#        --resume --keys MODEL_API_KEY_2,MODEL_API_KEY_3
#
# --keys lists environment variable NAMES; each value is read at the moment of its run, exported first, else from the
# repo-level .env (python-dotenv, as llm._env reads it). The child gets MODEL_API_KEY = that value and every other key
# variable blank, so one process holds one key; nothing from .env is printed, and the child's output passes through a
# filter that replaces the key value with [redacted] before it reaches the log. The script runs the child itself and
# reads its exit code directly. Exit 0 when a run published, 3 when every listed key drained, the run's code otherwise.
#
# DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): key rotation lives in an operator script, not in llm.py.
# Why: the per-account daily budget is an operator concern (whose key, how many), the running process must not
# hold several accounts' keys, and a resume from the checkpoint + replay journal loses nothing between keys.
# DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): the script takes topic, date, attempt, out, log, the key names and
# extra run.py arguments, starts the first run itself and reads each run's exit code, instead of waiting for a
# "live exit=N" line in a fixed log. Why: run.py never prints that line, so the old script waited forever; it also
# hardcoded russia-ukraine-war 2026-10-24, snapshots/_private and the _2 -> _3 order.
set -u

usage() { sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REASONING="$ROOT/reasoning"
TOPIC=""; DATE=""; ATTEMPT=1; OUT=""; LOG=""; KEYS="MODEL_API_KEY,MODEL_API_KEY_2,MODEL_API_KEY_3"; RESUME=0
ENVFILE="$ROOT/.env"; PY=""; WORKDIR="$REASONING"; EXTRA=()
while [ $# -gt 0 ]; do
  case "$1" in
    --topic) TOPIC="${2:-}"; shift 2 ;;
    --date) DATE="${2:-}"; shift 2 ;;
    --attempt) ATTEMPT="${2:-}"; shift 2 ;;
    --out) OUT="${2:-}"; shift 2 ;;
    --log) LOG="${2:-}"; shift 2 ;;
    --keys|--next-keys) KEYS="${2:-}"; shift 2 ;;
    --resume) RESUME=1; shift ;;
    --env-file) ENVFILE="${2:-}"; shift 2 ;;
    --python) PY="${2:-}"; shift 2 ;;
    --workdir) WORKDIR="${2:-}"; shift 2 ;;
    --) shift; EXTRA=("$@"); break ;;
    -h|--help) usage ;;
    *) echo "unknown argument: $1 (see --help)" >&2; exit 2 ;;
  esac
done
[ -n "$TOPIC" ] && [ -n "$DATE" ] || { echo "--topic and --date are required (see --help)" >&2; exit 2; }
[[ "$TOPIC" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || { echo "--topic must be a lower-case slug" >&2; exit 2; }
[[ "$DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "--date must be YYYY-MM-DD" >&2; exit 2; }
[[ "$ATTEMPT" =~ ^[1-9][0-9]*$ ]] || { echo "--attempt must be a positive integer" >&2; exit 2; }
for arg in ${EXTRA[@]+"${EXTRA[@]}"}; do
  case "$arg" in
    --topic|--date|--attempt|--out|--model|--corpus|--resume|--seed-journal|--dry-run|--topic=*|--date=*|--attempt=*|--out=*|--model=*|--corpus=*)
      echo "extra run.py argument $arg is managed by this script" >&2; exit 2 ;;
  esac
done
if [ -z "$PY" ]; then
  if [ -x "$REASONING/.venv/Scripts/python.exe" ] || [ -x "$REASONING/.venv/Scripts/python" ]; then PY="$REASONING/.venv/Scripts/python"
  else PY="$REASONING/.venv/bin/python"; fi
fi
OUT="${OUT:-$REASONING/snapshots/_private}"
LOG="${LOG:-$OUT/live_${DATE}_${TOPIC}_attempt${ATTEMPT}.log}"
# Windows paths typed with backslashes (C:\...) work in Git Bash and in Python once written with forward slashes
OUT="${OUT//\\//}"; LOG="${LOG//\\//}"; ENVFILE="${ENVFILE//\\//}"; PY="${PY//\\//}"; WORKDIR="${WORKDIR//\\//}"
# relative to where the script was started, not to --workdir, where the child runs
abs() { case "$1" in /*|[A-Za-z]:/*) printf '%s' "$1" ;; *) printf '%s/%s' "$PWD" "$1" ;; esac; }
OUT="$(abs "$OUT")"; LOG="$(abs "$LOG")"; ENVFILE="$(abs "$ENVFILE")"; WORKDIR="$(abs "$WORKDIR")"
case "$PY" in */*) PY="$(abs "$PY")" ;; esac
"$PY" -c "import dotenv" 2>/dev/null || { echo "no usable Python with python-dotenv at $PY (pass --python)" >&2; exit 2; }
mkdir -p "$(dirname "$LOG")"
IFS=',' read -r -a KEY_NAMES <<< "$KEYS"
[ "${#KEY_NAMES[@]}" -gt 0 ] || { echo "--keys is empty" >&2; exit 2; }
for name in "${KEY_NAMES[@]}"; do
  [[ "$name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || { echo "--keys takes environment variable names" >&2; exit 2; }
done

key_value() {  # name -> value (exported first, else the env file); never echoed by the caller
  local v
  v="$(printenv "$1" 2>/dev/null || true)"
  if [ -z "$v" ] && [ -f "$ENVFILE" ]; then
    v="$("$PY" -c 'import sys
from dotenv import dotenv_values
sys.stdout.write((dotenv_values(sys.argv[1]).get(sys.argv[2]) or "").strip())' "$ENVFILE" "$1" 2>/dev/null)"
  fi
  printf '%s' "$v"
}

# every key variable is blank in the child (one key per process): the listed names and any MODEL_API_KEY_* known here
BLANK=()
for name in "${KEY_NAMES[@]}" $(compgen -e | grep -E '^MODEL_API_KEY_[A-Za-z0-9_]+$' || true) \
            $( [ -f "$ENVFILE" ] && grep -oE '^MODEL_API_KEY_[A-Za-z0-9_]+' "$ENVFILE" || true ); do
  BLANK+=("$name=")
done

# the log filter: the key value (passed in the filter's environment, never on a command line) becomes [redacted]
REDACT='import os, sys
v = os.environ.get("QUORUM_REDACT_VALUE", "").encode()
out = sys.stdout.buffer
for line in sys.stdin.buffer:
    out.write(line.replace(v, b"[redacted]") if len(v) >= 8 else line)
    out.flush()'

stamp() { date -u +%H:%M:%SZ; }
code=3
resume=$RESUME
for name in "${KEY_NAMES[@]}"; do
  key="$(key_value "$name")"
  if [ -z "$key" ]; then
    echo "$(stamp) $name has no value (exported or in the env file): skipped"
    continue
  fi
  flag=(); [ "$resume" = 1 ] && flag=(--resume)
  echo "$(stamp) $TOPIC $DATE attempt $ATTEMPT on $name${flag[*]:+ (resume)}; log $LOG"
  echo "=== $TOPIC $DATE attempt $ATTEMPT on $name${flag[*]:+ (resume)} at $(stamp) ===" >> "$LOG"
  ( cd "$WORKDIR" && env "${BLANK[@]}" "MODEL_API_KEY=$key" PYTHONUNBUFFERED=1 "$PY" -X utf8 -m quorum_reasoning.run \
      --topic "$TOPIC" --date "$DATE" --model live --corpus zetaris --out "$OUT" --attempt "$ATTEMPT" --verbose \
      ${flag[@]+"${flag[@]}"} ${EXTRA[@]+"${EXTRA[@]}"} 2>&1 ) | QUORUM_REDACT_VALUE="$key" "$PY" -c "$REDACT" >> "$LOG"
  code=${PIPESTATUS[0]}
  echo "live exit=$code ($name)" >> "$LOG"
  echo "$(stamp) run on $name ended with exit $code"
  [ "$code" = "3" ] || break
  resume=1
done
if [ "$code" = "3" ]; then
  echo "$(stamp) every listed key is drained or empty; rerun with --resume once a key has rested (>= 6 h)"
fi
echo "$(stamp) final exit $code"
exit "$code"
