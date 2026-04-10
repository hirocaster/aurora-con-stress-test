# ベンチマークレポート: db.r6i.4xlarge

**実施日**: 2026-04-09  
**インスタンス**: db.r6i.4xlarge (amd64 / Intel)  
**実施条件**: ulimit 適用済み

---

## エグゼクティブサマリー

| 項目 | 結論 |
|------|------|
| **実運用推奨上限** | **QPS 4,000**（Healthy / Congested 両シナリオで完全安定） |
| **実運用許容上限** | **QPS 5,000**（Congested で散発的タイムアウト 2 窓、要監視） |
| **実運用不可** | **QPS 6,000 以上**（エラー窓が増加し継続運用に不適） |
| **arm64比較** | db.r8g.4xlarge より高QPS帯（特に QPS 5,000）で安定性が高い |

---

## テスト環境・条件

| 項目 | 値 |
|------|-----|
| テスト対象 | Aurora MySQL (db.r6i.4xlarge) |
| エンドポイント | database-connectivity-instance1-cluster.cluster-c9eaw8m4yzeq.ap-northeast-1.rds.amazonaws.com:3306 |
| max_connections | 16,000 |
| Max_used_connections | 960（QPS 10,000 congested 終了時） |
| テスト方式 | connect → SELECT 1 → disconnect（コネクションプールなし） |
| 計測ウィンドウ | 10秒バケット |
| テスト時間/シナリオ | 5分 |
| テスト開始時刻 | 2026-04-09 01:36:47 UTC 〜 |
| Healthy: 並列数 | QPS × 25 / 1,000 goroutine（sleep_between_attempts=10ms） |
| Congested: 並列数 | QPS × 60 / 1,000 goroutine（sleep_between_attempts=30ms） |

**シナリオ定義:**
- **Healthy**: 比較的余裕のある接続環境。接続間隔が短く並列数も少ない。
- **Congested**: 接続に時間がかかる輻輳状態を模擬。高並列・長い接続待ち間隔。

---

## QPS別テスト結果サマリー

| QPS目標 | シナリオ | 並列数 | 実測 TPS | 全体成功率 | エラー発生窓数(概算) | 運用判定 |
|---------|---------|--------|---------|-----------|---------------------|---------|
| 1,000 | Healthy | 25 | ~194-1,001 | **100%** | 0 | ✅ 実運用可 |
| 1,000 | Congested | 60 | ~150-1,308 | **100%** | 0 | ✅ 実運用可 |
| 2,000 | Healthy | 50 | ~80-2,017 | 100% | 1 | ✅ 実運用可 |
| 2,000 | Congested | 120 | ~84-2,616 | **100%** | 0 | ✅ 実運用可 |
| 3,000 | Healthy | 75 | ~315-3,010 | **100%** | 0 | ✅ 実運用可 |
| 3,000 | Congested | 180 | ~756-3,924 | **100%** | 0 | ✅ 実運用可 |
| 4,000 | Healthy | 100 | ~1,055-4,027 | **100%** | 0 | ✅ 実運用可（推奨上限） |
| 4,000 | Congested | 240 | ~1,824-5,232 | **100%** | 0 | ✅ 実運用可 |
| 5,000 | Healthy | 125 | ~2,100-5,092 | **100%** | 0 | ⚠️ 実運用許容 |
| 5,000 | Congested | 300 | ~2,622-6,614 | 99.9〜100% | 2 | ⚠️ 実運用許容（要監視） |
| 6,000 | Healthy | 150 | ~1,941-6,143 | 99.6〜100% | 1 | ❌ 実運用不可 |
| 6,000 | Congested | 360 | ~1,838-7,973 | 99.6〜100% | 9 | ❌ 実運用不可 |
| 7,000 | Healthy | 175 | ~1,302-7,105 | 99.8〜100% | 12 | ❌ 実運用不可 |
| 7,000 | Congested | 420 | ~1,252-9,233 | 99.4〜100% | 18 | ❌ 実運用不可 |
| 8,000 | Healthy | 200 | ~11-7,954（崩壊） | **22.5〜100%（崩壊）** | 18+ | ❌ **実運用不可** |
| 8,000 | Congested | 480 | 48-9,650（崩壊） | **37.9〜100%（崩壊）** | 27+ | ❌ **実運用不可** |
| 9,000 | Healthy | 225 | 22.5-8,305（崩壊） | **33.3〜100%（崩壊）** | 22+ | ❌ **実運用不可** |
| 9,000 | Congested | 540 | ~193-8,345 | 98.5〜99.8% | 31 | ❌ **実運用不可** |
| 10,000 | Healthy | 250 | ~517-8,972 | 99.5〜100% | 23 | ❌ **実運用不可** |
| 10,000 | Congested | 600 | ~2,088-7,845 | 98.6〜100% | 30 | ❌ **実運用不可** |

