#!/bin/bash
# usage: [BOT=path] [SLOT=1] harness/dbg.sh OPP SEED [extra runner args]
# plays BOT (default bots/current.py) with DEBUG on; log in runs/dbg/me.log
set -e
cd "$(dirname "$0")/.."
mkdir -p runs/dbg
sed 's/^DEBUG = False/DEBUG = True/' "${BOT:-bots/current.py}" > runs/dbg/current_dbg.py
OPP=$1; SEED=$2; shift 2
if [ "${SLOT:-0}" = "1" ]; then A="$OPP"; B=runs/dbg/current_dbg.py; L=bot_1; else A=runs/dbg/current_dbg.py; B="$OPP"; L=bot_0; fi
.venv/bin/python harness/runner.py "$A" "$B" --seed "$SEED" --log-dir runs/dbg --move-ms 5000 --record runs/dbg/last.jsonl "$@" | head -9 | tr -d '\n '; echo
cp runs/dbg/$L.stderr.log runs/dbg/me.log
