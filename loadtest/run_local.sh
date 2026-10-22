#!/usr/bin/env bash
# 本機 / CI 壓測：Firestore emulator + gunicorn（LINE_DRY_RUN=1）+ locust headless
# 用法：USERS=50 DURATION=2m RECORDS_PER_USER=200 ./loadtest/run_local.sh
set -euo pipefail
cd "$(dirname "$0")/.."

USERS="${USERS:-30}"
DURATION="${DURATION:-60s}"
RECORDS_PER_USER="${RECORDS_PER_USER:-200}"
EMULATOR_PORT="${EMULATOR_PORT:-8681}"
APP_PORT="${APP_PORT:-8090}"
OUT=loadtest/out
mkdir -p "$OUT"

export FIRESTORE_EMULATOR_HOST="localhost:$EMULATOR_PORT"
export GOOGLE_CLOUD_PROJECT="demo-sleep-bot-loadtest"
export LINE_CHANNEL_SECRET="loadtest-secret"
export LINE_CHANNEL_ACCESS_TOKEN="loadtest-token"
export LINE_DRY_RUN=1
export LOADTEST_USERS="$USERS"
export RECORDS_PER_USER

pids=()
cleanup() { for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done; }
trap cleanup EXIT

gcloud emulators firestore start --host-port="localhost:$EMULATOR_PORT" > "$OUT/emulator.log" 2>&1 &
pids+=($!)
for _ in $(seq 1 60); do curl -sf "http://localhost:$EMULATOR_PORT" > /dev/null && break; sleep 1; done

python loadtest/seed.py

# 與 Dockerfile 相同的 gunicorn 設定
gunicorn --bind "127.0.0.1:$APP_PORT" --workers 1 --threads 8 --timeout 0 app:app > "$OUT/app.log" 2>&1 &
pids+=($!)
for _ in $(seq 1 30); do curl -sf "http://127.0.0.1:$APP_PORT/" > /dev/null && break; sleep 1; done

locust -f loadtest/locustfile.py --headless \
  --host "http://127.0.0.1:$APP_PORT" \
  --users "$USERS" --spawn-rate "$USERS" --run-time "$DURATION" \
  --csv "$OUT/result" --html "$OUT/report.html" --only-summary