---

## QPS別詳細分析

### QPS 1,000

#### Healthy（concurrency=25, sleep=10ms）
- **実測 TPS**: 194〜1,001 QPS
- **全体成功率**: 100%
- **connect P99**: 10〜54ms
- **total P99**: 19〜61ms
- **Max_used_connections**: 33（0.2%）
- **エラー**: なし

#### Congested（concurrency=60, sleep=30ms）
- **実測 TPS**: 150〜1,308 QPS
- **全体成功率**: 100%
- **connect P99**: 10〜16ms
- **total P99**: 18〜25ms
- **Max_used_connections**: 81（0.5%）
- **エラー**: なし

**判定**: 完全安定。

---

### QPS 2,000

#### Healthy（concurrency=50, sleep=10ms）
- **実測 TPS**: 80〜2,017 QPS
- **全体成功率**: 100%
- **エラーパターン**: 1窓のみ `timeout:2`（散発）
- **connect P99**: 10〜13ms
- **total P99**: 19〜23ms
- **Max_used_connections**: 81（0.5%）

#### Congested（concurrency=120, sleep=30ms）
- **実測 TPS**: 84〜2,616 QPS
- **全体成功率**: 100%
- **connect P99**: 9〜19ms
- **total P99**: 16〜35ms
- **Max_used_connections**: 150（0.9%）
- **エラー**: なし

**判定**: 実運用可。Healthy の単発エラーは許容範囲。

---

### QPS 3,000

#### Healthy（concurrency=75, sleep=10ms）
- **実測 TPS**: 315〜3,010 QPS
- **全体成功率**: 100%
- **connect P99**: 10〜13ms
- **total P99**: 18〜24ms
- **Max_used_connections**: 150（0.9%）
- **エラー**: なし

#### Congested（concurrency=180, sleep=30ms）
- **実測 TPS**: 756〜3,924 QPS
- **全体成功率**: 100%
- **connect P99**: 11〜22ms
- **total P99**: 18〜42ms
- **Max_used_connections**: 256（1.6%）
- **エラー**: なし

**判定**: 実運用可。Healthy / Congested ともに高い安定性。

---

### QPS 4,000

#### Healthy（concurrency=100, sleep=10ms）
- **実測 TPS**: 1,055〜4,027 QPS
- **全体成功率**: 100%
- **connect P99**: 10〜16ms
- **total P99**: 18〜27ms
- **Max_used_connections**: 256（1.6%）
- **エラー**: なし

#### Congested（concurrency=240, sleep=30ms）
- **実測 TPS**: 1,824〜5,232 QPS
- **全体成功率**: 100%
- **connect P99**: 10〜25ms
- **total P99**: 19〜47ms
- **Max_used_connections**: 356（2.2%）
- **エラー**: なし

**判定**: 実運用可（推奨上限）。4xlarge帯では非常に安定。

---

### QPS 5,000

#### Healthy（concurrency=125, sleep=10ms）
- **実測 TPS**: 2,100〜5,092 QPS
- **全体成功率**: 100%
- **connect P99**: 10〜18ms
- **total P99**: 18〜35ms
- **Max_used_connections**: 356（2.2%）
- **エラー**: なし

#### Congested（concurrency=300, sleep=30ms）
- **実測 TPS**: 2,622〜6,614 QPS
- **全体成功率**: 99.9〜100%
- **エラーパターン**: 2窓で `timeout:37〜56`
- **connect P99**: 10〜71ms
- **total P99**: 19〜107ms
- **Max_used_connections**: 480（3.0%）

**判定**: ⚠️ 実運用許容。高い成功率を維持するが、Congested で散発エラーが発生。

---

### QPS 6,000

#### Healthy（concurrency=150, sleep=10ms）
- **実測 TPS**: 1,941〜6,143 QPS
- **全体成功率**: 99.6〜100%
- **エラーパターン**: 1窓で `timeout:100`
- **connect P99**: 10〜17ms
- **total P99**: 18〜33ms
- **Max_used_connections**: 480（3.0%）

#### Congested（concurrency=360, sleep=30ms）
- **実測 TPS**: 1,838〜7,973 QPS
- **全体成功率**: 99.6〜100%
- **エラーパターン**: 9窓で `timeout:50〜183`
- **connect P99**: 11〜84ms
- **total P99**: 20〜120ms
- **Max_used_connections**: 613（3.8%）

**判定**: ❌ 実運用不可。Congested でエラー窓が多く継続運用には不適。

---

### QPS 7,000

