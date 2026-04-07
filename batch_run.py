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
    
    print(f"\n🚀 Phase: QPS {qps} - {scenario_name.capitalize()} Case")
    print(f"   Parameters: -concurrency {concurrency}, -sleep_between_attempts {sleep_ms}ms")
    
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
        print(f"❌ Error running stress-test: {e}")
        return

    # Run plot.py
    print(f"📊 Generating plot for {scenario_name}...")
    plot_cmd = [
        "uv", "run", "plot.py",
        os.path.join(results_dir, "aggregate.jsonl"),
        "-o", os.path.join(results_dir, "plot.png")
    ]
    try:
        subprocess.run(plot_cmd, check=True)
        print(f"✅ Success: Results saved in {results_dir}")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Warning: Plot generation failed for {results_dir}")

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
        print(f"Error: QPS file not found: {args.qps_file}")
        return
    
    with open(args.qps_file, 'r') as f:
        for line in f:
            val = line.strip()
            if val:
                try:
                    qps_list.append(int(val))
                except ValueError:
                    print(f"Skipping invalid QPS value: {val}")

    print(f"📋 Loaded {len(qps_list)} QPS targets from {args.qps_file}")

    for i, qps in enumerate(qps_list):
        # Case 1: Healthy (15ms latency, 10ms sleep)
        c_healthy = calculate_concurrency(qps, 15, 10)
        run_test(qps, "healthy", c_healthy, 10, args)

        print(f"⏳ Cooling down for {args.cooldown} seconds...")
        time.sleep(args.cooldown)

        # Case 2: Congested (30ms latency, 30ms sleep)
        c_congested = calculate_concurrency(qps, 30, 30)
        run_test(qps, "congested", c_congested, 30, args)
        
        # 最後のQPSでなければ、次のQPSの前に再度クールダウン
        if i < len(qps_list) - 1:
            print(f"⏳ Cooling down for {args.cooldown} seconds before next QPS target...")
            time.sleep(args.cooldown)

    print("\n✨ All batch tests completed!")

if __name__ == "__main__":
    main()
