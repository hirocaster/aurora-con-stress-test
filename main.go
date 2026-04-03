package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"os"
	"sort"
	"sync"
	"time"

	"github.com/go-sql-driver/mysql"
)

type Config struct {
	Host                 string
	Port                 int
	User                 string
	Password             string
	Database             string
	SQL                  string
	Concurrency          int
	Duration             time.Duration
	ConnectTimeout       time.Duration
	QueryTimeout         time.Duration
	RunID                string
	AggregateLogPath     string
	ErrorLogPath         string
	AggregateWindow      time.Duration
	SleepBetweenAttempts time.Duration
	
	// Spike settings
	SpikeConcurrency     int
	SpikeDuration        time.Duration
	SpikeInterval        time.Duration
}

type TrialResult struct {
	Timestamp          time.Time
	WorkerID           int
	AttemptID          int64
	ConnectLatencyMs   *int64
	QueryLatencyMs     *int64
	DisconnectLatencyMs *int64
	TotalLatencyMs     *int64
	Success            bool
	FailurePhase       *string
	ErrorMessage       *string
}

type BucketStats struct {
	BucketStart            time.Time `json:"bucket_start"`
	BucketEnd              time.Time `json:"bucket_end"`
	RunID                  string    `json:"run_id"`
	ConfiguredConcurrency  int       `json:"configured_concurrency"`
	Attempts               int       `json:"attempts"`
	ConnectSuccessCount    int       `json:"connect_success_count"`
	ConnectFailureCount    int       `json:"connect_failure_count"`
	QuerySuccessCount      int       `json:"query_success_count"`
	QueryFailureCount      int       `json:"query_failure_count"`
	DisconnectSuccessCount int       `json:"disconnect_success_count"`
	DisconnectFailureCount int       `json:"disconnect_failure_count"`
	OverallSuccessCount    int       `json:"overall_success_count"`
	OverallFailureCount    int       `json:"overall_failure_count"`

	ConnectSuccessRate    float64 `json:"connect_success_rate"`
	QuerySuccessRate      float64 `json:"query_success_rate"`
	DisconnectSuccessRate float64 `json:"disconnect_success_rate"`
	OverallSuccessRate    float64 `json:"overall_success_rate"`
	ThroughputPerSec      float64 `json:"throughput_per_sec"`

	ConnectAvgMs float64 `json:"connect_avg_ms"`
	ConnectP50Ms int64   `json:"connect_p50_ms"`
	ConnectP90Ms int64   `json:"connect_p90_ms"`
	ConnectP95Ms int64   `json:"connect_p95_ms"`
	ConnectP99Ms int64   `json:"connect_p99_ms"`
	ConnectMaxMs int64   `json:"connect_max_ms"`

	QueryAvgMs float64 `json:"query_avg_ms"`
	QueryP50Ms int64   `json:"query_p50_ms"`
	QueryP90Ms int64   `json:"query_p90_ms"`
	QueryP95Ms int64   `json:"query_p95_ms"`
	QueryP99Ms int64   `json:"query_p99_ms"`
	QueryMaxMs int64   `json:"query_max_ms"`

	TotalAvgMs float64 `json:"total_avg_ms"`
	TotalP50Ms int64   `json:"total_p50_ms"`
	TotalP90Ms int64   `json:"total_p90_ms"`
	TotalP95Ms int64   `json:"total_p95_ms"`
	TotalP99Ms int64   `json:"total_p99_ms"`
	TotalMaxMs int64   `json:"total_max_ms"`

	FailurePhaseCounts map[string]int `json:"failure_phase_counts"`
	ErrorTypeCounts    map[string]int `json:"error_type_counts"`
}

type ErrorLog struct {
	Timestamp           string `json:"timestamp"`
	RunID               string `json:"run_id"`
	WorkerID            int    `json:"worker_id"`
	AttemptID           int64  `json:"attempt_id"`
	TargetHost          string `json:"target_host"`
	TargetPort          int    `json:"target_port"`
	FailurePhase        string `json:"failure_phase"`
	ErrorMessage        string `json:"error_message"`
	ConnectLatencyMs    *int64 `json:"connect_latency_ms"`
	QueryLatencyMs      *int64 `json:"query_latency_ms"`
	DisconnectLatencyMs *int64 `json:"disconnect_latency_ms"`
	TotalLatencyMs      *int64 `json:"total_latency_ms"`
}

