import argparse
import math
import subprocess
import os
import shutil
import time

def calculate_concurrency(target_qps, latency_ms, sleep_ms):
    # 1ワーカーあたりの秒間リクエスト数
    req_per_worker = 1000 / (latency_ms + sleep_ms)
    # 必要となるコンカレンシー (切り上げ)
    return math.ceil(target_qps / req_per_worker)

def run_test(qps, scenario_name, concurrency, sleep_ms, args):
    results_dir = f"results/qps{qps}_{scenario_name}"
    os.makedirs(results_dir, exist_ok=True)
    print(f"\n🚀 Phase: QPS {qps} - {scenario_name.capitalize()} Case", flush=True)
    print(f"   Parameters: -concurrency {concurrency}, -sleep_between_attempts {sleep_ms}ms", flush=True)
    
    cmd = [
        "./stress-test",
        "-host", args.host,
        "-user", args.user,
        "-password", args.password,
        "-concurrency", str(concurrency),
        "-sleep_between_attempts", f"{sleep_ms}ms",
        "-duration", args.duration,
        "-aggregate_window", args.window,
        "-aggregate_log_path", os.path.join(results_dir, "aggregate.jsonl"),
        "-error_log_path", os.path.join(results_dir, "error.jsonl")
    ]
    
    # Run the stress test
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Error running stress-test: {e}", flush=True)
        return

    # Run plot.py
    print(f"📊 Generating plot for {scenario_name}...", flush=True)
    plot_cmd = [
        "uv", "run", "plot.py",
        os.path.join(results_dir, "aggregate.jsonl"),
        "-o", os.path.join(results_dir, "plot.png")
    ]
    try:
        subprocess.run(plot_cmd, check=True)
        print(f"✅ Success: Results saved in {results_dir}", flush=True)
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Warning: Plot generation failed for {results_dir}", flush=True)

def main():
    parser = argparse.ArgumentParser(description="Automated Batch Aurora Stress Test Runner")
    parser.add_argument("qps_file", help="File containing list of target QPS (one per line)")
    parser.add_argument("--host", required=True, help="Database host")
    parser.add_argument("--user", required=True, help="Database user")
    parser.add_argument("--password", required=True, help="Database password")
    parser.add_argument("--duration", default="5m", help="Test duration (default: 5m)")
    parser.add_argument("--window", default="10s", help="Aggregate window (default: 10s)")
    parser.add_argument("--cooldown", type=int, default=30, help="Cooldown time between tests in seconds (default: 30)")
    args = parser.parse_args()

    # Read QPS values
    qps_list = []
    if not os.path.exists(args.qps_file):
        print(f"Error: QPS file not found: {args.qps_file}", flush=True)
        return
    
    with open(args.qps_file, 'r') as f:
        for line in f:
            val = line.strip()
            if val:
                try:
                    qps_list.append(int(val))
                except ValueError:
                    print(f"Skipping invalid QPS value: {val}", flush=True)

    print(f"📋 Loaded {len(qps_list)} QPS targets from {args.qps_file}", flush=True)

    scenarios = [
        ("healthy", 15, 10),
        ("congested", 30, 30)
    ]
    
    total_runs = len(qps_list) * len(scenarios)
    run_idx = 0

    for qps in qps_list:
        for scenario_name, lat, slp in scenarios:
            run_idx += 1
            
            # 最初の実行以外は、開始前にクールダウンを挟む
            if run_idx > 1:
                print(f"\n⏳ Waiting {args.cooldown}s for environment to settle before next scenario...", flush=True)
                time.sleep(args.cooldown)
            
            concurrency = calculate_concurrency(qps, lat, slp)
            run_test(qps, scenario_name, concurrency, slp, args)

    print(f"\n✨ All {total_runs} tests completed!", flush=True)

if __name__ == "__main__":
    main()
