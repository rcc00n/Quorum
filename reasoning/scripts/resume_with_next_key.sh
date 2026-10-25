#!/usr/bin/env bash
# Waits for a live run to end; when it stopped with exit 3 (route drained), resumes it with the next API key.
#
#   bash reasoning/scripts/resume_with_next_key.sh <attempt> [<log path>]
#
# Keys are read from the repo-level .env at the moment of each swap: MODEL_API_KEY_2, MODEL_API_KEY_3, ...
# (the run itself started on MODEL_API_KEY). An exported MODEL_API_KEY wins over .env because llm._env() loads
# the file with override=False. Nothing from .env is ever printed. Exit 0 when a resume published (exit 0), exit 3
# when every key was drained, the run's own code otherwise.
#
# DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): key rotation lives in an operator script, not in llm.py.
# Why: the per-account daily budget is an operator concern (whose key, how many), the running process must not
# hold several accounts' keys, and a resume from the checkpoint + replay journal loses nothing between keys.
set -u
ATTEMPT="${1:?attempt number}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REASONING="$ROOT/reasoning"
LOG="${2:-$REASONING/snapshots/_private/live_2026-10-24_attempt${ATTEMPT}.log}"
PY="$REASONING/.venv/Scripts/python"
ENVFILE="$ROOT/.env"

key_value() {  # name -> value from .env, empty when missing; never echoed by the caller
  grep -E "^$1=" "$ENVFILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\r'
}

wait_for_exit() {  # the run appends "live exit=N" when it ends
  until grep -q -E "^live exit=" "$LOG" 2>/dev/null; do sleep 20; done
  grep -E "^live exit=" "$LOG" | tail -1 | sed -E 's/^live exit=([0-9]+).*/\1/'
}

code="$(wait_for_exit)"
echo "$(date -u +%H:%M:%SZ) run ended with exit $code"
n=2
while [ "$code" = "3" ]; do
  key="$(key_value "MODEL_API_KEY_$n")"
  if [ -z "$key" ]; then
    echo "$(date -u +%H:%M:%SZ) no MODEL_API_KEY_$n in .env: every listed key is drained; stopping (exit 3)"
    exit 3
  fi
  echo "$(date -u +%H:%M:%SZ) resuming attempt $ATTEMPT with key #$n"
  echo "=== resume with key #$n at $(date -u +%H:%M:%SZ) ===" >> "$LOG"
  ( cd "$REASONING" && MODEL_API_KEY="$key" "$PY" -X utf8 -m quorum_reasoning.run --topic russia-ukraine-war --date 2026-10-24 \
      --corpus zetaris --model live --verbose --checkpoint --attempt "$ATTEMPT" --resume --out "$REASONING/snapshots/_private" >> "$LOG" 2>&1 )
  code=$?
  echo "live exit=$code (resume with key #$n)" >> "$LOG"
  echo "$(date -u +%H:%M:%SZ) resume with key #$n ended with exit $code"
  n=$((n + 1))
done
echo "$(date -u +%H:%M:%SZ) final exit $code"
exit "$code"
