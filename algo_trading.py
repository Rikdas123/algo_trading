import json
import asyncio
import threading
import time
import requests
import websockets
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta

# ==== CONFIG ====
UPPER_THRESHOLD = 9_150_000   # ₹92.15 L
LOWER_THRESHOLD = 9_050_000   # ₹91.50 L
START_BTC = 10
START_INR = 1_00_00_000
USD_INR_DEFAULT = 88.0

# ==== GLOBAL STATE ====
latest_price = None
usd_inr = USD_INR_DEFAULT
btc_balance = START_BTC
inr_balance = START_INR
timestamps, prices = [], []
running = True
last_action = None  # “buy”, “sell”, or None


# ==== FETCH USD-INR ====
def get_usd_inr():
    global usd_inr
    while running:
        try:
            res = requests.get("https://open.er-api.com/v6/latest/USD", timeout=4)
            data = res.json()
            usd_inr = float(data["rates"]["INR"])
        except:
            pass
        time.sleep(30)


# ==== BYBIT STREAM ====
async def bybit_stream():
    global latest_price, usd_inr
    uri = "wss://stream.bybit.com/v5/public/linear"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"op": "subscribe", "args": ["tickers.BTCUSDT"]}))
        print("✅ Connected to Bybit BTCUSDT feed")
        while running:
            try:
                msg = await ws.recv()
                data = json.loads(msg)
                if "data" in data and "lastPrice" in data["data"]:
                    price_usdt = float(data["data"]["lastPrice"])
                    latest_price = price_usdt * usd_inr
            except:
                await asyncio.sleep(1)


def start_websocket():
    asyncio.run(bybit_stream())


# ==== AUTO TRADING LOGIC ====
def trading_logic():
    global btc_balance, inr_balance, last_action
    while running:
        if latest_price:
            # ---- SELL LOGIC ----
            if latest_price >= UPPER_THRESHOLD and last_action != "sell":
                print(f"📈 Above ₹{UPPER_THRESHOLD:,}, watching for peak…")
                peak_price = latest_price
                time.sleep(3)
                while True:
                    if latest_price > peak_price:
                        peak_price = latest_price
                        time.sleep(1)
                    elif latest_price < peak_price:  # reversal detected
                        if btc_balance >= 1:
                            btc_balance -= 1
                            inr_balance += latest_price
                            last_action = "sell"
                            print(f"💰 Sold 1 BTC at ₹{latest_price:,.0f} | BTC={btc_balance}, INR={inr_balance:,.0f}")
                        break

            # ---- BUY LOGIC ----
            elif latest_price <= LOWER_THRESHOLD and last_action != "buy":
                print(f"📉 Below ₹{LOWER_THRESHOLD:,}, watching for bottom…")
                bottom_price = latest_price
                time.sleep(3)
                while True:
                    if latest_price < bottom_price:
                        bottom_price = latest_price
                        time.sleep(1)
                    elif latest_price > bottom_price:  # reversal detected
                        if inr_balance >= latest_price:
                            btc_balance += 1
                            inr_balance -= latest_price
                            last_action = "buy"
                            print(f"🪙 Bought 1 BTC at ₹{latest_price:,.0f} | BTC={btc_balance}, INR={inr_balance:,.0f}")
                        break
        time.sleep(1)


# ==== MAIN PLOT ====
def main_plot():
    global latest_price

    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.set_title("💹 Real-Time Bitcoin Auto-Trading Simulator (₹ INR)", color="white")
    ax.set_xlabel("Time", color="gray")
    ax.set_ylabel("BTC Price (₹)", color="gray")

    # Threshold lines
    ax.axhline(UPPER_THRESHOLD, color='red', linestyle='--', linewidth=1.3,
               label=f"Sell ≥ ₹{UPPER_THRESHOLD/1e5:.2f}L")
    ax.axhline(LOWER_THRESHOLD, color='cyan', linestyle='--', linewidth=1.3,
               label=f"Buy ≤ ₹{LOWER_THRESHOLD/1e5:.2f}L")
    ax.legend(facecolor='black')

    # Format x-axis for real time
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    fig.autofmt_xdate()

    info_box = ax.text(0.02, 0.92, "", transform=ax.transAxes, color='lime',
                       fontsize=10, bbox=dict(facecolor='black', alpha=0.6))
    price_box = ax.text(0.70, 0.92, "", transform=ax.transAxes, color='yellow',
                        fontsize=10, bbox=dict(facecolor='black', alpha=0.6))
    line, = ax.plot([], [], color='lime', linewidth=2)

    initial_price = None
    plt.ion()
    plt.show()

    # --- Keep last 2 minutes (120s) of data ---
    window_duration = timedelta(seconds=30)

    while plt.fignum_exists(fig.number):
        if latest_price:
            if initial_price is None:
                initial_price = latest_price

            timestamps.append(datetime.now())
            prices.append(latest_price)

            # Keep 2 minutes of data
            now = datetime.now()
            cutoff = now - window_duration
            while timestamps and timestamps[0] < cutoff:
                timestamps.pop(0)
                prices.pop(0)

            line.set_data(timestamps, prices)

            # X range = last 2 minutes
            ax.set_xlim(now - window_duration, now)
            ax.set_ylim(min(min(prices), LOWER_THRESHOLD)*0.995,
                        max(max(prices), UPPER_THRESHOLD)*1.005)

            total_value = inr_balance + btc_balance * latest_price
            start_value = START_INR + START_BTC * initial_price

            info_box.set_text(
                f"INR ₹{inr_balance:,.0f}\nBTC {btc_balance}\n"
                f"Total ₹{total_value:,.0f}\nStart ₹{start_value:,.0f}"
            )
            price_box.set_text(f"BTC ₹{latest_price/1e5:.2f}L\nUSD→INR ₹{usd_inr:.2f}")

            plt.pause(0.05)
        else:
            plt.pause(0.2)


# ==== ENTRY ====
if __name__ == "__main__":
    print("💱 Starting Real-Time BTC/INR Auto-Trader (2-Minute Window)...")
    threading.Thread(target=get_usd_inr, daemon=True).start()
    threading.Thread(target=start_websocket, daemon=True).start()
    threading.Thread(target=trading_logic, daemon=True).start()
    main_plot()
