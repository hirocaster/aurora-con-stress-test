#!/usr/bin/env bash

# Linux OS/Network Preflight Check for High Concurrency Stress Test

echo "======================================================="
echo " Linux Preflight Check for High Concurrency Connection "
echo "======================================================="

warn_count=0
ng_count=0

function check_value() {
    local name="$1"
    local current="$2"
    local recommended="$3"
    local severity="$4"
    local reason="$5"
    local fix="$6"

    printf "%-30s: %s\n" "$name" "$current"
    if [ "$current" -lt "$recommended" ]; then
        if [ "$severity" == "WARN" ]; then
            echo -e "  -> \e[33m[WARN]\e[0m (Recommended: >= $recommended)"
            ((warn_count++))
        else
            echo -e "  -> \e[31m[NG]\e[0m (Recommended: >= $recommended)"
            ((ng_count++))
        fi
        echo "     Reason: $reason"
        echo "     Fix:    $fix"
    else
        echo -e "  -> \e[32m[OK]\e[0m"
    fi
    echo ""
}

function check_value_reverse() {
    local name="$1"
    local current="$2"
    local recommended="$3"
    local severity="$4"
    local reason="$5"
    local fix="$6"

    printf "%-30s: %s\n" "$name" "$current"
    if [ "$current" -gt "$recommended" ]; then
        if [ "$severity" == "WARN" ]; then
            echo -e "  -> \e[33m[WARN]\e[0m (Recommended: <= $recommended)"
            ((warn_count++))
        else
            echo -e "  -> \e[31m[NG]\e[0m (Recommended: <= $recommended)"
            ((ng_count++))
        fi
        echo "     Reason: $reason"
        echo "     Fix:    $fix"
    else
        echo -e "  -> \e[32m[OK]\e[0m"
    fi
    echo ""
}

# 1. CPU / Memory
cpus=$(nproc)
mem_kb=$(awk '/MemTotal/ {print $2}' /proc/meminfo)
mem_gb=$((mem_kb / 1024 / 1024))
echo "System: CPUs: $cpus, RAM: ${mem_gb}GB, Kernel: $(uname -r)"
echo ""

# 2. File Descriptors
ulimit_n=$(ulimit -n)
check_value "ulimit -n (open files)" "$ulimit_n" 65535 "NG" \
    "高並列でTCP接続を作成するとファイルディスクリプタが枯渇し 'too many open files' エラーになります。" \
    "Edit /etc/security/limits.conf or use ulimit -n 65535"

fs_file_max=$(cat /proc/sys/fs/file-max)
check_value "/proc/sys/fs/file-max" "$fs_file_max" 200000 "WARN" \
    "システム全体の最大ファイル数制限です。負荷が高いとシステム全体が止まる可能性があります。" \
    "sysctl -w fs.file-max=200000"

# 3. Ephemeral Ports
port_range=$(cat /proc/sys/net/ipv4/ip_local_port_range | awk '{print $2 - $1}')
check_value "Ephemeral port range size" "$port_range" 40000 "NG" \
    "使用可能なポート数が少ないと、短命接続を大量に作った際に枯渇し 'Cannot assign requested address' が発生します。" \
    "sysctl -w net.ipv4.ip_local_port_range='1024 65535'"

# 4. TIME_WAIT and TCP reuse
tcp_fin_timeout=$(cat /proc/sys/net/ipv4/tcp_fin_timeout)
check_value_reverse "tcp_fin_timeout" "$tcp_fin_timeout" 15 "WARN" \
    "短命接続では大量のソケットが TIME_WAIT 状態になります。タイムアウトが長い(>15s)とポート枯渇の原因になります。" \
    "sysctl -w net.ipv4.tcp_fin_timeout=15"

tcp_tw_reuse=$(cat /proc/sys/net/ipv4/tcp_tw_reuse)
if [ "$tcp_tw_reuse" -eq 1 ] || [ "$tcp_tw_reuse" -eq 2 ]; then
    echo -e "tcp_tw_reuse                  : $tcp_tw_reuse\n  -> \e[32m[OK]\e[0m\n"
else
    echo -e "tcp_tw_reuse                  : $tcp_tw_reuse\n  -> \e[31m[NG]\e[0m\n     Reason: TIME_WAIT 状態のソケットを再利用できないと、短命接続のポート枯渇が急速に進みます。\n     Fix:    sysctl -w net.ipv4.tcp_tw_reuse=1\n"
    ((ng_count++))
fi

