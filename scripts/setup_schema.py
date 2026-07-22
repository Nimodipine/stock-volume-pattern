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

# --- stock_data table ---
cursor.execute("""
CREATE TABLE IF NOT EXISTS stock_data (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    volume BIGINT NOT NULL,
    timestamp DATETIME NOT NULL,
    INDEX idx_ticker_time (ticker, timestamp)
)
""")
print("stock_data table created (or already exists).")

# --- historical_prices table ---
cursor.execute("""
CREATE TABLE IF NOT EXISTS historical_prices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    close_raw DECIMAL(10,2),
    close_adjusted DECIMAL(10,2),
    volume BIGINT NOT NULL,
    split_coefficient DECIMAL(10,4),
    INDEX idx_ticker_date (ticker, date)
)
""")
print("historical_prices table created (or already exists).")

# --- Add Open/High/Low columns (only runs once; safe to re-run) ---
try:
    cursor.execute("""
        ALTER TABLE historical_prices
        ADD COLUMN open_price DECIMAL(10,2),
        ADD COLUMN high_price DECIMAL(10,2),
        ADD COLUMN low_price DECIMAL(10,2)
    """)
    print("Added open_price, high_price, low_price columns.")
except mysql.connector.Error as err:
    if err.errno == 1060:  # Duplicate column error
        print("Columns already exist, skipping.")
    else:
        raise

# --- Unique constraint so re-running fetch_historical.py upserts instead of
# --- inserting duplicate rows for dates that already exist ---
try:
    cursor.execute("""
        ALTER TABLE historical_prices
        ADD UNIQUE KEY uniq_ticker_date (ticker, date)
    """)
    print("Added unique constraint on (ticker, date).")
except mysql.connector.Error as err:
    if err.errno == 1061:  # Duplicate key name (already exists)
        print("Unique constraint already exists, skipping.")
    else:
        raise

# --- Verify ---
cursor.execute("SHOW TABLES")
print(cursor.fetchall())

cursor.execute("DESCRIBE historical_prices")
for row in cursor.fetchall():
    print(row)

cursor.close()
conn.close()