import time
import requests

class BinanceLiveFrictionMonitor:
    def __init__(self, symbol: str = "BTCUSDT", threshold_a: float = 0.29213):
        """
        Initializes the real-time friction monitor using public Binance data.
        :param symbol: Market symbol (e.g., 'BTCUSDT', 'ETHUSDT').
        :param threshold_a: Critical parity threshold a(t) = 0.29213.
        """
        self.symbol = symbol.upper()
        self.threshold_a = threshold_a
        self.baseline_depth = None
        self.url = f"https://api.binance.com/api/v3/depth?symbol={self.symbol}&limit=50"

    def fetch_order_book(self) -> dict:
        """
        Retrieves live order book snapshot from Binance public API.
        """
        try:
            response = requests.get(self.url, timeout=5)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"\n[API Connection Error]: {e}")
        return None

    def run_monitor(self, intervals: int = 30, delay: float = 3.0):
        """
        Runs the live monitoring loop to evaluate market state.
        """
        print(f"Starting substrate monitoring for {self.symbol} (Critical threshold a(t) = {self.threshold_a})...\n")
        print(f"{'Time':<10} | {'Total Bid Vol':<16} | {'Total Ask Vol':<16} | {'Imbalance (C_s)':<15} | {'a(t)':<8} | {'Market Status'}")
        print("-" * 95)

        for _ in range(intervals):
            data = self.fetch_order_book()
            if data:
                bids = data.get('bids', [])
                asks = data.get('asks', [])

                # Calculate aggregate volume from order book depth
                bid_vol = sum([float(item[1]) for item in bids])
                ask_vol = sum([float(item[1]) for item in asks])
                total_vol = bid_vol + ask_vol

                # Set baseline on the first successful query
                if self.baseline_depth is None and total_vol > 0:
                    self.baseline_depth = total_vol

                if self.baseline_depth and self.baseline_depth > 0:
                    # 1. Order depth exhaustion index (I_depth)
                    i_depth = max(0.0, 1.0 - (total_vol / self.baseline_depth))

                    # 2. Synchronization / directional asymmetry coefficient (C_sync)
                    c_sync = abs(bid_vol - ask_vol) / total_vol if total_vol > 0 else 0.0

                    # 3. Simulated pressure rate based on instantaneous variation
                    r_hft = min(1.0, abs(bid_vol - ask_vol) / (total_vol * 0.4)) if total_vol > 0 else 0.0

                    # Weights for calculating the unified coefficient a(t)
                    w1, w2, w3 = 0.4, 0.3, 0.3
                    a_t = (w1 * i_depth) + (w2 * r_hft) + (w3 * c_sync)

                    # State evaluation based on the critical threshold
                    if a_t >= self.threshold_a:
                        status = "🔴 PANIC JAMMING (Saturation / High Asymmetry)"
                    else:
                        status = "🟢 NULL DRIFT (Fluid / Normal Market)"

                    current_time = time.strftime("%H:%M:%S")
                    print(f"{current_time:<10} | {bid_vol:<16.2f} | {ask_vol:<16.2f} | {c_sync:<15.4f} | {a_t:<8.4f} | {status}")

            time.sleep(delay)

if __name__ == "__main__":
    # Monitor BTC/USDT live, checking every 3 seconds
    monitor = BinanceLiveFrictionMonitor(symbol="BTCUSDT", threshold_a=0.29213)
    monitor.run_monitor(intervals=25, delay=3.0)
