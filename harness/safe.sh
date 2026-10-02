#!/bin/bash
# Run a heavy job inside a memory-capped cgroup so an overrun kills the job, not the machine.
# usage: harness/safe.sh <command...>     (cap from SAFE_MEM, default 8G)
exec systemd-run --user --scope -q -p MemoryMax="${SAFE_MEM:-8G}" -p MemorySwapMax=0 "$@"
