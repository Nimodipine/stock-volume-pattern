import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

conn = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT")),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME"),
    ssl_disabled=False
)
cursor = conn.cursor()

# Drop in reverse dependency order so re-running doesn't error
cursor.execute("DROP VIEW IF EXISTS transition_win_rate")
cursor.execute("DROP VIEW IF EXISTS volume_transitions")
cursor.execute("DROP VIEW IF EXISTS win_rate_summary")
cursor.execute("DROP VIEW IF EXISTS price_move_thresholds")
cursor.execute("DROP VIEW IF EXISTS price_path_forward")
# legacy views from the old point-in-time (5-day) approach - drop if present
cursor.execute("DROP VIEW IF EXISTS price_forward_returns")
cursor.execute("DROP VIEW IF EXISTS volume_spikes")
cursor.execute("DROP VIEW IF EXISTS volume_with_rolling_avg")

# Rolling average volume + day direction (up/down/unchanged vs previous close)
cursor.execute("""
CREATE VIEW volume_with_rolling_avg AS
SELECT
    ticker,
    date,
    open_price,
    high_price,
    low_price,
    close_adjusted,
    volume,
    AVG(volume) OVER (
        PARTITION BY ticker ORDER BY date
        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
    ) AS rolling_avg_volume,
    LAG(close_adjusted) OVER (PARTITION BY ticker ORDER BY date) AS prev_close,
    CASE
        WHEN close_adjusted > LAG(close_adjusted) OVER (PARTITION BY ticker ORDER BY date) THEN 'up'
        WHEN close_adjusted < LAG(close_adjusted) OVER (PARTITION BY ticker ORDER BY date) THEN 'down'
        ELSE 'unchanged'
    END AS day_direction
FROM historical_prices
""")

# Volume ratio + spike bucket
cursor.execute("""
CREATE VIEW volume_spikes AS
SELECT *,
    volume / NULLIF(rolling_avg_volume, 0) AS volume_ratio,
    CASE
        WHEN volume / NULLIF(rolling_avg_volume, 0) >= 3.0 THEN '3x+'
        WHEN volume / NULLIF(rolling_avg_volume, 0) >= 2.0 THEN '2x-3x'
        WHEN volume / NULLIF(rolling_avg_volume, 0) >= 1.5 THEN '1.5x-2x'
        ELSE 'normal'
    END AS spike_bucket
FROM volume_with_rolling_avg
""")

# Path-based forward move: the highest high and lowest low reached over the
# next 10 and next 20 trading days (~2 weeks and ~1 month). Using the daily
# high/low (instead of just the closing price N days later) captures moves
# that happen and reverse within the window, which matters a lot for a 3x
# leveraged product like TQQQ.
cursor.execute("""
CREATE VIEW price_path_forward AS
SELECT *,
    MAX(high_price) OVER (
        PARTITION BY ticker ORDER BY date
        ROWS BETWEEN 1 FOLLOWING AND 10 FOLLOWING
    ) AS max_high_10d,
    MAX(high_price) OVER (
        PARTITION BY ticker ORDER BY date
        ROWS BETWEEN 1 FOLLOWING AND 20 FOLLOWING
    ) AS max_high_20d,
    MIN(low_price) OVER (
        PARTITION BY ticker ORDER BY date
        ROWS BETWEEN 1 FOLLOWING AND 10 FOLLOWING
    ) AS min_low_10d,
    MIN(low_price) OVER (
        PARTITION BY ticker ORDER BY date
        ROWS BETWEEN 1 FOLLOWING AND 20 FOLLOWING
    ) AS min_low_20d
FROM volume_spikes
""")
print("price_path_forward view created.")

# Turn those extremes into pct-move figures and 10%/20% threshold hit flags.
# (Built as a separate view since MySQL won't let a SELECT reuse a window
# function's own alias in the same SELECT list for further math.)
cursor.execute("""
CREATE VIEW price_move_thresholds AS
SELECT *,
    ROUND((max_high_10d - close_adjusted) / close_adjusted * 100, 2) AS max_pct_up_10d,
    ROUND((max_high_20d - close_adjusted) / close_adjusted * 100, 2) AS max_pct_up_20d,
    ROUND((close_adjusted - min_low_10d) / close_adjusted * 100, 2) AS max_pct_down_10d,
    ROUND((close_adjusted - min_low_20d) / close_adjusted * 100, 2) AS max_pct_down_20d,
    CASE WHEN max_high_10d >= close_adjusted * 1.10 THEN 1 ELSE 0 END AS hit_up_10pct_within_10d,
    CASE WHEN max_high_20d >= close_adjusted * 1.10 THEN 1 ELSE 0 END AS hit_up_10pct_within_20d,
    CASE WHEN max_high_20d >= close_adjusted * 1.20 THEN 1 ELSE 0 END AS hit_up_20pct_within_20d,
    CASE WHEN min_low_10d <= close_adjusted * 0.90 THEN 1 ELSE 0 END AS hit_down_10pct_within_10d,
    CASE WHEN min_low_20d <= close_adjusted * 0.90 THEN 1 ELSE 0 END AS hit_down_10pct_within_20d,
    CASE WHEN min_low_20d <= close_adjusted * 0.80 THEN 1 ELSE 0 END AS hit_down_20pct_within_20d
FROM price_path_forward
""")
print("price_move_thresholds view created.")

