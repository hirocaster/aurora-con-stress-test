# Aurora MySQL 短命接続ストレステストツール仕様

Aurora MySQL に対して、**毎回 `connect -> SQL実行 -> disconnect`** を行う短命接続型のストレステストツールを **Golang** で作りたい。
接続先は **Aurora endpoint に direct 接続** とする。
長時間試験を前提とし、**特定の時間帯だけレイテンシや失敗率が悪化したか**を後から分析できるようにしたい。
ログは全試行詳細ではなく、**集約ログ中心** にして、ログ肥大化を避けたい。

## 目的

* 新規接続レイテンシを測る
* SQL 実行レイテンシを測る
* 接続成功率 / SQL 成功率 / 全体成功率を測る
* 長時間試験で、特定時間帯の劣化を分析できるようにする
* connection storm 的な負荷で Aurora MySQL の挙動を観測する

## 負荷仕様

* 毎回 `connect -> query -> disconnect`
* コネクションプールは使わない
* SQL は軽量（例: `SELECT 1`）
* 高並列・長時間で動作
* goroutine ベースで worker を動かす
* duration 終了まで各 worker が試行を繰り返す

## 実装要件

* Go で実装
* 単体バイナリで動作
* Aurora MySQL endpoint に direct 接続
* 接続 / クエリ / 切断の各 phase を個別に計測
* ログは **集約ログを主** とする
* 必要なら **失敗試行のみ詳細ログ** を別出力できるようにする

## CLI / 設定項目

* `host`
* `port`
* `user`
* `password`
* `database`
* `sql`
* `concurrency`
* `duration`
* `connect_timeout`
* `query_timeout`
* `run_id`
* `aggregate_log_path`
* `error_log_path`
* `aggregate_window`
  例: `1s`, `10s`, `1m`

必要なら追加:

* `dial_timeout`
* `tls_mode`
* `sleep_between_attempts_ms`

---

# 集約ログ仕様

## 基本方針

* 全試行の詳細ログは出さない
* **時間バケット単位の集約ログ** を出力する
* 長時間試験でもログサイズが増えすぎないようにする
* 後から CSV / JSON でグラフ化しやすい形式にする

## バケット単位

少なくとも以下をサポート:

* 1秒
* 10秒
* 1分

## 集約ログに含める項目

* `bucket_start`
* `bucket_end`
* `run_id`
* `configured_concurrency`
* `attempts`
* `connect_success_count`
* `connect_failure_count`
* `query_success_count`
* `query_failure_count`
* `disconnect_success_count`
* `disconnect_failure_count`
* `overall_success_count`
* `overall_failure_count`

### 成功率

* `connect_success_rate`
* `query_success_rate`
* `disconnect_success_rate`
* `overall_success_rate`

### throughput

* `throughput_per_sec`

### connect latency

成功した connect を対象に:

* `connect_avg_ms`
* `connect_p50_ms`
* `connect_p90_ms`
* `connect_p95_ms`
* `connect_p99_ms`
* `connect_max_ms`

### query latency

成功した query を対象に:

* `query_avg_ms`
* `query_p50_ms`
* `query_p90_ms`
* `query_p95_ms`
* `query_p99_ms`
* `query_max_ms`

### total latency

試行全体が完了したものを対象に:

* `total_avg_ms`
* `total_p50_ms`
* `total_p90_ms`
* `total_p95_ms`
* `total_p99_ms`
* `total_max_ms`

### 失敗内訳

* `failure_phase_counts`
* `error_type_counts`

ログ形式は **JSON Lines か CSV**。
集約ログは 1 バケットにつき 1 レコード。

---

# 失敗詳細ログ

## 方針

* 全成功試行の詳細は記録しない
* **失敗試行だけ詳細ログ**を出す
* 調査時に失敗内容を追えるようにする

## 失敗詳細ログ項目

* `timestamp`
* `run_id`
* `worker_id`
* `attempt_id`
* `target_host`
* `target_port`
* `failure_phase`
* `error_type`
* `error_code`
* `error_message`
* `connect_latency_ms`
* `query_latency_ms`
* `disconnect_latency_ms`
* `total_latency_ms`

形式は **JSON Lines** を推奨。

---

# 統計ルール

* connect 失敗時は query / disconnect latency は `null`
* query 失敗時でも connect 成功は別集計する
* phase ごとの percentile は、その phase の成功試行のみを対象に計算する
* `total_*` は試行全体が完了したもののみを対象に計算する
* `overall_success_rate` = connect / query / disconnect が全て成功した試行数 / 総試行数
* `throughput_per_sec` = バケット内の完了試行数 / バケット秒数

---

# 時系列分析要件

この集約ログで、後から以下が分かるようにしたい。

* 特定時間帯だけ connect latency が悪化した
* 特定時間帯だけ total latency が悪化した
* 特定時間帯だけ失敗率が増えた
* throughput が落ちた
* 一時的な connection storm の影響が出た

つまり、全体サマリだけでなく、**時間バケット単位の時系列分析ができること**を重視する。

---

# Linux 事前チェック用スクリプト

別スクリプトとして、負荷生成側 Linux ホストが OS / TCP / socket 制約で詰まらないか確認する **preflight check** を作りたい。

## 目的

* 高並列・短命接続テスト前に OS 設定不足を検知する
* root 権限不要でチェック中心
* 設定変更はしない
* warning と推奨設定例を出す

## チェック対象

* `ulimit -n`
* `/proc/sys/fs/file-max`
* `/proc/sys/net/ipv4/ip_local_port_range`
* `/proc/sys/net/ipv4/tcp_fin_timeout`
* `/proc/sys/net/ipv4/tcp_tw_reuse`
* `/proc/sys/net/core/somaxconn`
* `/proc/sys/net/ipv4/tcp_max_syn_backlog`
* `ss -s`
* `ss -tan state time-wait`
* `ss -tan state established`
* CPU コア数
* メモリ容量
* kernel version

## 出力内容

* 現在値
* 推奨値または推奨レンジ
* 判定 `OK / WARN / NG`
* なぜ問題か
* sysctl / limits.conf の設定例

---

# 欲しい成果物

* Go 製ストレステストツール
* 集約ログ仕様
* 失敗詳細ログ仕様
* ログ集計ツール
* Linux preflight check スクリプト
* README
* 実行例
* 集計例

---

# AI に確認したいこと

* この仕様で実装可能か
* Go でシンプルに作れるか
* 集約ログ中心の設計が妥当か
* percentile / 成功率 / throughput の定義が妥当か
* 長時間試験の時系列分析に十分か
* Linux の事前チェック項目に不足がないか
