# MEXC Trading Bot GUI Application

## Overview

A user-friendly graphical interface for the MEXC Trading Bot, providing easy access to settings, backtesting, and real-time monitoring.

## Features

### Settings Tab
- **API Configuration**: Set and save MEXC API Key and Secret to `.env` file
- **Backtest Configuration**: 
  - Select backtest period (1, 3, 6, or 12 years)
  - Choose symbols to backtest (ETHUSDT, XRPUSDT, or both) using checkboxes
- **Strategy Parameters**: Adjust ETH strategy parameters:
  - RSI Buy Level
  - RSI Sell Level
  - Pullback ATR Multiplier
  - Minimum Trend Strength

### Results Tab
- **Real-Time Graph** (Upper Half):
  - Operating mode: Shows portfolio value over time during live trading
  - Backtest mode: Shows profit percentage over time during backtesting
  - Mode switcher at bottom of graph area
- **Logs Display** (Lower Half):
  - Real-time log messages
  - Timestamped entries
  - Auto-scrolling

### Footer Controls
- **Start Trading**: Begin live trading (requires API credentials)
- **Stop Trading**: Stop live trading
- **Start Backtest**: Run backtest with selected symbols and parameters
- **Stop Backtest**: Stop running backtest

## Installation

1. Install required dependencies:
```bash
pip install -r requirements.txt
```

2. Ensure `.env` file exists with your API credentials (or set them in the GUI)

## Usage

### Starting the GUI

```bash
python gui_app.py
```

### Setting Up API Credentials

1. Go to **Settings** tab
2. Enter your MEXC API Key
3. Click **Save** next to API Key
4. Enter your MEXC API Secret
5. Click **Save** next to API Secret

### Running a Backtest

1. Go to **Settings** tab
2. Select backtest period (1, 3, 6, or 12 years)
3. Check the symbols you want to backtest (ETHUSDT, XRPUSDT, or both)
4. Adjust strategy parameters if needed
5. Go to **Results** tab and switch to "Backtest" graph mode
6. Click **Start Backtest** in the footer
7. Monitor progress in the graph and logs

### Starting Live Trading

1. Ensure API credentials are set in Settings tab
2. Click **Start Trading** in the footer
3. Switch to **Results** tab and select "Operating" graph mode
4. Monitor real-time portfolio value and logs
5. Click **Stop Trading** when you want to stop

## Graph Modes

### Operating Mode
- Displays real-time portfolio value during live trading
- Updates every polling interval
- Shows USDT value of total portfolio (USDT + base assets)

### Backtest Mode
- Displays profit percentage during backtesting
- Updates every 50 candles
- Shows cumulative profit/loss over time

## Notes

- **Thread Safety**: Trading and backtesting run in separate threads to keep GUI responsive
- **Graph Updates**: Graphs update automatically when data is available
- **Logs**: All operations are logged with timestamps
- **Error Handling**: Errors are displayed in logs and don't crash the application

## Requirements

- Python 3.8+
- tkinter (usually included with Python)
- matplotlib (for graphs)
- All dependencies from `requirements.txt`

## Troubleshooting

### GUI doesn't start
- Ensure tkinter is installed: `sudo apt-get install python3-tk` (Linux) or it should be included with Python on Windows/Mac

### API credentials not saving
- Check that `.env` file exists and is writable
- Ensure you click "Save" button after entering credentials

### Backtest not starting
- Ensure at least one symbol is selected
- Check that you have internet connection (needs to fetch historical data)

### Trading not starting
- Verify API credentials are set and saved
- Check that API key/secret are valid
- Ensure config file exists (`configs/eth_optimized.yaml` or `config.yaml`)
