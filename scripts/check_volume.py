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
    SELECT day_direction,
           COUNT(*) AS num_days,
           SUM(volume) AS total_volume,
           ROUND(AVG(volume), 0) AS avg_volume
    FROM price_move_thresholds
    GROUP BY day_direction
""")
for row in cursor.fetchall():
    print(row)

cursor.close()
conn.close()