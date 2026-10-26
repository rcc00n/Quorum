#!/usr/bin/env bash
# One live run of one topic-day with key rotation, by hand: starts the run on the first key and, whenever it stops with
# exit 3 (route drained), resumes it (--resume) on the next key. Stops at exit 0, at any other exit code, or when the
# keys run out. For several topics at once use scripts/run_editions.py (dry checks, budgets, status files).
#
#   bash reasoning/scripts/resume_with_next_key.sh --topic climate-policy --date 2026-10-26 \
#        [--attempt 1] [--out reasoning/snapshots/_private] [--log FILE] \
#        [--keys MODEL_API_KEY,MODEL_API_KEY_2,MODEL_API_KEY_3] [--resume] \
#        [--env-file .env] [--python PATH] [--workdir reasoning] [-- --quiet|--verbose|--checkpoint]
#
#   # a run started elsewhere on MODEL_API_KEY drained (exit 3): continue it on the next keys
#   bash reasoning/scripts/resume_with_next_key.sh --topic russia-ukraine-war --date 2026-10-24 --attempt 7 \
#        --resume --keys MODEL_API_KEY_2,MODEL_API_KEY_3
#
# --keys lists environment variable NAMES; each value is read at the moment of its run, exported first, else from the
# repo-level .env (python-dotenv, as llm._env reads it), or --env-file. The child gets MODEL_API_KEY = that value,
# MODEL_BASE_URL = the URL the route check passed, and every other key variable blank, so one process holds one key;
# nothing from .env is printed, and the child's output passes through a filter that replaces the key value with
# [redacted] before it reaches the log. The script runs the child itself and
# reads its exit code directly. Exit 0 when a run published, 3 when every listed key drained, 2 a refusal (also when
# MODEL_BASE_URL is not NVIDIA's direct route), the run's code otherwise.
#
# DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): key rotation lives in an operator script, not in llm.py.
# Why: the per-account daily budget is an operator concern (whose key, how many), the running process must not
# hold several accounts' keys, and a resume from the checkpoint + replay journal loses nothing between keys.
# DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): the script takes topic, date, attempt, out, log, the key names and
# extra run.py arguments, starts the first run itself and reads each run's exit code, instead of waiting for a
# "live exit=N" line in a fixed log. Why: run.py never prints that line, so the old script waited forever; it also
# hardcoded russia-ukraine-war 2026-10-24, snapshots/_private and the _2 -> _3 order.
# DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): the run's subshell sets MODEL_API_KEY and the blanks with the
# `export` builtin and then execs Python; no external `env` program is used. Why: /usr/bin/env took them as arguments
# and, under Git Bash, stayed alive as the run's parent for hours with the key readable in its process command line.
# DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): after `--` only --quiet, --verbose and --checkpoint pass through,
# spelled exactly; anything else is refused (exit 2). Why: run.py's parser takes unique prefixes (argparse allow_abbrev),
# so refusing exact spellings let `--ou X`, `--corp fixture`, `--att 9` or `--res` override the managed arguments (the
# last value wins), and the check modes replace the run and exit 0, which this script reports as a published run
# (--test-connection and --probe even send paid completions on the injected key). Supersedes the list of refused names.
# DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): before any run the script refuses (exit 2) unless MODEL_BASE_URL,
# exported or else from the env file (read like the keys), is NVIDIA's direct route by llm._is_direct_url. Why: it hands
# each key to the run as MODEL_API_KEY, which only that route uses (the runner refuses the same in run_editions.main); on
# the Meterless route the first exit 3 sent MODEL_API_KEY_2, an NVIDIA key, as the bearer to the Meterless daemon, and
# Meterless drains per account, not per key, so rotating there gains nothing.
# DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): the URL that passed the check is exported as MODEL_BASE_URL in
# each run's subshell, next to MODEL_API_KEY. Why: the run's llm._env loads the repository's .env with
# load_dotenv(override=False), so with --env-file naming another file the check read that file's NVIDIA URL while the
# run took the repository's Meterless URL and sent each NVIDIA key as the bearer to the Meterless daemon (closing
# review round 2); an exported value is one load_dotenv never replaces.
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
[[ "$TOPIC" =~ ^[a-z0-9][a-z0-9-]{0,63}$ ]] || { echo "--topic must follow the shared topic-id rule ^[a-z0-9][a-z0-9-]{0,63}\$" >&2; exit 2; }
# no Windows device name (decision at run_editions.topic_id_problem); the rule above already refuses upper case and
# the superscript digits, so the lower-case ASCII forms are all that can reach this line
if [[ "$TOPIC" =~ ^(con|prn|aux|nul|com[0-9]|lpt[0-9])$ ]]; then
  echo "--topic may not be a Windows reserved device name (con, prn, aux, nul, com0-9, lpt0-9)" >&2; exit 2
fi
[[ "$DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "--date must be YYYY-MM-DD" >&2; exit 2; }
[[ "$ATTEMPT" =~ ^[1-9][0-9]*$ ]] || { echo "--attempt must be a positive integer" >&2; exit 2; }
for arg in ${EXTRA[@]+"${EXTRA[@]}"}; do  # decision at the top: exact spellings only
  case "$arg" in
    --quiet|--verbose|--checkpoint) ;;
    *) shown="(not echoed)"; [[ "$arg" =~ ^--?[A-Za-z][A-Za-z0-9-]*$ ]] && shown="$arg"
       echo "extra run.py argument $shown is not passed through: after -- only --quiet, --verbose and --checkpoint are allowed" \
            "(the script manages topic, date, attempt, out, model, corpus and resume; check modes are no run)" >&2; exit 2 ;;
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

# the direct NVIDIA route only (decision at the top); the URL reaches Python through its environment, and each run gets
# this same URL exported (decision at the top)
BASE_URL="$(key_value MODEL_BASE_URL)"
QUORUM_CHECK_BASE_URL="$BASE_URL" "$PY" -c 'import os, sys
sys.path.insert(0, sys.argv[1])
from quorum_reasoning import llm
base = os.environ.get("QUORUM_CHECK_BASE_URL", "").strip()
sys.exit(0 if base and llm._is_direct_url(base) else 3)' "$REASONING" 2>/dev/null
route=$?
if [ "$route" != 0 ]; then
  if [ "$route" = 3 ]; then
    echo "refusing to run: MODEL_BASE_URL (exported or in the env file) is not NVIDIA's direct route (integrate.api.nvidia.com);" \
         "this script hands each key to the run as MODEL_API_KEY, which only that route uses (on the Meterless route run run.py itself)" >&2
  else
    echo "refusing to run: could not check MODEL_BASE_URL (quorum_reasoning.llm did not import from $REASONING with $PY)" >&2
  fi
  exit 2
fi

# every key variable is blank in the child (one key per process): the listed names and any MODEL_API_KEY_* known here
BLANK_NAMES=()
for name in "${KEY_NAMES[@]}" $(compgen -e | grep -E '^MODEL_API_KEY_[A-Za-z0-9_]+$' || true) \
            $( [ -f "$ENVFILE" ] && grep -oE '^MODEL_API_KEY_[A-Za-z0-9_]+' "$ENVFILE" || true ); do
  BLANK_NAMES+=("$name")
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
  # builtins only between the key and Python: nothing carries the value on a command line (decision at the top)
  ( cd "$WORKDIR" || exit 1
    for n in "${BLANK_NAMES[@]}"; do export "$n="; done
    export MODEL_API_KEY="$key" MODEL_BASE_URL="$BASE_URL" PYTHONUNBUFFERED=1
    exec "$PY" -X utf8 -m quorum_reasoning.run \
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
