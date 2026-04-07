import argparse
import math

def suggest(target_qps, latency_ms):
    print(f"--- Suggestion for {target_qps} QPS (Assumed Latency: {latency_ms}ms) ---")
    
    # 試行するスリープ時間の候補 (ms)
    sleep_options = [10, 20, 30, 50]
    
    for sleep in sleep_options:
        # 1ワーカーあたりの秒間リクエスト数
        req_per_worker = 1000 / (latency_ms + sleep)
        
        # 必要となるコンカレンシー
        concurrency = math.ceil(target_qps / req_per_worker)
        
        # 実際に出るであろう理論値
        actual_qps = req_per_worker * concurrency
        
        print(f"Option (Sleep {sleep:2}ms): -concurrency {concurrency:<3}  (Theory: {actual_qps:.1f} QPS)")

def main():
    parser = argparse.ArgumentParser(description="Suggest stress-test parameters for a target QPS")
    parser.add_argument("qps", type=int, help="Target QPS (e.g. 2000)")
    args = parser.parse_args()

    # パターン1: 健康時 (応答が早い)
    suggest(args.qps, latency_ms=15)
    print()
    # パターン2: 混雑時 (応答が少し遅れる)
    suggest(args.qps, latency_ms=30)
    
    print("\n[Tip]")
    print(" - If you want zero errors, choose a configuration from the 'Congested' pattern.")
    print(" - If the Aurora limit is lower than your target QPS, you will see timeouts regardless of parameters.")

if __name__ == "__main__":
    main()
