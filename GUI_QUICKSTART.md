# GUI Quick Start Guide

## Installation

1. Install matplotlib (if not already installed):
```bash
pip install matplotlib
```

Or install all requirements:
```bash
pip install -r requirements.txt
```

## Running the GUI

```bash
python gui_app.py
```

## Quick Setup

### 1. Configure API Credentials
- Open the **Settings** tab
- Enter your MEXC API Key and click **Save**
- Enter your MEXC API Secret and click **Save**
- Credentials are saved to `.env` file

### 2. Run a Backtest
- In **Settings** tab:
  - Select backtest period (1, 3, 6, or 12 years)
  - Check ETHUSDT and/or XRPUSDT
  - Adjust strategy parameters if needed
- Switch to **Results** tab
- Select **Backtest** graph mode (radio buttons below graph)
- Click **Start Backtest** in footer
- Watch progress in graph and logs

### 3. Start Live Trading
- Ensure API credentials are saved
- Click **Start Trading** in footer
- Switch to **Results** tab
- Select **Operating** graph mode
- Monitor real-time portfolio value
- Click **Stop Trading** when done

## Features

✅ **Settings Tab**:
- API Key/Secret management
- Backtest period selection
- Symbol selection (checkboxes)
- Strategy parameter adjustment

✅ **Results Tab**:
- Real-time graph (upper half)
- Logs display (lower half)
- Graph mode switcher (Operating/Backtest)

✅ **Footer Controls**:
- Start/Stop Trading
- Start/Stop Backtest

## Notes

- Trading and backtesting run in background threads
- GUI remains responsive during operations
- All operations are logged with timestamps
- Graphs update automatically
