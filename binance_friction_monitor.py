import asyncio
import json
import websockets
import csv
import requests
from datetime import datetime

class TelegramFrictionMonitor:
    def __init__(self, symbol: str = "btcusdt", threshold_a: float = 0.29213, cooldown_seconds: int = 60):
        self.symbol = symbol.lower()
        self.threshold_a = threshold_a
        self.baseline_depth = None
        self.ws_url = f"wss://stream.binance.com:9443/ws/{self.symbol}@depth20@100ms"
        
        # Log files
        self.history_log = f"friction_history_{self.symbol}.csv"
        self.alert_log = f"panic_alerts_{self.symbol}.log"
        
        # Cooldown anti-spam configuration
        self.cooldown_seconds = cooldown_seconds
        self.last_alert_time = None
        
        # Telegram configuration
        self.TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
        self.CHAT_ID = "YOUR_CHAT_ID"
        self.use_telegram = False  # Set to True after configuring your token and chat ID
        
        self.init_history_csv()

    def init_history_csv(self):
        """Initializes the CSV history log file with headers."""
        with open(self.history_log, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Symbol", "BidVol", "AskVol", "Asymmetry", "A_t", "Status"])

    def log_to_csv(self, timestamp, bid_vol, ask_vol, c_sync, a_t, status):
        """Appends a new record to the CSV history file."""
        with open(self.history_log, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, self.symbol.upper(), f"{bid_vol:.2f}", f"{ask_vol:.2f}", f"{c_sync:.4f}", f"{a_t:.4f}", status])

    def send_telegram_message(self, message: str):
        """Sends an alert message via Telegram API."""
        if not self.use_telegram:
            return
        try:
            url = f"https://api.telegram.org/bot{self.TELEGRAM_TOKEN}/sendMessage"
            payload = {
                "chat_id": self.CHAT_ID,
                "text": message,
                "parse_mode": "Markdown"
            }
            requests.post(url, json=payload, timeout=3)
        except Exception as e:
            print(f"\n[Telegram Error]: {e}")

    def trigger_alert(self, current_dt: datetime, timestamp_str: str, a_t: float, c_sync: float):
        """Triggers the alert mechanism respecting the cooldown period."""
        if self.last_alert_time is not None:
            elapsed = (current_dt - self.last_alert_time).total_seconds()
            if elapsed < self.cooldown_seconds:
                return  # Suppressed by cooldown

        self.last_alert_time = current_dt

        alert_message = (
            f"🚨 *PANIC JAMMING DETECTED* 🚨\n\n"
            f"• Symbol: `{self.symbol.upper()}`\n"
            f"• Threshold a(t): `{a_t:.4f}` (Limit: {self.threshold_a})\n"
            f"• Asymmetry (C_s): `{c_sync:.4f}`\n"
            f"• Timestamp: `{timestamp_str}`"
        )

        # Write to local alert log file
        with open(self.alert_log, mode='a', encoding='utf-8') as f:
            f.write(f"[{timestamp_str}] ALERT: a(t) = {a_t:.4f}\n")

        # Send via Telegram
        self.send_telegram_message(alert_message)
        print(" -> [Telegram Alert Sent Successfully]")

    async def process_order_book(self, data: dict):
        """Processes incoming WebSocket order book snapshots."""
        bids = data.get('bids', [])
        asks = data.get('asks', [])

        bid_vol = sum([float(item[1]) for item in bids])
        ask_vol = sum([float(item[1]) for item in asks])
        total_vol = bid_vol + ask_vol

        if self.baseline_depth is None and total_vol > 0:
            self.baseline_depth = total_vol

        if self.baseline_depth and self.baseline_depth > 0:
            i_depth = max(0.0, 1.0 - (total_vol / self.baseline_depth))
            c_sync = abs(bid_vol - ask_vol) / total_vol if total_vol > 0 else 0.0
            r_hft = min(1.0, abs(bid_vol - ask_vol) / (total_vol * 0.4)) if total_vol > 0 else 0.0

            w1, w2, w3 = 0.4, 0.3, 0.3
            a_t = (w1 * i_depth) + (w2 * r_hft) + (w3 * c_sync)

            now_dt = datetime.now()
            current_time_str = now_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

            if a_t >= self.threshold_a:
                status = "PANIC JAMMING"
                self.trigger_alert(now_dt, current_time_str, a_t, c_sync)
                print(f"\033[91m{current_time_str} | Bid: {bid_vol:.2f} | Ask: {ask_vol:.2f} | a(t): {a_t:.4f} | 🔴 {status}\033[0m")
            else:
                status = "NULL DRIFT"
                print(f"{current_time_str} | Bid: {bid_vol:.2f} | Ask: {ask_vol:.2f} | a(t): {a_t:.4f} | 🟢 {status}")

            self.log_to_csv(current_time_str, bid_vol, ask_vol, c_sync, a_t, status)

    async def connect(self):
        """Establishes and maintains the persistent WebSocket connection."""
        print(f"Starting WebSocket monitor for {self.symbol.upper()} with Cooldown ({self.cooldown_seconds}s)...\n")
        while True:
            try:
                async with websockets.connect(self.ws_url) as websocket:
                    print("[Connected to Binance WebSocket Stream]\n")
                    async for message in websocket:
                        data = json.loads(message)
                        await self.process_order_book(data)
            except Exception as e:
                print(f"\n[Connection Error]: {e}. Reconnecting in 3 seconds...")
                await asyncio.sleep(3)

if __name__ == "__main__":
    # Initialize monitor with a 60-second cooldown between alerts
    monitor = TelegramFrictionMonitor(symbol="btcusdt", threshold_a=0.29213, cooldown_seconds=60)
    
    # monitor.use_telegram = True  # Uncomment and configure token/chat_id to enable Telegram
    
    try:
        asyncio.run(monitor.connect())
    except KeyboardInterrupt:
        print("\n[Monitor Stopped Safely]")


