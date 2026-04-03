import json
import argparse
import sys
from datetime import datetime

def main():
    parser = argparse.ArgumentParser(description="Analyze Aurora stress test aggregate logs")
    parser.add_argument("log_file", help="Path to the JSON Lines aggregate log file")
    parser.add_argument("--errors-only", action="store_true", help="Only show buckets with errors/failures")
    parser.add_argument("--latency-threshold", type=int, help="Only show buckets where Total p99 latency (ms) exceeds this value")
    args = parser.parse_args()

    print("=" * 70)
    print("AURORA STRESS TEST AGGREGATE ANALYSIS REPORT")
    print("=" * 70)

    try:
        with open(args.log_file, 'r') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    stats = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                # Check filters
                overall_rate = stats.get('overall_success_rate', 0) * 100
                tot_p99 = stats.get('total_p99_ms', 0)

                if args.errors_only and overall_rate == 100.0:
                    continue
                
                if args.latency_threshold is not None and tot_p99 <= args.latency_threshold:
                    continue

                start_ts = stats.get('bucket_start', '')
                end_ts = stats.get('bucket_end', '')
                try:
                    dt = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
                    time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    time_str = start_ts
                
                attempts = stats.get('attempts', 0)
                overall_rate = stats.get('overall_success_rate', 0) * 100
                conn_rate = stats.get('connect_success_rate', 0) * 100
                tps = stats.get('throughput_per_sec', 0)
                
                conn_p90 = stats.get('connect_p90_ms', 0)
                conn_p99 = stats.get('connect_p99_ms', 0)
                query_p90 = stats.get('query_p90_ms', 0)
                query_p99 = stats.get('query_p99_ms', 0)
                tot_p90 = stats.get('total_p90_ms', 0)
                tot_p99 = stats.get('total_p99_ms', 0)

                print(f"[{time_str}] Attempts: {attempts:<5} | TPS: {tps:>6.1f} | Overall Success: {overall_rate:>6.2f}% | Conn Success: {conn_rate:>6.2f}%")
                print(f"    Latency (ms) p90/p99 -> Conn: {conn_p90}/{conn_p99} | Query: {query_p90}/{query_p99} | Total: {tot_p90}/{tot_p99}")
                
                failures = stats.get('failure_phase_counts', {})
                if failures:
                    print(f"    Failures: {failures}")
                
                errors = stats.get('error_type_counts', {})
                if errors:
                    # truncate long error messages
                    short_errors = {k[:50] + ('...' if len(k)>50 else ''): v for k, v in errors.items()}
                    print(f"    Errors:   {short_errors}")
                
                print("-" * 70)
                
    except FileNotFoundError:
        print(f"Error: Log file not found: {args.log_file}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze.py <aggregate_log.jsonl>")
        sys.exit(1)
    main()