print("Views created successfully.")

cursor.execute("""
CREATE VIEW win_rate_summary AS
SELECT
    spike_bucket,
    COUNT(*) AS total_events,
    SUM(hit_up_10pct_within_10d) AS events_hit_10pct_10d,
    ROUND(SUM(hit_up_10pct_within_10d) / COUNT(*) * 100, 1) AS pct_chance_10pct_within_10d,
    SUM(hit_up_10pct_within_20d) AS events_hit_10pct_20d,
    ROUND(SUM(hit_up_10pct_within_20d) / COUNT(*) * 100, 1) AS pct_chance_10pct_within_20d,
    SUM(hit_up_20pct_within_20d) AS events_hit_20pct_20d,
    ROUND(SUM(hit_up_20pct_within_20d) / COUNT(*) * 100, 1) AS pct_chance_20pct_within_20d,
    SUM(hit_down_10pct_within_10d) AS events_hit_down10pct_10d,
    ROUND(SUM(hit_down_10pct_within_10d) / COUNT(*) * 100, 1) AS pct_chance_down10pct_within_10d,
    SUM(hit_down_10pct_within_20d) AS events_hit_down10pct_20d,
    ROUND(SUM(hit_down_10pct_within_20d) / COUNT(*) * 100, 1) AS pct_chance_down10pct_within_20d,
    SUM(hit_down_20pct_within_20d) AS events_hit_down20pct_20d,
    ROUND(SUM(hit_down_20pct_within_20d) / COUNT(*) * 100, 1) AS pct_chance_down20pct_within_20d,
    ROUND(AVG(max_pct_up_10d), 2) AS avg_max_move_10d,
    ROUND(AVG(max_pct_up_20d), 2) AS avg_max_move_20d,
    ROUND(AVG(max_pct_down_10d), 2) AS avg_max_drop_10d,
    ROUND(AVG(max_pct_down_20d), 2) AS avg_max_drop_20d
FROM price_move_thresholds
WHERE max_pct_up_20d IS NOT NULL
GROUP BY spike_bucket
""")
print("win_rate_summary view created.")

# --- NEW: volume transitions (day-over-day direction change) ---
cursor.execute("""
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
FROM price_move_thresholds
""")
print("volume_transitions view created.")

# --- NEW: win rate by transition type + spike bucket ---
cursor.execute("""
CREATE VIEW transition_win_rate AS
SELECT
    transition_type,
    spike_bucket,
    COUNT(*) AS total_events,
    ROUND(SUM(hit_up_10pct_within_10d) / COUNT(*) * 100, 1) AS pct_chance_10pct_within_10d,
    ROUND(SUM(hit_up_10pct_within_20d) / COUNT(*) * 100, 1) AS pct_chance_10pct_within_20d,
    ROUND(SUM(hit_up_20pct_within_20d) / COUNT(*) * 100, 1) AS pct_chance_20pct_within_20d,
    ROUND(SUM(hit_down_10pct_within_10d) / COUNT(*) * 100, 1) AS pct_chance_down10pct_within_10d,
    ROUND(SUM(hit_down_10pct_within_20d) / COUNT(*) * 100, 1) AS pct_chance_down10pct_within_20d,
    ROUND(SUM(hit_down_20pct_within_20d) / COUNT(*) * 100, 1) AS pct_chance_down20pct_within_20d,
    ROUND(AVG(max_pct_up_10d), 2) AS avg_max_move_10d,
    ROUND(AVG(max_pct_up_20d), 2) AS avg_max_move_20d,
    ROUND(AVG(max_pct_down_10d), 2) AS avg_max_drop_10d,
    ROUND(AVG(max_pct_down_20d), 2) AS avg_max_drop_20d
FROM volume_transitions
WHERE max_pct_up_20d IS NOT NULL
GROUP BY transition_type, spike_bucket
ORDER BY transition_type, spike_bucket
""")
print("transition_win_rate view created.")

# Win rate summary: probability of hitting +10% / +20% AND -10% / -20% within the window
cursor.execute("""
SELECT spike_bucket, total_events,
    pct_chance_10pct_within_10d,
    pct_chance_20pct_within_20d,
    pct_chance_down10pct_within_10d,
    pct_chance_down20pct_within_20d,
    avg_max_move_10d,
    avg_max_drop_10d
FROM win_rate_summary
ORDER BY spike_bucket
""")

for row in cursor.fetchall():
    print(row)

# Quick check on day_direction distribution
cursor.execute("""
SELECT spike_bucket, day_direction, COUNT(*) 
FROM volume_spikes 
GROUP BY spike_bucket, day_direction
ORDER BY spike_bucket, day_direction
""")
print("\nDay direction by spike bucket:")
for row in cursor.fetchall():
    print(row)

# --- Transition win rate output ---
cursor.execute("""
SELECT transition_type, spike_bucket, total_events,
    pct_chance_10pct_within_10d,
    pct_chance_20pct_within_20d,
    pct_chance_down10pct_within_10d,
    pct_chance_down20pct_within_20d
FROM transition_win_rate
ORDER BY transition_type, spike_bucket
""")
print("\nTransition win rate:")
for row in cursor.fetchall():
    print(row)

cursor.close()
conn.close()