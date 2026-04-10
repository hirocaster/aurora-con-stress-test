#!/usr/bin/env python3
import argparse
import json
import os
import time
from datetime import datetime, timezone
from typing import Optional, Dict


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_sockstat() -> Dict[str, Optional[int]]:
    out = {
        "tcp_inuse": None,
        "tcp_tw": None,
        "tcp_alloc": None,
        "tcp_mem": None,
        "sockets_used": None,
    }

    try:
        with open("/proc/net/sockstat", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("sockets:"):
                    parts = line.split()
                    # sockets: used 824
                    if len(parts) >= 3 and parts[1] == "used":
                        out["sockets_used"] = int(parts[2])
                elif line.startswith("TCP:"):
                    parts = line.split()
                    # TCP: inuse 30 orphan 0 tw 20 alloc 50 mem 10
                    values = {}
                    for i in range(1, len(parts) - 1, 2):
                        k = parts[i]
                        v = parts[i + 1]
                        values[k] = int(v)
                    out["tcp_inuse"] = values.get("inuse")
                    out["tcp_tw"] = values.get("tw")
                    out["tcp_alloc"] = values.get("alloc")
                    out["tcp_mem"] = values.get("mem")
    except FileNotFoundError:
        pass

    return out


def read_loadavg() -> Dict[str, Optional[float]]:
    out = {
        "load_avg_1m": None,
        "load_avg_5m": None,
        "load_avg_15m": None,
    }
    try:
        with open("/proc/loadavg", "r", encoding="utf-8") as f:
            parts = f.read().strip().split()
            if len(parts) >= 3:
                out["load_avg_1m"] = float(parts[0])
                out["load_avg_5m"] = float(parts[1])
                out["load_avg_15m"] = float(parts[2])
    except FileNotFoundError:
        pass
    return out


def read_proc_status(pid: int) -> Dict[str, Optional[int]]:
    out = {
        "pid_alive": 0,
        "rss_kb": None,
        "vms_kb": None,
        "threads": None,
        "open_fds": None,
    }

    status_path = f"/proc/{pid}/status"
    if not os.path.exists(status_path):
        return out

    out["pid_alive"] = 1

    try:
        with open(status_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    out["rss_kb"] = int(line.split()[1])
                elif line.startswith("VmSize:"):
                    out["vms_kb"] = int(line.split()[1])
                elif line.startswith("Threads:"):
                    out["threads"] = int(line.split()[1])
    except FileNotFoundError:
        return out

    fd_dir = f"/proc/{pid}/fd"
    try:
        out["open_fds"] = len(os.listdir(fd_dir))
    except FileNotFoundError:
        out["open_fds"] = None

    return out


def read_meminfo_available_kb() -> Optional[int]:
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1])
    except FileNotFoundError:
        return None
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor system and stress-test process resources into JSONL")
    parser.add_argument("--pid", type=int, required=True, help="PID of stress-test process to observe")
    parser.add_argument("--output", required=True, help="Output JSONL path")
    parser.add_argument("--interval", type=int, default=30, help="Sampling interval in seconds")
    parser.add_argument("--stop-after-exit-seconds", type=int, default=120, help="Keep sampling after process exit")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    dead_since: Optional[float] = None

    with open(args.output, "a", encoding="utf-8") as out:
        while True:
            ts = now_iso()

            sock = read_sockstat()
            load = read_loadavg()
            proc = read_proc_status(args.pid)
            mem_avail = read_meminfo_available_kb()

            row = {
                "timestamp": ts,
                "pid": args.pid,
                "pid_alive": proc["pid_alive"],
                "rss_kb": proc["rss_kb"],
                "vms_kb": proc["vms_kb"],
                "threads": proc["threads"],
                "open_fds": proc["open_fds"],
                "tcp_inuse": sock["tcp_inuse"],
                "tcp_tw": sock["tcp_tw"],
                "tcp_alloc": sock["tcp_alloc"],
                "tcp_mem": sock["tcp_mem"],
                "sockets_used": sock["sockets_used"],
                "load_avg_1m": load["load_avg_1m"],
                "load_avg_5m": load["load_avg_5m"],
                "load_avg_15m": load["load_avg_15m"],
                "mem_available_kb": mem_avail,
            }
            out.write(json.dumps(row, ensure_ascii=True) + "\n")
            out.flush()

            if proc["pid_alive"] == 0:
                if dead_since is None:
                    dead_since = time.time()
                elif (time.time() - dead_since) >= args.stop_after_exit_seconds:
                    break
            else:
                dead_since = None

            time.sleep(max(1, args.interval))


if __name__ == "__main__":
    main()
