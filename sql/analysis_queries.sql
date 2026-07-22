-- Rolling average volume
CREATE VIEW volume_with_rolling_avg AS
SELECT
    ticker,
    date,
    close_adjusted,
    volume,
    AVG(volume) OVER (
        PARTITION BY ticker
        ORDER BY date
        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
    ) AS rolling_avg_volume
FROM historical_prices;

-- Volume ratio + spike bucket
CREATE VIEW volume_spikes AS
SELECT
    *,
    volume / NULLIF(rolling_avg_volume, 0) AS volume_ratio,
    CASE
        WHEN volume / NULLIF(rolling_avg_volume, 0) >= 3.0 THEN '3x+'
        WHEN volume / NULLIF(rolling_avg_volume, 0) >= 2.0 THEN '2x-3x'
        WHEN volume / NULLIF(rolling_avg_volume, 0) >= 1.5 THEN '1.5x-2x'
        ELSE 'normal'
    END AS spike_bucket
FROM volume_with_rolling_avg;

-- Forward returns (5 trading days later)
CREATE VIEW price_forward_returns AS
SELECT
    *,
    LEAD(close_adjusted, 5) OVER (PARTITION BY ticker ORDER BY date) AS price_5d_later,
    ROUND(
        (LEAD(close_adjusted, 5) OVER (PARTITION BY ticker ORDER BY date) - close_adjusted) / close_adjusted * 100,
        2
    ) AS pct_change_5d
FROM volume_spikes;

-- Direction of the day (up/down/unchanged)
CREATE VIEW volume_with_direction AS
SELECT
    ticker,
    date,
    close_adjusted,
    volume,
    LAG(close_adjusted) OVER (PARTITION BY ticker ORDER BY date) AS prev_close,
    CASE
        WHEN close_adjusted > LAG(close_adjusted) OVER (PARTITION BY ticker ORDER BY date) THEN 'up'
        WHEN close_adjusted < LAG(close_adjusted) OVER (PARTITION BY ticker ORDER BY date) THEN 'down'
        ELSE 'unchanged'
    END AS day_direction
FROM historical_prices;

-- Win rate summary
SELECT
    spike_bucket,
    COUNT(*) AS total_events,
    SUM(CASE WHEN pct_change_5d > 0 THEN 1 ELSE 0 END) AS up_count,
    SUM(CASE WHEN pct_change_5d < 0 THEN 1 ELSE 0 END) AS down_count,
    ROUND(SUM(CASE WHEN pct_change_5d > 0 THEN 1 ELSE 0 END) / COUNT(*) * 100, 1) AS pct_chance_up,
    ROUND(SUM(CASE WHEN pct_change_5d < 0 THEN 1 ELSE 0 END) / COUNT(*) * 100, 1) AS pct_chance_down,
    ROUND(AVG(pct_change_5d), 2) AS avg_pct_move
FROM price_forward_returns
WHERE pct_change_5d IS NOT NULL
GROUP BY spike_bucket
ORDER BY spike_bucket;

-- Win rate summary view (queryable directly from Power BI)
CREATE VIEW win_rate_summary AS
SELECT
    spike_bucket,
    COUNT(*) AS total_events,
    SUM(CASE WHEN pct_change_5d > 0 THEN 1 ELSE 0 END) AS up_count,
    SUM(CASE WHEN pct_change_5d < 0 THEN 1 ELSE 0 END) AS down_count,
    ROUND(SUM(CASE WHEN pct_change_5d > 0 THEN 1 ELSE 0 END) / COUNT(*) * 100, 1) AS pct_chance_up,
    ROUND(SUM(CASE WHEN pct_change_5d < 0 THEN 1 ELSE 0 END) / COUNT(*) * 100, 1) AS pct_chance_down,
    ROUND(SUM(CASE WHEN pct_change_5d = 0 THEN 1 ELSE 0 END) / COUNT(*) * 100, 1) AS pct_chance_unchanged,
    ROUND(AVG(pct_change_5d), 2) AS avg_pct_move
FROM price_forward_returns
WHERE pct_change_5d IS NOT NULL
GROUP BY spike_bucket;

-- Volume transitions (day-over-day direction change combined with volume spike)
CREATE VIEW volume_transitions AS
SELECT
    *,
    LAG(day_direction) OVER (PARTITION BY ticker ORDER BY date) AS prev_direction,
    CASE
        WHEN LAG(day_direction) OVER (PARTITION BY ticker ORDER BY date) = 'down' AND day_direction = 'up' THEN 'sell_to_buy'
        WHEN LAG(day_direction) OVER (PARTITION BY ticker ORDER BY date) = 'up' AND day_direction = 'up' THEN 'buy_continuation'
        WHEN LAG(day_direction) OVER (PARTITION BY ticker ORDER BY date) = 'down' AND day_direction = 'down' THEN 'sell_continuation'
        WHEN LAG(day_direction) OVER (PARTITION BY ticker ORDER BY date) = 'up' AND day_direction = 'down' THEN 'buy_to_sell'
        ELSE 'unchanged_or_na'
    END AS transition_type
FROM price_forward_returns;

-- Win rate by transition type + spike bucket
CREATE VIEW transition_win_rate AS
SELECT
    transition_type,
    spike_bucket,
    COUNT(*) AS total_events,
    ROUND(SUM(CASE WHEN pct_change_5d > 0 THEN 1 ELSE 0 END) / COUNT(*) * 100, 1) AS pct_chance_up,
    ROUND(SUM(CASE WHEN pct_change_5d < 0 THEN 1 ELSE 0 END) / COUNT(*) * 100, 1) AS pct_chance_down,
    ROUND(AVG(pct_change_5d), 2) AS avg_pct_move
FROM volume_transitions
WHERE pct_change_5d IS NOT NULL
GROUP BY transition_type, spike_bucket
ORDER BY transition_type, spike_bucket;