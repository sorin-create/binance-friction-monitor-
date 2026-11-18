# binance-friction-monitor-
Real-time Binance order book friction and market saturation monitor. 
A lightweight Python script that connects to the public Binance API to monitor real-time order book friction, liquidity contraction, and directional asymmetry. 

Instead of traditional lagging indicators, this script calculates a unified dynamic friction coefficient `a(t)` based on order depth exhaustion, high-frequency pressure rates, and order imbalance, benchmarking market stress against a critical threshold (`0.29213`).

## Features
- Fetches live order book depth data (`bids` and `asks`) via public REST endpoints without requiring API keys.
- Computes real-time stress metrics (`I_depth`, `C_sync`, `r_hft`).
- Dynamically classifies market states into **Null Drift** (fluid regime) vs. **Panic Jamming** (systemic saturation).

## Requirements
- Python 3.x
- `requests`
- `numpy`

## Usage
Run the script directly from your terminal:
```bash
python binance_friction_monitor.py
