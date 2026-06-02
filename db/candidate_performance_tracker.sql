-- Candidate performance tracking for PRISM-INSIGHT optimization feedback.
--
-- Purpose:
--   Track both traded and skipped candidates so future scoring can learn which
--   triggers, sectors, and agent signals actually produced returns.

CREATE TABLE IF NOT EXISTS candidate_performance_tracker (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    company_name TEXT,
    market TEXT,
    sector TEXT,
    trigger_type TEXT,
    trigger_mode TEXT,
    selected_at TEXT NOT NULL,
    signal_date TEXT,
    entry_decision TEXT NOT NULL DEFAULT 'unknown',
    no_entry_reason TEXT,
    profit_score REAL,
    raw_edge_score REAL,
    risk_penalty REAL,
    expected_value REAL,
    buy_score REAL,
    risk_reward_ratio REAL,
    price_at_signal REAL,
    target_price REAL,
    stop_loss_price REAL,
    return_7d REAL,
    return_14d REAL,
    return_30d REAL,
    max_gain_30d REAL,
    max_drawdown_30d REAL,
    realized_return REAL,
    realized_exit_reason TEXT,
    agent_scores_json TEXT,
    score_reasons_json TEXT,
    risk_governor_reasons_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_candidate_perf_ticker
    ON candidate_performance_tracker (ticker, selected_at);

CREATE INDEX IF NOT EXISTS idx_candidate_perf_trigger
    ON candidate_performance_tracker (trigger_type, selected_at);

CREATE INDEX IF NOT EXISTS idx_candidate_perf_sector
    ON candidate_performance_tracker (sector, selected_at);

CREATE INDEX IF NOT EXISTS idx_candidate_perf_decision
    ON candidate_performance_tracker (entry_decision, selected_at);

CREATE VIEW IF NOT EXISTS trigger_performance_summary AS
SELECT
    trigger_type,
    COUNT(*) AS sample_count,
    AVG(return_7d) AS avg_return_7d,
    AVG(return_14d) AS avg_return_14d,
    AVG(return_30d) AS avg_return_30d,
    AVG(CASE WHEN return_14d > 0 THEN 1.0 ELSE 0.0 END) * 100.0 AS win_rate_14d,
    AVG(max_gain_30d) AS avg_max_gain_30d,
    AVG(max_drawdown_30d) AS avg_max_drawdown_30d
FROM candidate_performance_tracker
WHERE trigger_type IS NOT NULL
GROUP BY trigger_type;

CREATE VIEW IF NOT EXISTS profit_score_bucket_summary AS
SELECT
    CASE
        WHEN profit_score >= 80 THEN '80+'
        WHEN profit_score >= 70 THEN '70-79'
        WHEN profit_score >= 60 THEN '60-69'
        WHEN profit_score >= 50 THEN '50-59'
        ELSE '0-49'
    END AS profit_score_bucket,
    COUNT(*) AS sample_count,
    AVG(return_14d) AS avg_return_14d,
    AVG(return_30d) AS avg_return_30d,
    AVG(CASE WHEN return_14d > 0 THEN 1.0 ELSE 0.0 END) * 100.0 AS win_rate_14d
FROM candidate_performance_tracker
WHERE profit_score IS NOT NULL
GROUP BY profit_score_bucket;
