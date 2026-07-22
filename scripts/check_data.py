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

cursor.execute("""
    SELECT date, close_raw, close_adjusted, volume
    FROM historical_prices
    WHERE date BETWEEN '2025-11-17' AND '2025-11-21'
    ORDER BY date
""")
for row in cursor.fetchall():
    print(row)

cursor.execute("""
    SELECT spike_bucket, COUNT(*) AS unchanged_count
    FROM price_forward_returns
    WHERE pct_change_5d = 0
    GROUP BY spike_bucket
""")
for row in cursor.fetchall():
    print(row)

cursor.execute("SELECT MIN(date), MAX(date), COUNT(*) FROM historical_prices")
print(cursor.fetchone())

cursor.close()
conn.close()