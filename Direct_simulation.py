import asyncio
import csv
import random
from collections import deque
from datetime import datetime


class FrictionTradingSimulation:
    def __init__(
        self,
        symbol: str = "btcusdt",
        threshold_a: float = 0.25,  # Slightly lowered to capture more signals in a short simulation
        cooldown_seconds: int = 10,
        initial_balance: float = 1000.0,
        tp_pct: float = 0.0025,     # Take Profit: 0.25%
        sl_pct: float = 0.0015,     # Stop Loss: 0.15%
        fee_pct: float = 0.001      # Binance Spot Fee: 0.1%
    ):
        self.symbol = symbol.lower()
        self.threshold_a = threshold_a

        # Rolling window for liquidity (last 500 snapshots)
        self.depth_window = deque(maxlen=500)

        # Logging and CSV Buffer
        self.history_log = f"friction_history_{self.symbol}.csv"
        self.trades_log = f"paper_trades_{self.symbol}.csv"
        self.csv_buffer = []
        self.buffer_limit = 20

        # Anti-spam cooldown
        self.cooldown_seconds = cooldown_seconds
        self.last_alert_time = None

        # Virtual Portfolio (Paper Trading)
        self.balance = initial_balance
        self.position = None
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

    def manage_paper_position(self, current_price: float, timestamp_str: str):
        """Checks if the active position has reached Take Profit or Stop Loss."""
        if not self.position:
            return

        side = self.position['side']
        entry = self.position['entry']
        size = self.position['size']

        price_change = (current_price - entry) / entry if side == "LONG" else (entry - current_price) / entry

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

    def process_order_book(self, data: dict):
        bids = data.get('bids', [])
        asks = data.get('asks', [])
        if not bids or not asks:
            return

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
        if len(self.depth_window) < 30:  # Reduced threshold for a fast simulation warm-up
            return

        rolling_baseline = sum(self.depth_window) / len(self.depth_window)

        # 3. Compute friction index a(t) and directional asymmetry
        i_depth = max(0.0, 1.0 - (total_vol / rolling_baseline))
        signed_asym = (bid_vol - ask_vol) / total_vol
        c_sync = abs(signed_asym)
        r_hft = min(1.0, abs(bid_vol - ask_vol) / (total_vol * 0.4))

        w1, w2, w3 = 0.4, 0.3, 0.3
        a_t = (w1 * i_depth) + (w2 * r_hft) + (w3 * c_sync)

        signal = "NEUTRAL"

        # 4. Generate signal and virtual execution
        if a_t >= self.threshold_a:
            if signed_asym > 0.15:
                signal = "LONG"
            elif signed_asym < -0.15:
                signal = "SHORT"

            if signal in ("LONG", "SHORT"):
                if self.position is None:
                    self.position = {
                        'side': signal,
                        'entry': mid_price,
                        'size': self.balance
                    }
                    print(f"\033[93m[OPEN {signal}] Price: {mid_price:.2f} | a(t): {a_t:.4f} | Asym: {signed_asym:+.2f}\033[0m")

                if self.last_alert_time is None or (now_dt - self.last_alert_time).total_seconds() >= self.cooldown_seconds:
                    self.last_alert_time = now_dt
                    print(f"⚡ [TELEGRAM MOCK ALERT] Signal: {signal} at Price: {mid_price:.2f} | Index a(t): {a_t:.4f}")

        # 5. Append to CSV buffer
        self.csv_buffer.append([
            current_time_str, self.symbol.upper(), f"{mid_price:.2f}",
            f"{bid_vol:.2f}", f"{ask_vol:.2f}", f"{signed_asym:.4f}", f"{a_t:.4f}", signal
        ])
        if len(self.csv_buffer) >= self.buffer_limit:
            self.flush_csv_buffer()

    async def run_simulation(self, total_steps: int = 600):
        print(f"Starting Friction Trading Simulation on {self.symbol.upper()} | Initial Balance: {self.balance} USDT\n")

        base_price = 65000.0
        spread = 0.5

        for step in range(total_steps):
            # Generate Brownian motion / Random Walk with occasional volume shocks
            price_change = random.gauss(0, 3.5)
            base_price += price_change

            # Simulate temporary order book imbalances (buying or selling pressure)
            pressure_bias = random.choice([0.8, 1.0, 1.2, 1.5 if random.random() > 0.8 else 1.0])

            mock_bids = [
                [str(round(base_price - spread - i * 0.5, 2)), str(round(random.uniform(0.8, 6.0) * pressure_bias, 4))]
                for i in range(20)
            ]
            mock_asks = [
                [str(round(base_price + spread + i * 0.5, 2)), str(round(random.uniform(0.8, 6.0) * (2.0 - pressure_bias), 4))]
                for i in range(20)
            ]

            mock_data = {
                "bids": mock_bids,
                "asks": mock_asks
            }

            self.process_order_book(mock_data)

            # Run simulated steps every 0.05s to fast-forward the test
            await asyncio.sleep(0.05)

        self.flush_csv_buffer()
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        print(f"\n[Simulation Completed] Total Trades: {self.total_trades} | Win Rate: {win_rate:.1f}% | Final Balance: {self.balance:.2f} USDT")


if __name__ == "__main__":
    sim = FrictionTradingSimulation(
        symbol="btcusdt",
        threshold_a=0.24,
        cooldown_seconds=5,
        initial_balance=1000.0
    )
    asyncio.run(sim.run_simulation(total_steps=500))
