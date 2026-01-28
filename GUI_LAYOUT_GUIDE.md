# GUI Layout Guide

## Window Structure

```
┌─────────────────────────────────────────────────────────┐
│                    MEXC Trading Bot - Control Panel      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  [Settings Tab]  [Results Tab]                         │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │                                                   │  │
│  │         Tab Content Area                         │  │
│  │         (Settings or Results)                    │  │
│  │                                                   │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
├─────────────────────────────────────────────────────────┤
│  Trading: [Start Trading] [Stop Trading] | Backtest:  │
│  [Start Backtest] [Stop Backtest]                     │
└─────────────────────────────────────────────────────────┘
         ↑
    FOOTER BUTTONS (Always Visible at Bottom)
```

## Button Locations

### Footer (Bottom of Window - Always Visible)

The footer is at the **very bottom** of the window, below all tabs:

1. **Trading Section** (Left side):
   - Label: "Trading:"
   - **"Start Trading"** button
   - **"Stop Trading"** button (disabled when not trading)

2. **Separator** (Vertical line)

3. **Backtest Section** (Right side):
   - Label: "Backtest:"
   - **"Start Backtest"** button
   - **"Stop Backtest"** button (disabled when not backtesting)

## If You Don't See the Buttons

1. **Check Window Size**: The window might be too small. Try resizing it.
2. **Scroll Down**: If the content is too tall, scroll to the bottom.
3. **Check if Window is Maximized**: Try maximizing the window.

## Quick Test

1. Run: `python gui_app.py`
2. Look at the **very bottom** of the window
3. You should see:
   ```
   Trading: [Start Trading] [Stop Trading] | Backtest: [Start Backtest] [Stop Backtest]
   ```

## Button States

- **Start Trading**: Enabled when trading is stopped
- **Stop Trading**: Enabled when trading is active
- **Start Backtest**: Enabled when backtest is stopped
- **Stop Backtest**: Enabled when backtest is running
