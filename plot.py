import json
import argparse
import sys
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

def main():
    parser = argparse.ArgumentParser(description="Plot Aurora stress test aggregate logs")
    parser.add_argument("log_file", help="Path to the JSON Lines aggregate log file")
    parser.add_argument("--output", "-o", default="stress_test_plot.png", help="Output image file name (default: stress_test_plot.png)")
    args = parser.parse_args()

    times = []
    tps = []
    overall_success_rate = []
    conn_p99 = []
    query_p99 = []
    total_p99 = []
    active_concurrency = []

    try:
        with open(args.log_file, 'r') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    stats = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                start_ts = stats.get('bucket_start', '')
                try:
                    # Parse timestamp, assuming ISO format with timezone
                    dt = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
                except ValueError:
                    continue
                
                times.append(dt)
                tps.append(stats.get('throughput_per_sec', 0))
                overall_success_rate.append(stats.get('overall_success_rate', 0) * 100)
                conn_p99.append(stats.get('connect_p99_ms', 0))
                query_p99.append(stats.get('query_p99_ms', 0))
                total_p99.append(stats.get('total_p99_ms', 0))
                active_concurrency.append(stats.get('active_concurrency', stats.get('configured_concurrency', 0)))

    except FileNotFoundError:
        print(f"Error: Log file not found: {args.log_file}")
        sys.exit(1)

    if not times:
        print("No valid data found to plot.")
        sys.exit(1)

    # Create subplots: 3 rows, 1 column
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
    fig.suptitle('Aurora Stress Test Performance', fontsize=16)

    # 1. Throughput (TPS)
    ax1.plot(times, tps, color='blue', label='TPS')
    ax1.set_ylabel('Throughput (req/sec)', color='blue')
    ax1.tick_params(axis='y', labelcolor='blue')
    ax1.grid(True, linestyle='--', alpha=0.7)
    
    # Add secondary Y axis for concurrency
    ax1_twin = ax1.twinx()
    ax1_twin.plot(times, active_concurrency, color='gray', linestyle=':', label='Active Concurrency')
    ax1_twin.set_ylabel('Concurrency', color='gray')
    ax1_twin.tick_params(axis='y', labelcolor='gray')
    ax1_twin.set_ylim(bottom=0)
    
    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_2, labels_2 = ax1_twin.get_legend_handles_labels()
    ax1_twin.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper left')

    # 2. Success Rate
    ax2.plot(times, overall_success_rate, color='green', label='Success Rate')
    ax2.set_ylabel('Success Rate (%)')
    ax2.set_ylim(-5, 105)
    ax2.grid(True, linestyle='--', alpha=0.7)
    ax2.legend(loc='upper left')

    # 3. Latency p99
    ax3.plot(times, conn_p99, color='orange', label='Connect p99')
    ax3.plot(times, query_p99, color='red', label='Query p99')
    ax3.plot(times, total_p99, color='purple', label='Total p99', linestyle='--')
    ax3.set_ylabel('Latency (ms)')
    ax3.set_xlabel('Time')
    ax3.grid(True, linestyle='--', alpha=0.7)
    ax3.legend(loc='upper left')

    # Format x-axis
    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
    fig.autofmt_xdate()

    plt.tight_layout()
    plt.savefig(args.output)
    print(f"Plot successfully saved to {args.output}")

if __name__ == "__main__":
    main()
