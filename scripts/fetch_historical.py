import os
import yfinance as yf
import mysql.connector
from dotenv import load_dotenv

load_dotenv()
SYMBOL = "TQQQ"

def fetch_historical():
    ticker = yf.Ticker(SYMBOL)
    df = ticker.history(period="max", auto_adjust=False)
    return df

def insert_historical(cursor, df):
    count = 0
    for date, row in df.iterrows():
        cursor.execute("""
            INSERT INTO historical_prices
            (ticker, date, open_price, high_price, low_price, close_raw, close_adjusted, volume, split_coefficient)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                open_price = VALUES(open_price),
                high_price = VALUES(high_price),
                low_price = VALUES(low_price),
                close_raw = VALUES(close_raw),
                close_adjusted = VALUES(close_adjusted),
                volume = VALUES(volume),
                split_coefficient = VALUES(split_coefficient)
        """, (
            SYMBOL,
            date.strftime("%Y-%m-%d"),
            float(row["Open"]),
            float(row["High"]),
            float(row["Low"]),
            float(row["Close"]),
            float(row["Adj Close"]),
            int(row["Volume"]),
            float(row["Stock Splits"]) if row["Stock Splits"] != 0 else 1.0
        ))
        count += 1
    return count

def main():
    conn = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        ssl_disabled=False
    )
    cursor = conn.cursor()

    df = fetch_historical()
    count = insert_historical(cursor, df)
    conn.commit()
    print(f"Inserted {count} historical rows for {SYMBOL}.")

    cursor.close()
    conn.close()

if __name__ == "__main__":
    main()