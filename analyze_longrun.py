#!/usr/bin/env python3
import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@dataclass
class Bucket:
    ts: datetime
    attempts: int
    success_rate: float
    throughput: float
    total_p99_ms: float


@dataclass
class Sample:
    ts: datetime
    rss_kb: Optional[int]
    tcp_tw: Optional[int]


def load_buckets(path: str) -> List[Bucket]:
    out: List[Bucket] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            ts_raw = obj.get("bucket_start")
            if not ts_raw:
                continue
            attempts = int(obj.get("attempts") or 0)
            succ = obj.get("overall_success_rate")
            throughput = float(obj.get("throughput_per_sec") or 0.0)
            p99 = float(obj.get("total_p99_ms") or 0.0)
            out.append(
                Bucket(
                    ts=parse_ts(ts_raw),
                    attempts=attempts,
                    success_rate=float(succ if succ is not None else 0.0),
                    throughput=throughput,
                    total_p99_ms=p99,
                )
            )
    out.sort(key=lambda x: x.ts)
    return out


def load_samples(path: Optional[str]) -> List[Sample]:
    if not path:
        return []
    out: List[Sample] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            ts_raw = obj.get("timestamp")
            if not ts_raw:
                continue
            out.append(
                Sample(
                    ts=parse_ts(ts_raw),
                    rss_kb=obj.get("rss_kb"),
                    tcp_tw=obj.get("tcp_tw"),
                )
            )
    out.sort(key=lambda x: x.ts)
    return out


def weighted_success(buckets: List[Bucket]) -> float:
    total_attempts = sum(b.attempts for b in buckets)
    if total_attempts == 0:
        return 0.0
    total_success = sum(b.attempts * b.success_rate for b in buckets)
    return total_success / total_attempts


def avg_throughput(buckets: List[Bucket]) -> float:
    if not buckets:
        return 0.0
    return sum(b.throughput for b in buckets) / len(buckets)


def avg_p99(buckets: List[Bucket]) -> float:
    if not buckets:
        return 0.0
    return sum(b.total_p99_ms for b in buckets) / len(buckets)


def pct_change(old: float, new: float) -> float:
    if old == 0:
        return 0.0
    return (new - old) / old * 100.0


def window_slice(buckets: List[Bucket], start: datetime, end: datetime) -> List[Bucket]:
    return [b for b in buckets if start <= b.ts < end]


def summarize_resources(samples: List[Sample]) -> Dict[str, Optional[float]]:
    if not samples:
        return {
            "rss_start_mb": None,
            "rss_end_mb": None,
            "rss_growth_mb": None,
            "tcp_tw_max": None,
        }

    rss_vals = [s.rss_kb for s in samples if s.rss_kb is not None]
    tcp_tw_vals = [s.tcp_tw for s in samples if s.tcp_tw is not None]

    rss_start = rss_vals[0] / 1024.0 if rss_vals else None
    rss_end = rss_vals[-1] / 1024.0 if rss_vals else None
    rss_growth = (rss_end - rss_start) if (rss_start is not None and rss_end is not None) else None
    tcp_tw_max = max(tcp_tw_vals) if tcp_tw_vals else None

    return {
        "rss_start_mb": rss_start,
        "rss_end_mb": rss_end,
        "rss_growth_mb": rss_growth,
        "tcp_tw_max": tcp_tw_max,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze 48h long-run aggregate/resource logs")
    parser.add_argument("aggregate_log", help="Path to aggregate.jsonl")
    parser.add_argument("--resources-log", help="Path to resources.jsonl")
    parser.add_argument("--min-success-rate", type=float, default=0.995, help="Minimum required overall success rate (0-1)")
    parser.add_argument("--max-throughput-drop-pct", type=float, default=10.0, help="Max allowed throughput drop (percent)")
    parser.add_argument("--max-p99-increase-pct", type=float, default=10.0, help="Max allowed total p99 increase (percent)")
    parser.add_argument("--window-hours", type=int, default=1, help="Window size for baseline/final comparison")
    parser.add_argument("--json-out", help="Optional summary JSON output path")
    args = parser.parse_args()

    buckets = load_buckets(args.aggregate_log)
    samples = load_samples(args.resources_log)

    if not buckets:
        raise SystemExit("No valid bucket records found in aggregate log")

    start_ts = buckets[0].ts
    end_ts = buckets[-1].ts
    window = timedelta(hours=max(1, args.window_hours))

    first_window = window_slice(buckets, start_ts, start_ts + window)
    last_window = window_slice(buckets, end_ts - window, end_ts + timedelta(seconds=1))

    overall_success = weighted_success(buckets)
    first_tp = avg_throughput(first_window)
    last_tp = avg_throughput(last_window)
    tp_change_pct = pct_change(first_tp, last_tp)

    first_p99 = avg_p99(first_window)
    last_p99 = avg_p99(last_window)
    p99_change_pct = pct_change(first_p99, last_p99)

    res = summarize_resources(samples)

    success_pass = overall_success >= args.min_success_rate
    throughput_pass = tp_change_pct >= -abs(args.max_throughput_drop_pct)
    p99_pass = p99_change_pct <= abs(args.max_p99_increase_pct)
    verdict = "PASS" if (success_pass and throughput_pass and p99_pass) else "FAIL"

    summary = {
        "verdict": verdict,
        "start": start_ts.isoformat(),
        "end": end_ts.isoformat(),
        "records": len(buckets),
        "overall_success_rate": overall_success,
        "overall_success_rate_pct": overall_success * 100.0,
        "first_window_throughput": first_tp,
        "last_window_throughput": last_tp,
        "throughput_change_pct": tp_change_pct,
        "first_window_total_p99_ms": first_p99,
        "last_window_total_p99_ms": last_p99,
        "p99_change_pct": p99_change_pct,
        "resource": res,
        "thresholds": {
            "min_success_rate": args.min_success_rate,
            "max_throughput_drop_pct": args.max_throughput_drop_pct,
            "max_p99_increase_pct": args.max_p99_increase_pct,
        },
        "checks": {
            "success_pass": success_pass,
            "throughput_pass": throughput_pass,
            "p99_pass": p99_pass,
        },
    }

    print("=" * 68)
    print("LONG-RUN STABILITY SUMMARY")
    print("=" * 68)
    print(f"Verdict                 : {summary['verdict']}")
    print(f"Test range              : {summary['start']} -> {summary['end']}")
    print(f"Bucket count            : {summary['records']}")
    print(f"Overall success rate    : {summary['overall_success_rate_pct']:.4f}%")
    print(f"Throughput change       : {summary['throughput_change_pct']:.2f}% (first {args.window_hours}h -> last {args.window_hours}h)")
    print(f"Total p99 change        : {summary['p99_change_pct']:.2f}% (first {args.window_hours}h -> last {args.window_hours}h)")

    if res["rss_growth_mb"] is not None:
        print(f"RSS growth              : {res['rss_growth_mb']:.2f} MB")
    if res["tcp_tw_max"] is not None:
        print(f"TCP TIME_WAIT peak      : {res['tcp_tw_max']}")

    print("Checks:")
    print(f"  success >= {args.min_success_rate * 100:.2f}%           : {'PASS' if success_pass else 'FAIL'}")
    print(f"  throughput drop <= {args.max_throughput_drop_pct:.2f}%  : {'PASS' if throughput_pass else 'FAIL'}")
    print(f"  p99 increase <= {args.max_p99_increase_pct:.2f}%        : {'PASS' if p99_pass else 'FAIL'}")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=True, indent=2)


if __name__ == "__main__":
    main()