#### Healthy（concurrency=175, sleep=10ms）
- **実測 TPS**: 1,302〜7,105 QPS
- **全体成功率**: 99.8〜100%
- **エラーパターン**: 12窓で `timeout:7〜120`
- **connect P99**: 11〜43ms
- **total P99**: 19〜60ms
- **Max_used_connections**: 613（3.8%）

#### Congested（concurrency=420, sleep=30ms）
- **実測 TPS**: 1,252〜9,233 QPS
- **全体成功率**: 99.4〜100%
- **エラーパターン**: 18窓で `timeout:28〜230`
- **connect P99**: 12〜73ms
- **total P99**: 22〜104ms
- **Max_used_connections**: 682（4.3%）

**判定**: ❌ 実運用不可。エラー頻度が高く、耐障害性が不足。

---

### QPS 8,000

#### Healthy（concurrency=200, sleep=10ms）
- **実測 TPS**: 10.7〜7,954 QPS（大幅変動）
- **全体成功率**: 22.5〜100%（崩壊状態）
- **エラーパターン**: 18窓以上で `timeout:58〜155`
- **connect P99**: 11〜5,022ms
- **total P99**: 20〜5,046ms
- **Max_used_connections**: 682（4.3%）

#### Congested（concurrency=480, sleep=30ms）
- **実測 TPS**: 48〜9,650 QPS（大幅変動）
- **全体成功率**: 37.9〜100%（崩壊状態）
- **エラーパターン**: 27窓以上で `timeout:10〜345`
- **connect P99**: 17〜5,053ms
- **total P99**: 29〜5,110ms
- **Max_used_connections**: 780（4.9%）

**判定**: ❌ 実運用不可。両シナリオで崩壊挙動。

---

### QPS 9,000

#### Healthy（concurrency=225, sleep=10ms）
- **実測 TPS**: 22.5〜8,305 QPS（大幅変動）
- **全体成功率**: 33.3〜100%（崩壊状態）
- **エラーパターン**: 22窓以上で `timeout:23〜209`
- **connect P99**: 12〜5,026ms
- **total P99**: 22〜5,051ms
- **Max_used_connections**: 780（4.9%）

#### Congested（concurrency=540, sleep=30ms）
- **実測 TPS**: 193〜8,345 QPS
- **全体成功率**: 98.5〜99.8%
- **エラーパターン**: 全窓で timeout（`7〜341`）
- **connect P99**: 19〜5,038ms
- **total P99**: 37〜5,101ms
- **Max_used_connections**: 945（5.9%）

**判定**: ❌ 実運用不可。Healthy は崩壊、Congested も全窓でエラー。

---

### QPS 10,000

#### Healthy（concurrency=250, sleep=10ms）
- **実測 TPS**: 517〜8,972 QPS
- **全体成功率**: 99.5〜100%
- **エラーパターン**: 23窓で `timeout:4〜202`
- **connect P99**: 12〜29ms
- **total P99**: 23〜56ms
- **Max_used_connections**: 945（5.9%）

#### Congested（concurrency=600, sleep=30ms）
- **実測 TPS**: 2,088〜7,845 QPS
- **全体成功率**: 98.6〜100%
- **エラーパターン**: 30窓で `timeout:13〜631`
- **connect P99**: 16〜5,050ms
- **total P99**: 30〜5,120ms
- **Max_used_connections**: 960（6.0%）

**判定**: ❌ 実運用不可。継続的エラーが発生し続ける。

---

## Max_used_connections 推移の分析

| QPS | Max_used_connections | max_connectionsに対する割合 |
|-----|---------------------|---------------------------|
| 1,000 (Healthy) | 33 | 0.2% |
| 1,000 (Congested) | 81 | 0.5% |
| 2,000 (Healthy) | 81 | 0.5% |
| 2,000 (Congested) | 150 | 0.9% |
| 3,000 (Healthy) | 150 | 0.9% |
| 3,000 (Congested) | 256 | 1.6% |
| 4,000 (Healthy) | 256 | 1.6% |
| 4,000 (Congested) | 356 | 2.2% |
| 5,000 (Healthy) | 356 | 2.2% |
| 5,000 (Congested) | 480 | 3.0% |
| 6,000 (Healthy) | 480 | 3.0% |
| 6,000 (Congested) | 613 | 3.8% |
| 7,000 (Healthy) | 613 | 3.8% |
| 7,000 (Congested) | 682 | 4.3% |
| 8,000 (Healthy) | 682 | 4.3% |
| 8,000 (Congested) | 780 | 4.9% |
| 9,000 (Healthy) | 780 | 4.9% |
| 9,000 (Congested) | 945 | 5.9% |
| 10,000 (Healthy) | 945 | 5.9% |
| 10,000 (Congested) | 960 | 6.0% |

