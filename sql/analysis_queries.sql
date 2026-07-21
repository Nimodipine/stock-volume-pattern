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