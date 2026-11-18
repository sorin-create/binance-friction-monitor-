import time
from collections import deque
import requests

class BinanceLiveFrictionMonitor:
    def __init__(self, symbol: str = "BTCUSDT", threshold_a: float = 0.29213, window_size: int = 10):
        """
        Initializes the real-time friction monitor using public Binance data.
        :param symbol: Market symbol (e.g., 'BTCUSDT', 'ETHUSDT').
        :param threshold_a: Critical parity threshold a(t) = 0.29213.
        :param window_size: Number of snapshots for the rolling liquidity baseline.
        """
        self.symbol = symbol.upper()
        self.threshold_a = threshold_a
        self.volume_history = deque(maxlen=window_size)
        self.prev_total_vol = None
        self.url = f"https://api.binance.com/api/v3/depth?symbol={self.symbol}&limit=50"

    def fetch_order_book(self) -> dict:
        """
        Retrieves live order book snapshot from Binance public API with HTTP error handling.
        """
        try:
            response = requests.get(self.url, timeout=5)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"\n[API Warning]: HTTP {response.status_code} - {response.reason}")
        except requests.exceptions.RequestException as e:
            print(f"\n[Connection Error]: {e}")
        return None

    def run_monitor(self, intervals: int = 30, delay: float = 3.0):
        """
        Runs the live monitoring loop to evaluate market state using dynamic metrics.
        """
        print(f"Starting substrate monitoring for {self.symbol} (Critical threshold a(t) = {self.threshold_a})...\n")
        print(f"{'Time':<10} | {'Bid Vol':<12} | {'Ask Vol':<12} | {'Asym (C_s)':<11} | {'Shock (R)':<10} | {'a(t)':<8} | {'Market Status'}")
        print("-" * 105)

        for _ in range(intervals):
            data = self.fetch_order_book()
            if data:
                bids = data.get('bids', [])
                asks = data.get('asks', [])

                bid_vol = sum(float(item[1]) for item in bids)
                ask_vol = sum(float(item[1]) for item in asks)
                total_vol = bid_vol + ask_vol

                if total_vol > 0:
                    self.volume_history.append(total_vol)
                    rolling_baseline = sum(self.volume_history) / len(self.volume_history)

                    # 1. Dynamic order depth exhaustion index (I_depth) against rolling average
                    i_depth = max(0.0, 1.0 - (total_vol / rolling_baseline)) if rolling_baseline > 0 else 0.0

                    # 2. Directional asymmetry coefficient (C_sync)
                    c_sync = abs(bid_vol - ask_vol) / total_vol

                    # 3. High-frequency shock rate (R_hft): relative volume velocity between ticks
                    if self.prev_total_vol is not None and self.prev_total_vol > 0:
                        r_hft = min(1.0, abs(total_vol - self.prev_total_vol) / self.prev_total_vol)
                    else:
                        r_hft = 0.0

                    self.prev_total_vol = total_vol

                    # Unified saturation coefficient a(t)
                    w1, w2, w3 = 0.4, 0.3, 0.3
                    a_t = (w1 * i_depth) + (w2 * r_hft) + (w3 * c_sync)

                    # State evaluation based on the critical parity threshold
                    if a_t >= self.threshold_a:
                        status = "🔴 PANIC JAMMING (Saturation / High Friction)"
                    else:
                        status = "🟢 NULL DRIFT (Fluid / Normal Market)"

                    current_time = time.strftime("%H:%M:%S")
                    print(f"{current_time:<10} | {bid_vol:<12.2f} | {ask_vol:<12.2f} | {c_sync:<11.4f} | {r_hft:<10.4f} | {a_t:<8.4f} | {status}")

            time.sleep(delay)

if __name__ == "__main__":
    # Monitor BTC/USDT live, checking every 3 seconds with a 10-tick rolling baseline
    monitor = BinanceLiveFrictionMonitor(symbol="BTCUSDT", threshold_a=0.29213, window_size=10)
    monitor.run_monitor(intervals=25, delay=3.0)