**知見:**
- 全テストで接続数は max_connections (16,000) の 6% 以下に収まっている。
- 接続数枯渇ではなく、接続処理のレイテンシ急増（P99 / MAX の 5秒化）と内部処理能力がボトルネック。
- r8g.4xlarge と同様に「接続数上限」より先に「処理遅延限界」に到達する。

---

## アーキテクチャ比較（db.r8g.4xlarge arm64 との対比）

同一条件で計測済みの [db.r8g.4xlarge](../db_r8g_4xlarge/REPORT.md)（arm64/Graviton）と比較。

| インスタンス | CPUアーキ | vCPU | メモリ (GiB) | 推奨上限QPS | 許容上限QPS |
|-------------|-----------|------|-------------|-------------|-------------|
| db.r8g.4xlarge | arm64 (Graviton) | 16 | 128 | 3,000 | 4,000 |
| **db.r6i.4xlarge** | **amd64 (Intel)** | **16** | **128** | **4,000** | **5,000** |

### QPS帯別の安定性比較

| QPS帯 | db.r8g.4xlarge (arm64) | db.r6i.4xlarge (amd64) |
|-------|-------------------------|--------------------------|
| QPS 1,000 | 100%安定 | 100%安定（同等） |
| QPS 2,000 | 散発エラーあり（Healthy） | ほぼ完全安定（Healthy単発2件のみ） |
| QPS 3,000 | 実運用可（推奨上限） | 実運用可（完全安定） |
| QPS 4,000 | 実運用許容（散発エラー） | 完全安定（推奨上限） |
| QPS 5,000 | Healthy 崩壊で実運用不可 | Healthy 100%、Congested 99.9%（要監視） |
| QPS 6,000 | 実運用不可 | 実運用不可（エラー窓増加） |

**要点:**
- 同一 4xlarge クラスでも、今回の短命接続ワークロードでは **amd64 (r6i)** が高QPS帯でより安定した。
- 差が最も大きいのは QPS 5,000 帯で、r8g は崩壊、r6i は高成功率を維持。
- 一方で QPS 6,000 以上は r6i でも継続的なエラーが増え、実運用不可判定となる。

---

## 運用ガイドライン

### 本番環境での推奨QPS設定

| 環境タイプ | 推奨上限QPS | 理由 |
|-----------|-------------|------|
| **通常運用** | **QPS 4,000** | Healthy / Congested ともに 100% 成功、安定運用可能 |
| **高安定性要求** | **QPS 3,000** | 余裕が大きく、瞬間障害の余地が小さい |
| **一時的なバースト** | **QPS 5,000** | 高成功率だが散発 timeout が発生するため要監視 |

### CloudWatch アラート推奨設定

```yaml
DBConnections:
  Warning: > 600
  Critical: > 1100

CPUUtilization:
  Warning: > 70
  Critical: > 85

SelectLatencyP99Ms:
  Warning: > 25
  Critical: > 60

TimeoutErrorsPer10s:
  Warning: > 20
  Critical: > 80
```

### インスタンス選定の示唆

| 想定QPS | 推奨インスタンスクラス | 備考 |
|---------|---------------------|------|
| 〜3,000 | db.r8g.4xlarge / db.r6i.4xlarge | どちらも安定域 |
| 3,001〜4,000 | db.r6i.4xlarge 優先 | r8gより安定余裕が大きい |
| 4,001〜5,000 | db.r6i.4xlarge（要監視） | timeout監視とリトライ実装が必須 |
| 5,001〜 | 上位クラスまたは分散構成を検討 | 4xlarge帯の実運用上限超過 |

---

## 制約事項

### テストパターンの特性

本テストは「接続 → SELECT 1 → 切断」パターンであり、以下の環境を模擬している。
- サーバーレス環境
- 短命な接続を大量に処理するケース
- コネクションプールを使わない環境

### 本番環境との差異

本番環境では以下の要素が性能に影響する。
- 複雑なクエリ
- トランザクション処理
- ロック競合
- ストレージI/O負荷
- 他ワークロードとの競合

### タイムアウト設定の影響

本テストのタイムアウト設定は 5,000ms。
- より短いタイムアウトでは、より低いQPSで限界に達する可能性がある。
- アプリケーション側のリトライ戦略次第で見かけの成功率は変化する。

---

## 参考資料

- [../db_r8g_4xlarge/REPORT.md](../db_r8g_4xlarge/REPORT.md)
- [../db_r8g_xlarge/REPORT.md](../db_r8g_xlarge/REPORT.md)
- https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/

---

**レポート作成日:** 2026-04-10  
**テストツールバージョン:** stress test v2  
**データソース:** `/results/db_r6i_4xlarge/batch.log`
