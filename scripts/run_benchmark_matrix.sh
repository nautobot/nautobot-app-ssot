#!/usr/bin/env bash
# scripts/run_benchmark_matrix.sh
#
# One-stop validation: tear down the dev stack, rebuild it, run all
# migrations, then run the full benchmark matrix. Designed for the host
# (uses `invoke` to exec into the dev container).
#
# Usage:
#   ./scripts/run_benchmark_matrix.sh             # default: tiny, small, medium
#   ./scripts/run_benchmark_matrix.sh tiny small  # subset of scales
#
# WARNING: `invoke destroy` removes the postgres volume — all dev DB
# state is wiped. Re-run only when that's OK.
set -euo pipefail

cd "$(dirname "$0")/.."

SCALES=("$@")

echo "===== [1/4] tearing down existing dev stack ====="
invoke destroy

echo "===== [2/4] building images ====="
invoke build

echo "===== [3/4] starting stack & waiting for migrations ====="
invoke start
# `invoke start` tails until DB is up; nautobot-server runs migrations on container start.
# Give the worker a few extra seconds to fully come online.
sleep 10

echo "===== [4/4] running benchmark matrix ====="
if [ ${#SCALES[@]} -eq 0 ]; then
  invoke exec --command "python scripts/benchmark_infoblox.py --matrix"
else
  invoke exec --command "python scripts/benchmark_infoblox.py --matrix ${SCALES[*]}"
fi

echo
echo "===== matrix complete ====="
echo "Raw JSON results inside the container at /tmp/benchmark_results.json"
echo "Copy it locally with:  invoke exec --command 'cat /tmp/benchmark_results.json' > benchmark_results.json"
