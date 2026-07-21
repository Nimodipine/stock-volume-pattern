import os
import requests
import mysql.connector
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
TICKERS = ["TQQQ"]  # add/remove tickers here

def fetch_quote(symbol):
    url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={API_KEY}"
    response = requests.get(url)
    data = response.json()

    quote = data.get("Global Quote")
    if not quote or "05. price" not in quote:
        print(f"No data returned for {symbol}: {data}")
        return None

    return {
        "ticker": quote["01. symbol"],
        "price": float(quote["05. price"]),
        "volume": int(quote["06. volume"]),
        "timestamp": datetime.now()  # when WE fetched it, not market timestamp
    }

def insert_quote(cursor, quote):
    cursor.execute("""
        INSERT INTO stock_data (ticker, price, volume, timestamp)
        VALUES (%s, %s, %s, %s)
    """, (quote["ticker"], quote["price"], quote["volume"], quote["timestamp"]))

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

    for ticker in TICKERS:
        quote = fetch_quote(ticker)
        if quote:
            insert_quote(cursor, quote)
            print(f"Inserted {quote['ticker']}: price={quote['price']}, volume={quote['volume']}")

    conn.commit()
    cursor.close()
    conn.close()

if __name__ == "__main__":
    main()