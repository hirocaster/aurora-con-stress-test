#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$SCRIPT_DIR}"
OUT_FILE="${OUT_FILE:-longrun.out}"
LINES="${LINES:-30}"

usage() {
  cat <<'EOF'
Usage:
  ./check_longrun_status.sh [--repo-dir <path>] [--out <file>] [--lines <n>]

Environment variables:
  REPO_DIR  Repository directory (default: ~/aurora-con-stress-test)
  OUT_FILE  Runner output log file (default: longrun.out)
  LINES     Tail line count (default: 30)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-dir) REPO_DIR="$2"; shift 2 ;;
    --out) OUT_FILE="$2"; shift 2 ;;
    --lines) LINES="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ ! -d "$REPO_DIR" ]]; then
  echo "ERROR: repo dir not found: $REPO_DIR"
  exit 1
fi

cd "$REPO_DIR"

echo "============================================================"
echo "Long-run Status Check @ $(date -Is)"
echo "Host: $(hostname)"
echo "Repo: $PWD"
echo "============================================================"

echo "[1] Process health"
RUNNER_PIDS=$(pgrep -f "run_longrun_test.sh" || true)
STRESS_PIDS=$(pgrep -f "./stress-test .* -duration 48h" || true)
MONITOR_PIDS=$(pgrep -f "monitor_resources.py" || true)

if [[ -n "$RUNNER_PIDS" ]]; then
  echo "  run_longrun_test.sh : UP (pid: ${RUNNER_PIDS//$'\n'/, })"
else
  echo "  run_longrun_test.sh : DOWN"
fi

if [[ -n "$STRESS_PIDS" ]]; then
  echo "  stress-test         : UP (pid: ${STRESS_PIDS//$'\n'/, })"
else
  echo "  stress-test         : DOWN"
fi

if [[ -n "$MONITOR_PIDS" ]]; then
  echo "  monitor_resources   : UP (pid: ${MONITOR_PIDS//$'\n'/, })"
else
  echo "  monitor_resources   : DOWN"
fi

echo ""
echo "[2] Latest long-run directory"
LATEST_DIR=$(ls -td results/db_r8g_xlarge/longrun_qps* 2>/dev/null | head -n 1 || true)
if [[ -z "$LATEST_DIR" ]]; then
  echo "  No long-run result directory found yet."
  echo ""
  echo "[3] Tail of $OUT_FILE"
  if [[ -f "$OUT_FILE" ]]; then
    tail -n "$LINES" "$OUT_FILE"
  else
    echo "  Log file not found: $OUT_FILE"
  fi
  exit 0
fi

echo "  $LATEST_DIR"

AGG="$LATEST_DIR/aggregate.jsonl"
ERR="$LATEST_DIR/error.jsonl"
RES="$LATEST_DIR/resources.jsonl"

echo ""
echo "[3] Data freshness"
python3 - "$AGG" "$ERR" "$RES" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone

agg, err, res = sys.argv[1], sys.argv[2], sys.argv[3]


def read_last_jsonl(path):
    if not os.path.exists(path):
        return None
    last = None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            last = line
    if not last:
        return None
    try:
        return json.loads(last)
    except json.JSONDecodeError:
        return None


def count_lines(path):
    if not os.path.exists(path):
        return 0
    n = 0
    with open(path, "r", encoding="utf-8") as f:
        for _ in f:
            n += 1
    return n


agg_last = read_last_jsonl(agg)
res_last = read_last_jsonl(res)
err_lines = count_lines(err)
agg_lines = count_lines(agg)
res_lines = count_lines(res)

print(f"  aggregate lines  : {agg_lines}")
print(f"  error lines      : {err_lines}")
print(f"  resource lines   : {res_lines}")

if agg_last:
    ts = agg_last.get("bucket_end") or agg_last.get("bucket_start")
    succ = agg_last.get("overall_success_rate")
    tps = agg_last.get("throughput_per_sec")
    p99 = agg_last.get("total_p99_ms")
    if succ is not None:
        succ = f"{float(succ) * 100:.4f}%"
    print("  latest aggregate :")
    print(f"    ts             : {ts}")
    print(f"    success        : {succ}")
    print(f"    throughput     : {tps}")
    print(f"    total_p99_ms   : {p99}")

if res_last:
    print("  latest resource  :")
    print(f"    ts             : {res_last.get('timestamp')}")
    print(f"    rss_mb         : {((res_last.get('rss_kb') or 0) / 1024):.2f}")
    print(f"    tcp_tw         : {res_last.get('tcp_tw')}")
    print(f"    open_fds       : {res_last.get('open_fds')}")

# freshness check for latest aggregate bucket end
if agg_last and (agg_last.get("bucket_end") or agg_last.get("bucket_start")):
    ts_text = agg_last.get("bucket_end") or agg_last.get("bucket_start")
    try:
        ts = datetime.fromisoformat(ts_text.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        lag = (now - ts).total_seconds()
        print(f"  aggregate lag(s) : {lag:.1f}")
        if lag > 120:
            print("  WARN: aggregate update looks stale (>120s)")
    except Exception:
        pass
PY

echo ""
echo "[4] Tail of $OUT_FILE"
if [[ -f "$OUT_FILE" ]]; then
  tail -n "$LINES" "$OUT_FILE"
else
  echo "  Log file not found: $OUT_FILE"
fi

echo ""
echo "Done."
