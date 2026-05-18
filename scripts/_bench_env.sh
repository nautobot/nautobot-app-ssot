#!/usr/bin/env bash
# Helper: exports env vars so benchmark_infoblox.py can run inside a single
# container that has its own postgres + redis running on localhost.
# Source this file (`source scripts/_bench_env.sh`) before running benchmarks.
export NAUTOBOT_DB_HOST=127.0.0.1
export NAUTOBOT_REDIS_HOST=127.0.0.1
export NAUTOBOT_DB_PASSWORD=decinablesprewad
export NAUTOBOT_REDIS_PASSWORD=""
export INVOKE_NAUTOBOT_LOCAL=True
export DJANGO_SETTINGS_MODULE=development.nautobot_config
