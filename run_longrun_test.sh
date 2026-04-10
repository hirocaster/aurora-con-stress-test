#!/usr/bin/env bash
set -euo pipefail

HOST=""
PORT="3306"
USER=""
PASSWORD=""
DATABASE=""
QPS="2000"
DURATION="48h"
WINDOW="10s"
SLEEP_MS="10"
CONCURRENCY="50"
OUTPUT_ROOT="results/db_r8g_xlarge"
RUN_PREFLIGHT="true"

usage() {
  cat <<'EOF'
Usage:
  ./run_longrun_test.sh \
    --host <host> \
    --user <user> \
    --password <password> \
    [--database <database>] \
    [--port 3306] \
    [--qps 2000] \
    [--duration 48h] \
    [--window 10s] \
    [--sleep-ms 10] \
    [--concurrency 50] \
    [--output-root results/db_r8g_xlarge] \
    [--skip-preflight]
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --user) USER="$2"; shift 2 ;;
    --password) PASSWORD="$2"; shift 2 ;;
    --database) DATABASE="$2"; shift 2 ;;
    --qps) QPS="$2"; shift 2 ;;
    --duration) DURATION="$2"; shift 2 ;;
    --window) WINDOW="$2"; shift 2 ;;
    --sleep-ms) SLEEP_MS="$2"; shift 2 ;;
    --concurrency) CONCURRENCY="$2"; shift 2 ;;
    --output-root) OUTPUT_ROOT="$2"; shift 2 ;;
    --skip-preflight) RUN_PREFLIGHT="false"; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$HOST" || -z "$USER" || -z "$PASSWORD" ]]; then
  echo "--host, --user, --password are required"
  usage
  exit 1
fi

if [[ "$RUN_PREFLIGHT" == "true" ]]; then
  echo "[1/5] Running preflight checks"
  ./preflight.sh
fi

echo "[2/5] Building stress-test binary"
go build -o stress-test main.go

RUN_ID="longrun-$(date +%Y%m%d-%H%M%S)-qps${QPS}"
OUTDIR="${OUTPUT_ROOT}/longrun_qps${QPS}_${DURATION}_$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUTDIR"

AGG_LOG="${OUTDIR}/aggregate.jsonl"
ERR_LOG="${OUTDIR}/error.jsonl"
RES_LOG="${OUTDIR}/resources.jsonl"
SUMMARY_JSON="${OUTDIR}/summary.json"
SUMMARY_TXT="${OUTDIR}/summary.txt"

DB_ARGS=()
if [[ -n "$DATABASE" ]]; then
  DB_ARGS+=("-database" "$DATABASE")
fi

echo "[3/5] Starting stress-test"
set +e
./stress-test \
  -host "$HOST" \
  -port "$PORT" \
  -user "$USER" \
  -password "$PASSWORD" \
  "${DB_ARGS[@]}" \
  -concurrency "$CONCURRENCY" \
  -duration "$DURATION" \
  -aggregate_window "$WINDOW" \
  -sleep_between_attempts "${SLEEP_MS}ms" \
  -aggregate_log_path "$AGG_LOG" \
  -error_log_path "$ERR_LOG" \
  -run_id "$RUN_ID" >"${OUTDIR}/stress-test.log" 2>&1 &
STRESS_PID=$!
set -e

echo "[4/5] Starting resource monitor (pid=${STRESS_PID})"
python3 monitor_resources.py \
  --pid "$STRESS_PID" \
  --output "$RES_LOG" \
  --interval 30 \
  --stop-after-exit-seconds 120 >"${OUTDIR}/resource-monitor.log" 2>&1 &
MONITOR_PID=$!

set +e
wait "$STRESS_PID"
STRESS_EXIT=$?
wait "$MONITOR_PID"
MONITOR_EXIT=$?
set -e

echo "[5/5] Running long-run analysis"
python3 analyze_longrun.py "$AGG_LOG" \
  --resources-log "$RES_LOG" \
  --min-success-rate 0.995 \
  --max-throughput-drop-pct 10 \
  --max-p99-increase-pct 10 \
  --window-hours 1 \
  --json-out "$SUMMARY_JSON" | tee "$SUMMARY_TXT"

echo ""
echo "Run directory : $OUTDIR"
echo "Stress exit   : $STRESS_EXIT"
echo "Monitor exit  : $MONITOR_EXIT"

if [[ $STRESS_EXIT -ne 0 ]]; then
  echo "Stress-test failed. Check ${OUTDIR}/stress-test.log"
  exit "$STRESS_EXIT"
fi

if [[ $MONITOR_EXIT -ne 0 ]]; then
  echo "Resource monitor failed. Check ${OUTDIR}/resource-monitor.log"
  exit "$MONITOR_EXIT"
fi

echo "Long-run test completed successfully"