func calcPercentiles(latencies []int64) (avg float64, p50, p90, p95, p99, max int64) {
	if len(latencies) == 0 {
		return 0, 0, 0, 0, 0, 0
	}
	sort.Slice(latencies, func(i, j int) bool { return latencies[i] < latencies[j] })
	
	var sum int64
	for _, l := range latencies {
		sum += l
	}
	avg = float64(sum) / float64(len(latencies))
	
	n := float64(len(latencies))
	p50 = latencies[int(n*0.50)]
	p90 = latencies[int(n*0.90)]
	p95 = latencies[int(n*0.95)]
	p99 = latencies[int(n*0.99)]
	max = latencies[len(latencies)-1]
	
	return
}

func aggregator(ctx context.Context, cfg Config, results <-chan TrialResult, wg *sync.WaitGroup) {
	defer wg.Done()

	aggFile, err := os.OpenFile(cfg.AggregateLogPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		log.Fatalf("failed to open aggregate log: %v", err)
	}
	defer aggFile.Close()
	aggEncoder := json.NewEncoder(aggFile)

	var errFile *os.File
	var errEncoder *json.Encoder
	if cfg.ErrorLogPath != "" {
		errFile, err = os.OpenFile(cfg.ErrorLogPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
		if err != nil {
			log.Fatalf("failed to open error log: %v", err)
		}
		defer errFile.Close()
		errEncoder = json.NewEncoder(errFile)
	}

	ticker := time.NewTicker(cfg.AggregateWindow)
	defer ticker.Stop()

	var currentBucket []TrialResult
	bucketStart := time.Now()

	flushBucket := func(now time.Time) {
		if len(currentBucket) == 0 {
			bucketStart = now
			return
		}

		stats := BucketStats{
			BucketStart:           bucketStart,
			BucketEnd:             now,
			RunID:                 cfg.RunID,
			ConfiguredConcurrency: cfg.Concurrency, // Base concurrency
			Attempts:              len(currentBucket),
			FailurePhaseCounts:    make(map[string]int),
			ErrorTypeCounts:       make(map[string]int),
		}

		var connLatencies, queryLatencies, totalLatencies []int64

		for _, r := range currentBucket {
			if r.Success {
				stats.OverallSuccessCount++
				stats.ConnectSuccessCount++
				stats.QuerySuccessCount++
				stats.DisconnectSuccessCount++
				
				connLatencies = append(connLatencies, *r.ConnectLatencyMs)
				queryLatencies = append(queryLatencies, *r.QueryLatencyMs)
				totalLatencies = append(totalLatencies, *r.TotalLatencyMs)
			} else {
				stats.OverallFailureCount++
				stats.FailurePhaseCounts[*r.FailurePhase]++
				stats.ErrorTypeCounts[*r.ErrorMessage]++

				if *r.FailurePhase == "connect" {
					stats.ConnectFailureCount++
				} else {
					stats.ConnectSuccessCount++
					connLatencies = append(connLatencies, *r.ConnectLatencyMs)
					if *r.FailurePhase == "query" {
						stats.QueryFailureCount++
					} else {
						stats.QuerySuccessCount++
						queryLatencies = append(queryLatencies, *r.QueryLatencyMs)
						stats.DisconnectFailureCount++
					}
				}

				if errEncoder != nil {
					errLog := ErrorLog{
						Timestamp:           r.Timestamp.Format(time.RFC3339Nano),
						RunID:               cfg.RunID,
						WorkerID:            r.WorkerID,
						AttemptID:           r.AttemptID,
						TargetHost:          cfg.Host,
						TargetPort:          cfg.Port,
						FailurePhase:        *r.FailurePhase,
						ErrorMessage:        *r.ErrorMessage,
						ConnectLatencyMs:    r.ConnectLatencyMs,
						QueryLatencyMs:      r.QueryLatencyMs,
						DisconnectLatencyMs: r.DisconnectLatencyMs,
						TotalLatencyMs:      r.TotalLatencyMs,
					}
					errEncoder.Encode(errLog)
				}
			}
		}

		stats.ConnectSuccessRate = float64(stats.ConnectSuccessCount) / float64(stats.Attempts)
		if stats.ConnectSuccessCount > 0 {
			stats.QuerySuccessRate = float64(stats.QuerySuccessCount) / float64(stats.ConnectSuccessCount)
		}
		if stats.QuerySuccessCount > 0 {
			stats.DisconnectSuccessRate = float64(stats.DisconnectSuccessCount) / float64(stats.QuerySuccessCount)
		}
		stats.OverallSuccessRate = float64(stats.OverallSuccessCount) / float64(stats.Attempts)
		
		durationSecs := now.Sub(bucketStart).Seconds()
		if durationSecs > 0 {
			stats.ThroughputPerSec = float64(stats.Attempts) / durationSecs
		}

		stats.ConnectAvgMs, stats.ConnectP50Ms, stats.ConnectP90Ms, stats.ConnectP95Ms, stats.ConnectP99Ms, stats.ConnectMaxMs = calcPercentiles(connLatencies)
		stats.QueryAvgMs, stats.QueryP50Ms, stats.QueryP90Ms, stats.QueryP95Ms, stats.QueryP99Ms, stats.QueryMaxMs = calcPercentiles(queryLatencies)
		stats.TotalAvgMs, stats.TotalP50Ms, stats.TotalP90Ms, stats.TotalP95Ms, stats.TotalP99Ms, stats.TotalMaxMs = calcPercentiles(totalLatencies)

		aggEncoder.Encode(stats)

		currentBucket = currentBucket[:0]
		bucketStart = now
	}

	for {
		select {
		case r, ok := <-results:
			if !ok {
				flushBucket(time.Now())
				return
			}
			currentBucket = append(currentBucket, r)
		case t := <-ticker.C:
			flushBucket(t)
		}
	}
}

func worker(ctx context.Context, id int, cfg Config, results chan<- TrialResult, wg *sync.WaitGroup) {
	defer wg.Done()

	dsn := fmt.Sprintf("%s:%s@tcp(%s:%d)/%s?timeout=%s&readTimeout=%s&parseTime=true",
		cfg.User, cfg.Password, cfg.Host, cfg.Port, cfg.Database,
		cfg.ConnectTimeout.String(), cfg.QueryTimeout.String())

	var attemptID int64 = 0

	for {
		select {
		case <-ctx.Done():
			return
		default:
			attemptID++
			runTrial(ctx, id, attemptID, dsn, cfg, results)
			if cfg.SleepBetweenAttempts > 0 {
				time.Sleep(cfg.SleepBetweenAttempts)
			}
		}
	}
}

func ptr(v int64) *int64 { return &v }

func runTrial(ctx context.Context, workerID int, attemptID int64, dsn string, cfg Config, results chan<- TrialResult) {
	startTotal := time.Now()
	res := TrialResult{
		Timestamp: startTotal,
		WorkerID:  workerID,
		AttemptID: attemptID,
		Success:   false,
	}

	defer func() {
		// テスト時間が終了してキャンセルされた場合は、終了間際のノイズ（エラー）として記録しない
		if ctx.Err() != nil {
			return
		}
		total := time.Since(startTotal).Milliseconds()
		res.TotalLatencyMs = &total
		results <- res
	}()

	// Connect
	startConnect := time.Now()
	db, err := sql.Open("mysql", dsn)
	if err != nil {
		phase := "connect"
		errMsg := err.Error()
		res.FailurePhase = &phase
		res.ErrorMessage = &errMsg
		return
	}
	defer db.Close()

	db.SetMaxOpenConns(1)
	db.SetMaxIdleConns(0)
	db.SetConnMaxLifetime(0)

	err = db.PingContext(ctx)
	connLatency := time.Since(startConnect).Milliseconds()
	res.ConnectLatencyMs = ptr(connLatency)
	
	if err != nil {
		phase := "connect"
		errMsg := err.Error()
		res.FailurePhase = &phase
		res.ErrorMessage = &errMsg
		return
	}

	// Query
	startQuery := time.Now()
	rows, err := db.QueryContext(ctx, cfg.SQL)
	if err != nil {
		phase := "query"
		errMsg := err.Error()
		res.FailurePhase = &phase
		res.ErrorMessage = &errMsg
		return
	}
	for rows.Next() {}
	err = rows.Err()
	rows.Close()

	queryLatency := time.Since(startQuery).Milliseconds()
	res.QueryLatencyMs = ptr(queryLatency)

	if err != nil {
		phase := "query"
		errMsg := err.Error()
		res.FailurePhase = &phase
		res.ErrorMessage = &errMsg
		return
	}

	// Disconnect
	startDisconnect := time.Now()
	err = db.Close()
	discLatency := time.Since(startDisconnect).Milliseconds()
	res.DisconnectLatencyMs = ptr(discLatency)

	if err != nil {
		phase := "disconnect"
		errMsg := err.Error()
		res.FailurePhase = &phase
		res.ErrorMessage = &errMsg
		return
	}

	res.Success = true
}

func spikeManager(ctx context.Context, cfg Config, results chan<- TrialResult, wg *sync.WaitGroup) {
	defer wg.Done()
	if cfg.SpikeConcurrency <= 0 || cfg.SpikeInterval <= 0 || cfg.SpikeDuration <= 0 {
		return
	}

	ticker := time.NewTicker(cfg.SpikeInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			log.Printf("🔥 SPIKE TRIGGERED: Starting %d additional concurrent workers for %s", cfg.SpikeConcurrency, cfg.SpikeDuration)
			spikeCtx, spikeCancel := context.WithTimeout(ctx, cfg.SpikeDuration)
			
			var spikeWg sync.WaitGroup
			for i := 0; i < cfg.SpikeConcurrency; i++ {
				spikeWg.Add(1)
				wg.Add(1) // Track in main wait group to prevent channel closing too early
				go func(workerID int) {
					defer wg.Done()
					worker(spikeCtx, workerID, cfg, results, &spikeWg)
				}(cfg.Concurrency + i)
			}
			
			// Wait and cleanup in background to not block the next spike
			go func() {
				spikeWg.Wait()
				spikeCancel()
				log.Printf("📉 SPIKE ENDED: Additional workers stopped.")
			}()
		}
	}
}