# 5. Socket queues
somaxconn=$(cat /proc/sys/net/core/somaxconn)
check_value "somaxconn" "$somaxconn" 1024 "WARN" \
    "listenバックログの最大値です。高並列アクセス時に接続詰まりを防ぎます。" \
    "sysctl -w net.core.somaxconn=1024"

tcp_max_syn_backlog=$(cat /proc/sys/net/ipv4/tcp_max_syn_backlog)
check_value "tcp_max_syn_backlog" "$tcp_max_syn_backlog" 1024 "WARN" \
    "SYNを受信して未完了の接続キューの最大値です。" \
    "sysctl -w net.ipv4.tcp_max_syn_backlog=2048"

# 6. Network Buffers
rmem_max=$(cat /proc/sys/net/core/rmem_max)
check_value "rmem_max" "$rmem_max" 16777216 "WARN" \
    "ソケットの受信バッファの最大サイズです。数万のコネクションを張る際に不足する可能性があります。" \
    "sysctl -w net.core.rmem_max=16777216"

wmem_max=$(cat /proc/sys/net/core/wmem_max)
check_value "wmem_max" "$wmem_max" 16777216 "WARN" \
    "ソケットの送信バッファの最大サイズです。数万のコネクションを張る際に不足する可能性があります。" \
    "sysctl -w net.core.wmem_max=16777216"

tcp_rmem_max=$(cat /proc/sys/net/ipv4/tcp_rmem | awk '{print $3}')
check_value "tcp_rmem (max)" "$tcp_rmem_max" 16777216 "WARN" \
    "TCP受信バッファの最大サイズです。高並列時にパフォーマンスが低下する可能性があります。" \
    "sysctl -w net.ipv4.tcp_rmem='4096 87380 16777216'"

tcp_wmem_max=$(cat /proc/sys/net/ipv4/tcp_wmem | awk '{print $3}')
check_value "tcp_wmem (max)" "$tcp_wmem_max" 16777216 "WARN" \
    "TCP送信バッファの最大サイズです。高並列時にパフォーマンスが低下する可能性があります。" \
    "sysctl -w net.ipv4.tcp_wmem='4096 65536 16777216'"

# 7. Advanced Connection Checks
# nf_conntrack might not be loaded, check if the sysctl exists
if sysctl net.netfilter.nf_conntrack_max >/dev/null 2>&1; then
    nf_conntrack_max=$(cat /proc/sys/net/netfilter/nf_conntrack_max 2>/dev/null || cat /proc/sys/net/ipv4/netfilter/ip_conntrack_max 2>/dev/null)
    if [ -n "$nf_conntrack_max" ]; then
        check_value "nf_conntrack_max" "$nf_conntrack_max" 262144 "WARN" \
            "コネクショントラッキング(iptables等)の最大管理数です。上限に達するとパケットが破棄されます。" \
            "sysctl -w net.netfilter.nf_conntrack_max=262144"
    fi
fi

if [ -f /proc/sys/net/ipv4/tcp_max_tw_buckets ]; then
    tcp_max_tw_buckets=$(cat /proc/sys/net/ipv4/tcp_max_tw_buckets)
    check_value "tcp_max_tw_buckets" "$tcp_max_tw_buckets" 262144 "WARN" \
        "TIME_WAITソケットの最大許容数です。短命接続が多い場合は上限を引き上げないとエラーの元になります。" \
        "sysctl -w net.ipv4.tcp_max_tw_buckets=262144"
fi

# 8. Current Socket Status (ss)
echo "Current Socket Status:"
ss -s | grep -E "Total|TCP:|TIME-WAIT" | sed 's/^/  /'
echo ""

tw_count=$(ss -tan state time-wait | tail -n +2 | wc -l)
established_count=$(ss -tan state established | tail -n +2 | wc -l)
printf "%-30s: %s\n" "TIME_WAIT sockets" "$tw_count"
printf "%-30s: %s\n" "ESTABLISHED sockets" "$established_count"
echo ""

echo "======================================================="
if [ $ng_count -gt 0 ]; then
    echo -e "Result: \e[31mFAILED\e[0m ($ng_count Errors, $warn_count Warnings)"
    echo "Please fix the [NG] items before running high concurrency tests."
elif [ $warn_count -gt 0 ]; then
    echo -e "Result: \e[33mWARNING\e[0m (0 Errors, $warn_count Warnings)"
    echo "Test will run, but you might hit system limits under heavy load."
else
    echo -e "Result: \e[32mPASSED\e[0m (Ready for high concurrency testing)"
fi
