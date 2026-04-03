# Aurora MySQL 短命接続ストレステストツール (v2 - 集約ログ対応版)

「毎回 connect -> SQL実行 -> disconnect」を繰り返し、新規接続のレイテンシや短命接続時の成功率、および時間帯ごとのパフォーマンス劣化（connection storm等の影響）を計測するためのツールです。

## 特徴
- **集約ログ中心**: 全試行を1行ずつ吐き出さず、`1s`, `10s`, `1m` といった指定の「時間バケット」ごとに各種メトリクス（成功率、スループット、各レイテンシのパーセンタイル）を JSON Lines で出力します。
- **失敗詳細ログ**: 成功した通信の詳細は省き、失敗した試行のみ別途 `error.jsonl` に詳細を記録します。
- **Go実装**: コネクションプールを無効化し、高並列な goroutine で直接 endpoint に接続します。
- **Linux 事前チェック**: OSのTCPスタックやファイルディスクリプタ上限でボトルネックにならないかを診断する `preflight.sh` を同梱しています。

## 動作要件
- Go 1.20+
- Python 3.7+ (集約ログの簡易閲覧用 `analyze.py`)

## 準備とビルド
```bash
cd aurora-stress-test-v2
chmod +x preflight.sh

# 依存パッケージをダウンロード
go mod tidy

# ツールをビルド
go build -o stress-test main.go
```

## Linux 事前チェック (Preflight Check)
高並列テストを実施するホスト（EC2インスタンスなど）で、OSのパラメータ不足で失敗しないか確認します。
```bash
./preflight.sh
```

## テストの実行
```bash
./stress-test \
  -host "your-aurora-cluster.cluster-xyz.ap-northeast-1.rds.amazonaws.com" \
  -port 3306 \
  -user "admin" \
  -password "secret" \
  -database "mydb" \
  -sql "SELECT 1" \
  -concurrency 100 \
  -duration 10m \
  -aggregate_window 10s \
  -aggregate_log_path "aggregate.jsonl" \
  -error_log_path "error.jsonl" \
  -connect_timeout 5s \
  -query_timeout 10s
```

### パラメータ
- `-concurrency`: 並列ワーカー数（ゴルーチン数）
- `-duration`: 試験の実施時間（例: `10m`, `1h`）
- `-aggregate_window`: ログを集約する時間バケット幅（例: `1s`, `10s`, `1m`）
- `-sleep_between_attempts_ms`: 次の試行までのスリープ時間(ミリ秒)

## ログの確認
集約ログは1バケット1行の JSON Lines で出力されます。
これを同梱の Python スクリプトで簡単に視覚化できます。

```bash
python3 analyze.py aggregate.jsonl
```

### `analyze.py` 実行例
```text
======================================================================
AURORA STRESS TEST AGGREGATE ANALYSIS REPORT
======================================================================
[2024-05-01 10:00:00] Attempts: 320   | TPS:   32.0 | Overall Success: 100.00% | Conn Success: 100.00%
    Latency (ms) p90/p99 -> Conn: 15/45 | Query: 5/12 | Total: 22/58
----------------------------------------------------------------------
[2024-05-01 10:00:10] Attempts: 315   | TPS:   31.5 | Overall Success:  98.50% | Conn Success: 100.00%
    Latency (ms) p90/p99 -> Conn: 25/80 | Query: 6/15 | Total: 35/99
    Failures: {'query': 5}
    Errors:   {'Error 1205: Lock wait timeout exceeded; try rest...': 5}
----------------------------------------------------------------------
```
