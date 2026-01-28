# How to Start Operating in Practice

## 1. Prerequisites

- **Python 3.10+** and a virtualenv
- **MEXC account** with API key + secret (spot trading enabled)
- **USDT** in your MEXC spot wallet (the bot buys XRP/ETH with USDT)

## 2. Install

```bash
cd mexc_spot_bot
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS

pip install -U pip
pip install -r requirements.txt
```

## 3. Configure

### 3.1 Environment variables

Create `.env` in the project root (or use `cp .env.example .env` if available):

```env
MEXC_API_KEY=your_api_key_here
MEXC_API_SECRET=your_api_secret_here
```

Optional:

- `MEXC_BASE_URL` – default `https://api.mexc.com`
- `MEXC_RECV_WINDOW` – default `5000`

### 3.2 Config file

Use the existing `configs/xrp_eth_h1.yaml`. It defines:

- **Symbols**: `XRPUSDT`, `ETHUSDT`
- **Safety**: `max_usdt_per_order` (e.g. 50), `cooldown_seconds`, etc.
- **Runtime**: `poll_seconds` (e.g. 30), `log_level`

Adjust `safety.allow_symbols`, `safety.max_usdt_per_order`, and `safety.dry_run_default` if you want.

## 4. Run in practice

### Option A – Backtest-style logic (recommended)

Uses the **same strategies as backtest** (EthMq4 H1, XrpMq4 H4), BUY + SELL, cost-basis tracking, and min-profit checks.

**Step 1: Dry-run (no real orders)**

```bash
python -m mexc_bot run-backtest-mode --config configs/xrp_eth_h1.yaml --dry-run
```

Watch logs for `[DRY] MARKET BUY` / `[DRY] MARKET SELL`. Leave it running for a while to confirm behavior.

**Step 2: Live (real orders)**

```bash
python -m mexc_bot run-backtest-mode --config configs/xrp_eth_h1.yaml
```

Cost basis is stored in `cost_basis.json` (default). Use `--cost-basis-file path/to/file.json` to change it.

### Option B – Original mode (H1 trend pullback, BUY-only + profit sweep)

```bash
# Dry-run
python -m mexc_bot run --config configs/xrp_eth_h1.yaml --dry-run

# Live
python -m mexc_bot run --config configs/xrp_eth_h1.yaml
```

## 5. Run continuously (e.g. on a VPS)

Spot bots are usually run 24/7. Options:

- **Screen** (Linux):
  ```bash
  screen -S mexc_bot
  python -m mexc_bot run-backtest-mode -c configs/xrp_eth_h1.yaml
  # Ctrl+A, D to detach
  ```
- **systemd** (Linux): create a unit that runs the same command.
- **Windows**: run in a persistent terminal or as a scheduled task.

## 6. Quick reference

| Command | Purpose |
|--------|--------|
| `python -m mexc_bot run-backtest-mode -c configs/xrp_eth_h1.yaml --dry-run` | Dry-run with backtest logic |
| `python -m mexc_bot run-backtest-mode -c configs/xrp_eth_h1.yaml` | Live with backtest logic |
| `python -m mexc_bot run -c configs/xrp_eth_h1.yaml --dry-run` | Dry-run original mode |
| `python -m mexc_bot run -c configs/xrp_eth_h1.yaml` | Live original mode |
| `python -m mexc_bot.backtest.run_backtest` | Backtest only (no live trading) |

## 7. Safety checklist

- [ ] Test with `--dry-run` first.
- [ ] Start with small `max_usdt_per_order` (e.g. 10–50 USDT).
- [ ] Prefer `safety.dry_run_default: true` in config until you’re confident.
- [ ] Use a dedicated API key with **spot only**, no withdrawals.
- [ ] Keep the process running (e.g. screen/systemd) if you want it to trade continuously.
