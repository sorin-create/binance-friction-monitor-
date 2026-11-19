# ⚡ FrictionTradingBot


A lightweight, asynchronous Python paper-trading and order-book microstructure analysis bot that connects to the **Binance WebSocket API** (`@depth20@100ms`). 


It calculates a real-time **Market Friction Index $a(t)$** and directional order-book asymmetry to detect short-term liquidity imbalances, execute simulated trades, log tick-level data, and send instant alerts via Telegram.


---


## 🧠 How It Works


Every `100ms`, the bot ingests the top 20 levels of the Bid and Ask order book and evaluates market conditions using a rolling 500-snapshot baseline (~50 seconds):


1. **Liquidity Depth Drop ($I_{\text{depth}}$):** Measures how much current order-book volume has thinned out compared to the rolling average.

2. **Directional Asymmetry ($C_{\text{sync}}$):** Calculates the normalized imbalance between Bid volume and Ask volume:

   $$\text{Asymmetry} = \frac{V_{\text{bid}} - V_{\text{ask}}}{V_{\text{bid}} + V_{\text{ask}}}$$

3. **High-Frequency Pressure ($R_{\text{HFT}}$):** Captures sudden spikes in order-book skew relative to total visible liquidity.


These three components are combined into the **Friction Index $a(t)$**:

$$a(t) = 0.4 \cdot I_{\text{depth}} + 0.3 \cdot R_{\text{HFT}} + 0.3 \cdot C_{\text{sync}}$$


When $a(t)$ crosses the defined threshold (`0.29213` by default) and directional asymmetry exceeds $\pm 0.25$, the bot generates a **LONG** or **SHORT** signal, opens a simulated position with configurable Take Profit / Stop Loss, and logs the event.


---


## ✨ Features


- **Fully Asynchronous:** Built with `asyncio`, `websockets`, and `aiohttp` for non-blocking network I/O.

- **Zero-Lag Disk Logging:** Uses an in-memory CSV buffer to batch-write market snapshots without blocking the 100ms WebSocket loop.

- **Built-in Paper Trading Engine:** Tracks virtual balance, win rate, entry/exit fees, Take Profit (`TP`), and Stop Loss (`SL`).

- **Telegram Alerts:** Sends formatted signal notifications with an anti-spam cooldown mechanism.

- **Auto-Reconnect:** Automatically recovers from WebSocket disconnects without losing buffered data.


---


## 🚀 Quick Start

### 1. Clone the repository
```bash
git clone https://github.com
cd binance-friction-monitor-
```

### 2. Install dependencies
```bash
pip install websockets aiohttp
```

### 3. Run the live monitor (or offline simulation)
To connect to the live Binance WebSocket stream:
```bash
python binance_friction_monitor.py
```

To run a fast offline simulation using synthetic Random Walk order-book data (no internet or API required):
```bash
python Direct_simulation.py
```

*(Optional)* To enable Telegram alerts in the live bot, set `self.use_telegram = True` and add your `TELEGRAM_TOKEN` and `CHAT_ID` in `binance_friction_monitor.py`.


---


## 📊 Output Files


The bot generates two CSV files automatically:

- `friction_history_<symbol>.csv`: High-frequency log of mid-prices, bid/ask volumes, asymmetry, and $a(t)$ values.

- `paper_trades_<symbol>.csv`: Detailed ledger of simulated trades, exit reasons (`TAKE_PROFIT` / `STOP_LOSS`), net PnL, and running balance.


---


## ⚠️ Disclaimer


This project is for **educational and research purposes only**. It simulates trades using mid-price execution and does not account for real-world slippage, queue position, or latency. Do not use this code with real funds without extensive backtesting and risk management.