func main() {
	mysql.SetLogger(log.New(io.Discard, "", 0))
	cfg := Config{}
	flag.StringVar(&cfg.Host, "host", "127.0.0.1", "Target MySQL host")
	flag.IntVar(&cfg.Port, "port", 3306, "Target MySQL port")
	flag.StringVar(&cfg.User, "user", "root", "MySQL user")
	flag.StringVar(&cfg.Password, "password", "", "MySQL password")
	flag.StringVar(&cfg.Database, "database", "", "MySQL database")
	flag.StringVar(&cfg.SQL, "sql", "SELECT 1", "SQL query to execute")
	flag.IntVar(&cfg.Concurrency, "concurrency", 10, "Number of concurrent workers")
	flag.DurationVar(&cfg.Duration, "duration", 60*time.Second, "Test duration")
	flag.DurationVar(&cfg.ConnectTimeout, "connect_timeout", 5*time.Second, "Connection timeout")
	flag.DurationVar(&cfg.QueryTimeout, "query_timeout", 10*time.Second, "Query timeout")
	flag.StringVar(&cfg.RunID, "run_id", fmt.Sprintf("run-%d", time.Now().Unix()), "Identifier for this test run")
	flag.StringVar(&cfg.AggregateLogPath, "aggregate_log_path", "aggregate.jsonl", "Path to output aggregate log")
	flag.StringVar(&cfg.ErrorLogPath, "error_log_path", "error.jsonl", "Path to output error detailed log")
	flag.DurationVar(&cfg.AggregateWindow, "aggregate_window", 10*time.Second, "Time window for aggregation bucket (1s, 10s, 1m)")
	flag.DurationVar(&cfg.SleepBetweenAttempts, "sleep_between_attempts_ms", 0, "Sleep between attempts")

	// Spike options
	flag.IntVar(&cfg.SpikeConcurrency, "spike_concurrency", 0, "Additional concurrency during a spike")
	flag.DurationVar(&cfg.SpikeDuration, "spike_duration", 0, "Duration of the spike")
	flag.DurationVar(&cfg.SpikeInterval, "spike_interval", 0, "Interval between spikes")

	flag.Parse()

	log.Printf("Starting stress test v2 against %s:%d", cfg.Host, cfg.Port)
	log.Printf("Run ID: %s, Base Concurrency: %d, Duration: %s, Window: %s", cfg.RunID, cfg.Concurrency, cfg.Duration, cfg.AggregateWindow)
	
	if cfg.SpikeConcurrency > 0 {
		log.Printf("Spike Config: +%d workers for %s every %s", cfg.SpikeConcurrency, cfg.SpikeDuration, cfg.SpikeInterval)
	}

	ctx, cancel := context.WithTimeout(context.Background(), cfg.Duration)
	defer cancel()

	results := make(chan TrialResult, (cfg.Concurrency+cfg.SpikeConcurrency)*100)

	var aggWg sync.WaitGroup
	aggWg.Add(1)
	go aggregator(context.Background(), cfg, results, &aggWg)

	var workerWg sync.WaitGroup
	for i := 0; i < cfg.Concurrency; i++ {
		workerWg.Add(1)
		go worker(ctx, i, cfg, results, &workerWg)
	}

	if cfg.SpikeConcurrency > 0 && cfg.SpikeDuration > 0 && cfg.SpikeInterval > 0 {
		workerWg.Add(1)
		go spikeManager(ctx, cfg, results, &workerWg)
	}

	workerWg.Wait()
	close(results)
	aggWg.Wait()

	log.Printf("Stress test completed. Aggregates in %s, errors in %s", cfg.AggregateLogPath, cfg.ErrorLogPath)
}
