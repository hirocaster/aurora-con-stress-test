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
cd aurora-con-stress-test
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

#### コネクションストーム（スパイク）のシミュレーション
- `-spike_concurrency`: スパイク時に追加で発生させる同時接続数
- `-spike_duration`: スパイクの継続時間（例: `5s`）
- `-spike_interval`: スパイクを発生させる間隔（例: `1m`）
※ 普段は `-concurrency` の数で負荷をかけつつ、`-spike_interval` 経過毎に `-spike_duration` の間だけ `-spike_concurrency` 個のワーカーが追加で一斉に接続を行います。

## ログの確認
集約ログは1バケット1行の JSON Lines で出力されます。
これを同梱の Python スクリプトで簡単に視覚化できます。

```bash
python3 analyze.py aggregate.jsonl
```

### `analyze.py` 出力項目の解説
```text
[2024-05-01 10:00:00] Attempts: 320   | TPS:   32.0 | Overall Success: 100.00% | Conn Success: 100.00%
    Latency (ms) p90/p99 -> Conn: 15/45 | Query: 5/12 | Total: 22/58
```
- **Attempts**: この時間バケット内で試行された「connect → query → disconnect」の総サイクル数。
- **TPS**: 1秒あたりのスループット (Throughput Per Second)。
- **Overall Success**: 「接続」「クエリ」「切断」のすべてが成功した割合。100%未満の場合は何らかのエラーが発生しています。
- **Conn Success**: 最初の「TCP接続とDB認証」に成功した割合。
- **Latency (ms) p90/p99**:
  - `p90`: 90%の通信がこの時間(ms)以内に完了した。
  - `p99`: 99%の通信がこの時間(ms)以内に完了した（一番遅かった異常値を見るのに最適）。
  - `Conn`: 接続〜認証完了までの時間。
  - `Query`: クエリの実行時間。
  - `Total`: 一連のフルサイクル（接続〜切断）の時間。

*※ テスト時間終了時に発生する強制切断エラー（Context キャンセルによる `invalid connection` など）は、ノイズを防ぐため自動的に集計から除外され、エラーとしてもカウントされません。*

### `analyze.py` の便利なフィルタ機能
長期間のテストログから「パフォーマンスが悪化したポイント」だけを素早く探すためのオプションが用意されています。

**① エラーが発生した時間帯のみ抽出**
```bash
python3 analyze.py aggregate.jsonl --errors-only
```
（成功率が100%の時間帯をスキップし、エラーが起きたバケットのみを表示します）

**② レイテンシが悪化した時間帯のみ抽出**
```bash
python3 analyze.py aggregate.jsonl --latency-threshold 100
```
（全体のレイテンシの p99 が 100ms を超えた時間帯のみを表示します）

### コネクションレイテンシの集計について
本ツールは「コネクションプーリングを無効化」し、1試行ごとに毎回 `sql.Open -> db.Ping -> db.Query -> db.Close` を行っています。
そのため、DBが大量の新規接続（スパイク）を受けて「接続を出し渋る（Acceptキューが詰まるなど）」といった事象が発生した場合、それは明確に **`Conn` (Connect Latency) の悪化** として集約ログ（p90/p99/max 等）に記録されます。

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

## ⚠️ 長時間（数日〜1週間）負荷をかける際の注意事項

長期間の負荷テスト（例: `-duration 168h`）を実施する際は、以下の点に注意してください。

### 1. `aggregate_window`（時間バケット）の適切な設定
数日間にわたるテストの場合、`-aggregate_window` を短くしすぎると（例: `1s`）、ログが肥大化します。
長期間テストの場合は **`10s` または `1m`** に設定することを推奨します。
（`1m` の場合、1時間で60行、1週間で約10,000行、数MB程度のサイズに収まります）

### 2. エラーログ (`error.jsonl`) の肥大化リスク
本ツールは「成功した試行の詳細は出力せず、**失敗した試行のみ** 詳細を `error.jsonl` に出力」します。
通常はサイズ0のままですが、Auroraが完全にダウンし数万件の接続エラーが継続して発生するような事態に陥った場合、`error.jsonl` が急速に肥大化（数GBなど）する可能性があります。ディスク容量に余裕のあるパーティションで実行してください。

### 3. バックグラウンドでの実行
SSH接続を切ってもテストが継続するよう、`nohup` や `tmux`、`screen` などを利用して実行してください。

**長時間実行用コマンド例 (1週間稼働):**
```bash
nohup ./stress-test \
  -host "your-aurora-cluster.rds.amazonaws.com" \
  -user "admin" \
  -password "secret" \
  -database "mydb" \
  -concurrency 100 \
  -duration 168h \
  -aggregate_window 1m \
  -spike_interval 5m \
  -spike_duration 10s \
  -spike_concurrency 500 \
  > stress-test.log 2>&1 &
```
