import asyncio
import json
import websockets
import aiohttp
import csv
from collections import deque
from datetime import datetime

class FrictionTradingBot:
    def __init__(
        self,
        symbol: str = "btcusdt",
        threshold_a: float = 0.29213,
        cooldown_seconds: int = 30,
        initial_balance: float = 1000.0,
        tp_pct: float = 0.0025,   # Take Profit: 0.25%
        sl_pct: float = 0.0015,   # Stop Loss: 0.15%
        fee_pct: float = 0.001    # Binance Spot Fee: 0.1%
    ):
        self.symbol = symbol.lower()
        self.threshold_a = threshold_a
        self.ws_url = f"wss://stream.binance.com:9443/ws/{self.symbol}@depth20@100ms"

        # Rolling window for liquidity (last 500 snapshots = ~50 seconds)
        self.depth_window = deque(maxlen=500)

        # Logging and CSV Buffer (to avoid disk I/O lag every 100ms)
        self.history_log = f"friction_history_{self.symbol}.csv"
        self.trades_log = f"paper_trades_{self.symbol}.csv"
        self.csv_buffer = []
        self.buffer_limit = 50

        # Anti-spam
        self.cooldown_seconds = cooldown_seconds
        self.last_alert_time = None

        # Telegram
        self.TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
        self.CHAT_ID = "YOUR_CHAT_ID"
        self.use_telegram = False

        # Virtual Portfolio (Paper Trading)
        self.balance = initial_balance
        self.position = None  # Dict: {'side': 'LONG'/'SHORT', 'entry': float, 'size': float}
        self.tp_pct = tp_pct
        self.sl_pct = sl_pct
        self.fee_pct = fee_pct
        self.total_trades = 0
        self.winning_trades = 0

        self.init_logs()

    def init_logs(self):
        with open(self.history_log, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Symbol", "MidPrice", "BidVol", "AskVol", "SignedAsym", "A_t", "Signal"])

        with open(self.trades_log, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Side", "EntryPrice", "ExitPrice", "Reason", "PnL_USDT", "Balance"])

    def flush_csv_buffer(self):
        if not self.csv_buffer:
            return
        with open(self.history_log, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(self.csv_buffer)
        self.csv_buffer.clear()

    def log_trade(self, timestamp, side, entry, exit_price, reason, pnl):
        with open(self.trades_log, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, side, f"{entry:.2f}", f"{exit_price:.2f}", reason, f"{pnl:.4f}", f"{self.balance:.2f}"])

    async def send_telegram_message(self, session: aiohttp.ClientSession, message: str):
        if not self.use_telegram:
            return
        url = f"https://api.telegram.org/bot{self.TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": self.CHAT_ID, "text": message, "parse_mode": "Markdown"}
        try:
            async with session.post(url, json=payload, timeout=3) as resp:
                if resp.status != 200:
                    print(f"\n[Telegram Warning]: Status {resp.status}")
        except Exception as e:
            print(f"\n[Telegram Error]: {e}")

    def manage_paper_position(self, current_price: float, timestamp_str: str):
        """Checks if the active position has reached Take Profit or Stop Loss."""
        if not self.position:
            return

        side = self.position['side']
        entry = self.position['entry']
        size = self.position['size']

        if side == "LONG":
            price_change = (current_price - entry) / entry
        else:
            price_change = (entry - current_price) / entry

        reason = None
        if price_change >= self.tp_pct:
            reason = "TAKE_PROFIT"
        elif price_change <= -self.sl_pct:
            reason = "STOP_LOSS"

        if reason:
            gross_pnl = size * price_change
            fees = size * self.fee_pct * 2  # Entry + Exit fee
            net_pnl = gross_pnl - fees
            self.balance += net_pnl
            self.total_trades += 1
            if net_pnl > 0:
                self.winning_trades += 1

            self.log_trade(timestamp_str, side, entry, current_price, reason, net_pnl)
            color = "\033[92m" if net_pnl > 0 else "\033[91m"
            print(f"{color}[TRADE CLOSED] {side} | {reason} | Net PnL: {net_pnl:+.2f} USDT | Balance: {self.balance:.2f} USDT\033[0m")
            self.position = None

    async def process_order_book(self, data: dict, session: aiohttp.ClientSession):
        bids = data.get('bids', [])
        asks = data.get('asks', [])
        if not bids or not asks:
            return

        # Current mid price (best Bid and best Ask)
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        mid_price = (best_bid + best_ask) / 2.0

        now_dt = datetime.now()
        current_time_str = now_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        # 1. Check active positions
        self.manage_paper_position(mid_price, current_time_str)

        # 2. Compute volumes and update rolling window
        bid_vol = sum(float(item[1]) for item in bids)
        ask_vol = sum(float(item[1]) for item in asks)
        total_vol = bid_vol + ask_vol
        if total_vol <= 0:
            return

        self.depth_window.append(total_vol)
        # Wait for at least 50 samples (5 seconds) for a stable baseline
        if len(self.depth_window) < 50:
            return

        rolling_baseline = sum(self.depth_window) / len(self.depth_window)

        # 3. Compute friction index a(t) and directional asymmetry
        i_depth = max(0.0, 1.0 - (total_vol / rolling_baseline))
        signed_asym = (bid_vol - ask_vol) / total_vol  # Positive = buying pressure, Negative = selling pressure
        c_sync = abs(signed_asym)
        r_hft = min(1.0, abs(bid_vol - ask_vol) / (total_vol * 0.4))

        w1, w2, w3 = 0.4, 0.3, 0.3
        a_t = (w1 * i_depth) + (w2 * r_hft) + (w3 * c_sync)

        signal = "NEUTRAL"

        # 4. Generate signal and virtual execution
        if a_t >= self.threshold_a:
            # Minimum asymmetry threshold (e.g., 0.25) to avoid unclear signals
            if signed_asym > 0.25:
                signal = "LONG"
            elif signed_asym < -0.25:
                signal = "SHORT"

            if signal in ("LONG", "SHORT"):
                # Open virtual position if none is currently active
                if self.position is None:
                    self.position = {
                        'side': signal,
                        'entry': mid_price,
                        'size': self.balance  # Use full virtual balance (1x)
                    }
                    print(f"\033[93m[OPEN {signal}] Price: {mid_price:.2f} | a(t): {a_t:.4f} | Asym: {signed_asym:+.2f}\033[0m")

                # Telegram alert with cooldown
                if self.last_alert_time is None or (now_dt - self.last_alert_time).total_seconds() >= self.cooldown_seconds:
                    self.last_alert_time = now_dt
                    msg = (
                        f"⚡ *{signal} SIGNAL DETECTED* ⚡\n\n"
                        f"• Symbol: `{self.symbol.upper()}`\n"
                        f"• Price: `{mid_price:.2f}`\n"
                        f"• Index a(t): `{a_t:.4f}`\n"
                        f"• Asymmetry: `{signed_asym:+.4f}`\n"
                        f"• Time: `{current_time_str}`"
                    )
                    asyncio.create_task(self.send_telegram_message(session, msg))

        # 5. Append to CSV buffer
        self.csv_buffer.append([
            current_time_str, self.symbol.upper(), f"{mid_price:.2f}",
            f"{bid_vol:.2f}", f"{ask_vol:.2f}", f"{signed_asym:.4f}", f"{a_t:.4f}", signal
        ])
        if len(self.csv_buffer) >= self.buffer_limit:
            self.flush_csv_buffer()

    async def connect(self):
        print(f"Starting FrictionTradingBot on {self.symbol.upper()} | Virtual Balance: {self.balance} USDT\n")
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    async with websockets.connect(self.ws_url) as websocket:
                        print("[Connected to Binance WebSocket Stream - Collecting liquidity baseline (5s)...]\n")
                        async for message in websocket:
                            data = json.loads(message)
                            await self.process_order_book(data, session)
                except Exception as e:
                    print(f"\n[Connection Error]: {e}. Reconnecting in 3 seconds...")
                    self.flush_csv_buffer()
                    await asyncio.sleep(3)

if __name__ == "__main__":
    bot = FrictionTradingBot(
        symbol="btcusdt",
        threshold_a=0.29213,
        cooldown_seconds=30,
        initial_balance=1000.0,
        tp_pct=0.0025,  # 0.25% target profit
        sl_pct=0.0015,  # 0.15% maximum stop loss
        fee_pct=0.001   # 0.1% standard Binance Spot fee
    )

    try:
        asyncio.run(bot.connect())
    except KeyboardInterrupt:
        bot.flush_csv_buffer()
        win_rate = (bot.winning_trades / bot.total_trades * 100) if bot.total_trades > 0 else 0
        print(f"\n[Bot Stopped] Total Trades: {bot.total_trades} | Win Rate: {win_rate:.1f}% | Final Balance: {bot.balance:.2f} USDT")



