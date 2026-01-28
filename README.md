# MEXC Spot Bot (XRP/USDT + ETH/USDT) — Full Project (Python)

This project is a **starter** for a spot trading bot on **MEXC Spot V3** with:
- Signed REST client (HMAC SHA256)
- Strategy interfaces + example H1 strategy
- Dry-run mode
- Safety guards (symbol allowlist, max order size, cooldown)
- Profit sweep (convert realized USDT profit into base coin to **increase XRP/ETH holdings**)

## Quick Start

### Install
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -U pip
pip install -r requirements.txt
```

### Configure
```bash
cp .env.example .env
# fill API key/secret
```

### Run dry-run
```bash
python -m mexc_bot run --config configs/xrp_eth_h1.yaml --dry-run
```

### Run live
```bash
python -m mexc_bot run --config configs/xrp_eth_h1.yaml
```

### Backtest-style live (same logic as backtest: Eth/Xrp MQ4, BUY+SELL)
```bash
# Dry-run first
python -m mexc_bot run-backtest-mode --config configs/xrp_eth_h1.yaml --dry-run
# Live
python -m mexc_bot run-backtest-mode --config configs/xrp_eth_h1.yaml
```

See **[OPERATION.md](OPERATION.md)** for step-by-step “how to start operating in practice” (env, config, dry-run, live, VPS).

## Notes
- Spot exchanges typically require the bot to keep running (VPS recommended).
- Spot does not always support native bracket orders; this template focuses on clean execution and safety.
