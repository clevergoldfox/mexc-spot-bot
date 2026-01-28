#!/usr/bin/env python3
"""
MEXC Trading Bot GUI Application
Provides a user interface for settings, backtesting, and monitoring
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import queue
import os
from datetime import datetime, timedelta
from decimal import Decimal
from dotenv import load_dotenv, set_key, find_dotenv
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from collections import deque

from mexc_bot.mexc.client import MexcSpotClient
from mexc_bot.backtest.data_provider import fetch_klines
from mexc_bot.backtest.simulator import SpotWallet
from mexc_bot.backtest.engine import BacktestEngine
from mexc_bot.strategies.mq4_eth_xrp import EthMq4Strategy, EthMq4Params, XrpMq4Strategy, XrpMq4Params
from mexc_bot.config import load_config
from mexc_bot.logging_setup import setup_logging
from mexc_bot.services.execution import ExecutionService, ExecutionConfig
from mexc_bot.services.portfolio import Portfolio
from mexc_bot.services.profit_sweep import ProfitSweeper, ProfitSweepConfig


class TradingBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("MEXC Trading Bot - Control Panel")
        self.root.geometry("1200x800")
        self.root.minsize(800, 600)  # Minimum window size
        
        # State variables
        self.trading_active = False
        self.backtest_active = False
        self.trading_thread = None
        self.backtest_thread = None
        self.log_queue = queue.Queue()
        
        # Data for graphs
        self.operating_data = {
            'time': deque(maxlen=100),
            'portfolio_value': deque(maxlen=100),
            'eth_holdings': deque(maxlen=100),
            'xrp_holdings': deque(maxlen=100),
        }
        self.backtest_data = {
            'time': deque(maxlen=100),
            'portfolio_value': deque(maxlen=100),
            'profit_pct': deque(maxlen=100),
        }
        self.current_graph_mode = 'operating'  # 'operating' or 'backtest'
        
        # Load .env file
        self.env_path = find_dotenv() or '.env'
        if not os.path.exists(self.env_path):
            # Create .env file if it doesn't exist
            with open(self.env_path, 'w') as f:
                f.write("MEXC_API_KEY=\nMEXC_API_SECRET=\n")
        load_dotenv(self.env_path)
        
        self.setup_ui()
        self.check_log_queue()
        
    def setup_ui(self):
        """Setup the user interface"""
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Settings Tab
        self.settings_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.settings_frame, text="Settings")
        self.setup_settings_tab()
        
        # Results Tab
        self.results_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.results_frame, text="Results")
        self.setup_results_tab()
        
        # Footer buttons (always visible)
        self.setup_footer()
        
    def setup_settings_tab(self):
        """Setup the Settings tab"""
        # API Configuration Section
        api_frame = ttk.LabelFrame(self.settings_frame, text="API Configuration", padding=10)
        api_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(api_frame, text="MEXC API Key:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.api_key_var = tk.StringVar(value=os.getenv("MEXC_API_KEY", ""))
        ttk.Entry(api_frame, textvariable=self.api_key_var, width=50).grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(api_frame, text="Save", command=self.save_api_key).grid(row=0, column=2, padx=5)
        
        ttk.Label(api_frame, text="MEXC API Secret:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.api_secret_var = tk.StringVar(value=os.getenv("MEXC_API_SECRET", ""))
        ttk.Entry(api_frame, textvariable=self.api_secret_var, width=50, show="*").grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(api_frame, text="Save", command=self.save_api_secret).grid(row=1, column=2, padx=5)
        
        # Backtest Configuration Section
        backtest_frame = ttk.LabelFrame(self.settings_frame, text="Backtest Configuration", padding=10)
        backtest_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(backtest_frame, text="Backtest Period:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.period_var = tk.StringVar(value="1")
        period_combo = ttk.Combobox(backtest_frame, textvariable=self.period_var, 
                                     values=["1", "3", "6", "12"], width=10, state="readonly")
        period_combo.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        ttk.Label(backtest_frame, text="year(s)").grid(row=0, column=2, sticky=tk.W, padx=5)
        
        # Symbol Selection
        ttk.Label(backtest_frame, text="Select Symbols:").grid(row=1, column=0, sticky=tk.W, pady=5)
        symbol_frame = ttk.Frame(backtest_frame)
        symbol_frame.grid(row=1, column=1, columnspan=2, sticky=tk.W, padx=5)
        
        self.eth_checkbox_var = tk.BooleanVar(value=True)
        self.xrp_checkbox_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(symbol_frame, text="ETHUSDT", variable=self.eth_checkbox_var).pack(side=tk.LEFT, padx=10)
        ttk.Checkbutton(symbol_frame, text="XRPUSDT", variable=self.xrp_checkbox_var).pack(side=tk.LEFT, padx=10)
        
        # Strategy Parameters Section
        strategy_frame = ttk.LabelFrame(self.settings_frame, text="Strategy Parameters (ETH)", padding=10)
        strategy_frame.pack(fill=tk.X, padx=10, pady=5)
        
        params_grid = ttk.Frame(strategy_frame)
        params_grid.pack(fill=tk.X)
        
        # RSI Parameters
        ttk.Label(params_grid, text="RSI Buy Level:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.rsi_buy_var = tk.DoubleVar(value=40.0)
        ttk.Spinbox(params_grid, from_=30.0, to=50.0, textvariable=self.rsi_buy_var, width=10).grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(params_grid, text="RSI Sell Level:").grid(row=0, column=2, sticky=tk.W, padx=10, pady=2)
        self.rsi_sell_var = tk.DoubleVar(value=60.0)
        ttk.Spinbox(params_grid, from_=50.0, to=70.0, textvariable=self.rsi_sell_var, width=10).grid(row=0, column=3, padx=5, pady=2)
        
        ttk.Label(params_grid, text="Pullback ATR Mult:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.pullback_atr_var = tk.DoubleVar(value=0.65)
        ttk.Spinbox(params_grid, from_=0.5, to=1.0, increment=0.05, textvariable=self.pullback_atr_var, width=10).grid(row=1, column=1, padx=5, pady=2)
        
        ttk.Label(params_grid, text="Min Trend Strength:").grid(row=1, column=2, sticky=tk.W, padx=10, pady=2)
        self.trend_strength_var = tk.DoubleVar(value=0.001)
        ttk.Spinbox(params_grid, from_=0.0001, to=0.01, increment=0.0001, textvariable=self.trend_strength_var, width=10).grid(row=1, column=3, padx=5, pady=2)
        
    def setup_results_tab(self):
        """Setup the Results tab"""
        # Graph Section (Upper Half)
        graph_container = ttk.Frame(self.results_frame)
        graph_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Graph mode switcher
        mode_frame = ttk.Frame(graph_container)
        mode_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(mode_frame, text="Graph Mode:").pack(side=tk.LEFT, padx=5)
        self.graph_mode_var = tk.StringVar(value="operating")
        ttk.Radiobutton(mode_frame, text="Operating", variable=self.graph_mode_var, 
                       value="operating", command=self.switch_graph_mode).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(mode_frame, text="Backtest", variable=self.graph_mode_var, 
                       value="backtest", command=self.switch_graph_mode).pack(side=tk.LEFT, padx=5)
        
        # Matplotlib figure
        self.fig = Figure(figsize=(10, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, graph_container)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.update_graph()
        
        # Logs Section (Lower Half)
        logs_frame = ttk.LabelFrame(self.results_frame, text="Logs", padding=5)
        logs_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(logs_frame, height=15, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.config(state=tk.DISABLED)
        
    def setup_footer(self):
        """Setup footer buttons"""
        # Create a container frame for the footer to ensure it's always visible
        footer_container = ttk.Frame(self.root)
        footer_container.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)
        
        # Add a separator line above buttons for visibility
        ttk.Separator(footer_container, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 5))
        
        footer = ttk.Frame(footer_container)
        footer.pack(fill=tk.X)
        
        # Trading buttons
        trading_frame = ttk.Frame(footer)
        trading_frame.pack(side=tk.LEFT, padx=10)
        ttk.Label(trading_frame, text="Trading:", font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=5)
        self.start_trading_btn = ttk.Button(trading_frame, text="▶ Start Trading", command=self.start_trading, width=15)
        self.start_trading_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_trading_btn = ttk.Button(trading_frame, text="⏹ Stop Trading", command=self.stop_trading, state=tk.DISABLED, width=15)
        self.stop_trading_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Separator(footer, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=20)
        
        # Backtest buttons
        backtest_frame = ttk.Frame(footer)
        backtest_frame.pack(side=tk.LEFT, padx=10)
        ttk.Label(backtest_frame, text="Backtest:", font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=5)
        self.start_backtest_btn = ttk.Button(backtest_frame, text="▶ Start Backtest", command=self.start_backtest, width=15)
        self.start_backtest_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_backtest_btn = ttk.Button(backtest_frame, text="⏹ Stop Backtest", command=self.stop_backtest, state=tk.DISABLED, width=15)
        self.stop_backtest_btn.pack(side=tk.LEFT, padx=5)
        
    def save_api_key(self):
        """Save API key to .env file"""
        api_key = self.api_key_var.get().strip()
        if api_key:
            set_key(self.env_path, "MEXC_API_KEY", api_key)
            self.log_message("API Key saved successfully")
            messagebox.showinfo("Success", "API Key saved to .env file")
        else:
            messagebox.showerror("Error", "API Key cannot be empty")
    
    def save_api_secret(self):
        """Save API secret to .env file"""
        api_secret = self.api_secret_var.get().strip()
        if api_secret:
            set_key(self.env_path, "MEXC_API_SECRET", api_secret)
            self.log_message("API Secret saved successfully")
            messagebox.showinfo("Success", "API Secret saved to .env file")
        else:
            messagebox.showerror("Error", "API Secret cannot be empty")
    
    def switch_graph_mode(self):
        """Switch between operating and backtest graph modes"""
        self.current_graph_mode = self.graph_mode_var.get()
        self.update_graph()
    
    def update_graph(self):
        """Update the graph display"""
        self.ax.clear()
        
        if self.current_graph_mode == 'operating':
            if len(self.operating_data['time']) > 0:
                times = list(self.operating_data['time'])
                values = list(self.operating_data['portfolio_value'])
                
                # Convert datetime objects to numbers for plotting
                if times and isinstance(times[0], datetime):
                    time_nums = [(t - times[0]).total_seconds() / 60 for t in times]  # Minutes since start
                    self.ax.plot(time_nums, values, label='Portfolio Value', linewidth=2, color='blue')
                    self.ax.set_xlabel('Time (minutes)')
                else:
                    self.ax.plot(times, values, label='Portfolio Value', linewidth=2, color='blue')
                    self.ax.set_xlabel('Time')
                
                self.ax.set_title('Real-Time Trading Status', fontsize=12, fontweight='bold')
                self.ax.set_ylabel('Portfolio Value (USDT)')
                self.ax.legend()
                self.ax.grid(True, alpha=0.3)
        else:  # backtest mode
            if len(self.backtest_data['time']) > 0:
                times = list(self.backtest_data['time'])
                profit_pct = list(self.backtest_data['profit_pct'])
                
                self.ax.plot(times, profit_pct, label='Profit %', linewidth=2, color='green')
                self.ax.set_title('Backtest Results', fontsize=12, fontweight='bold')
                self.ax.set_xlabel('Candle Index')
                self.ax.set_ylabel('Profit %')
                self.ax.legend()
                self.ax.grid(True, alpha=0.3)
                self.ax.axhline(y=0, color='r', linestyle='--', alpha=0.5)
        
        self.fig.tight_layout()
        self.canvas.draw()
    
    def log_message(self, message):
        """Add message to log queue"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_queue.put(f"[{timestamp}] {message}")
    
    def check_log_queue(self):
        """Check for new log messages and display them"""
        try:
            while True:
                message = self.log_queue.get_nowait()
                self.log_text.config(state=tk.NORMAL)
                self.log_text.insert(tk.END, message + "\n")
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
        except queue.Empty:
            pass
        
        # Schedule next check
        self.root.after(100, self.check_log_queue)
    
    def start_trading(self):
        """Start live trading"""
        if self.trading_active:
            messagebox.showwarning("Warning", "Trading is already active")
            return
        
        # Validate API credentials
        api_key = os.getenv("MEXC_API_KEY")
        api_secret = os.getenv("MEXC_API_SECRET")
        
        if not api_key or not api_secret:
            messagebox.showerror("Error", "Please set API Key and Secret in Settings tab")
            return
        
        self.trading_active = True
        self.start_trading_btn.config(state=tk.DISABLED)
        self.stop_trading_btn.config(state=tk.NORMAL)
        
        self.log_message("Starting live trading...")
        self.trading_thread = threading.Thread(target=self.run_trading, daemon=True)
        self.trading_thread.start()
    
    def stop_trading(self):
        """Stop live trading"""
        if not self.trading_active:
            return
        
        self.trading_active = False
        self.start_trading_btn.config(state=tk.NORMAL)
        self.stop_trading_btn.config(state=tk.DISABLED)
        self.log_message("Stopping live trading...")
    
    def run_trading(self):
        """Run live trading in background thread"""
        try:
            # Load config
            config_path = "configs/eth_optimized.yaml"
            if not os.path.exists(config_path):
                config_path = "config.yaml"
            
            cfg = load_config(config_path)
            setup_logging(cfg.runtime.log_level)
            
            # Initialize client
            api_key = os.getenv("MEXC_API_KEY")
            api_secret = os.getenv("MEXC_API_SECRET")
            base_url = os.getenv("MEXC_BASE_URL") or "https://api.mexc.com"
            recv_window = int(os.getenv("MEXC_RECV_WINDOW") or "5000")
            
            client = MexcSpotClient(api_key, api_secret, base_url=base_url, recv_window=recv_window)
            
            # Initialize services
            execsvc = ExecutionService(client, ExecutionConfig(**cfg.execution.model_dump()), dry_run=False)
            
            # Initialize strategy based on config
            strategy_name = cfg.strategy.name.lower()
            quote_per_trade = Decimal(str(cfg.safety.max_usdt_per_order))
            
            if strategy_name == "eth_mq4_h1" or strategy_name == "mq4_eth":
                from mexc_bot.strategies.mq4_eth_xrp import EthMq4Strategy, EthMq4Params
                params = EthMq4Params(**cfg.strategy.params)
                strat = EthMq4Strategy(client, params, quote_per_trade=quote_per_trade)
            elif strategy_name == "xrp_mq4_h4" or strategy_name == "mq4_xrp":
                from mexc_bot.strategies.mq4_eth_xrp import XrpMq4Strategy, XrpMq4Params
                params = XrpMq4Params(**cfg.strategy.params)
                strat = XrpMq4Strategy(client, params, quote_per_trade=quote_per_trade)
            elif strategy_name == "h1_trend_pullback" or strategy_name == "trend_pullback":
                from mexc_bot.strategies.h1_trend_pullback import H1TrendPullbackStrategy, H1TrendPullbackParams
                params = H1TrendPullbackParams(**cfg.strategy.params)
                strat = H1TrendPullbackStrategy(client, params, quote_per_trade=quote_per_trade)
            else:
                raise ValueError(f"Unknown strategy: {strategy_name}")
            
            self.log_message("Trading bot initialized successfully")
            
            # Trading loop
            import time
            last_trade_ts = {s: 0.0 for s in cfg.safety.allow_symbols}
            
            while self.trading_active:
                try:
                    for symbol in cfg.safety.allow_symbols:
                        if not self.trading_active:
                            break
                        
                        if time.time() - last_trade_ts.get(symbol, 0.0) < cfg.safety.cooldown_seconds:
                            continue
                        
                        sig = strat.generate(symbol)
                        if sig:
                            self.log_message(f"Signal: {sig.side} {sig.symbol} | {sig.reason}")
                            
                            if sig.side == "BUY":
                                execsvc.market_buy_quote(symbol, Decimal(str(sig.size_quote)))
                                last_trade_ts[symbol] = time.time()
                                self.log_message(f"Executed BUY order for {symbol}")
                    
                    time.sleep(cfg.runtime.poll_seconds)
                    
                    # Update operating graph periodically (every 10 iterations)
                    if hasattr(self, '_trading_iteration_count'):
                        self._trading_iteration_count += 1
                    else:
                        self._trading_iteration_count = 0
                    
                    if self._trading_iteration_count % 10 == 0:
                        try:
                            from mexc_bot.cli import load_portfolio
                            portfolio = load_portfolio(client)
                            base_assets = cfg.portfolio.base_assets
                            portfolio_value = portfolio.asset_free("USDT")
                            
                            # Get current prices and calculate total value
                            for asset in base_assets:
                                symbol = f"{asset}USDT"
                                try:
                                    ticker = client.book_ticker(symbol)
                                    if isinstance(ticker, dict) and "bidPrice" in ticker:
                                        price = Decimal(str(ticker["bidPrice"]))
                                        qty = portfolio.asset_free(asset)
                                        portfolio_value += qty * price
                                except:
                                    pass
                            
                            current_time = datetime.now()
                            self.operating_data['time'].append(current_time)
                            self.operating_data['portfolio_value'].append(float(portfolio_value))
                            
                            if self.current_graph_mode == 'operating':
                                self.root.after(0, self.update_graph)
                        except:
                            pass  # Don't fail trading if graph update fails
                    
                except Exception as e:
                    self.log_message(f"Trading error: {str(e)}")
                    time.sleep(5)
            
            self.log_message("Trading stopped")
            
        except Exception as e:
            self.log_message(f"Failed to start trading: {str(e)}")
            self.trading_active = False
            self.root.after(0, lambda: self.start_trading_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.stop_trading_btn.config(state=tk.DISABLED))
    
    def start_backtest(self):
        """Start backtest"""
        if self.backtest_active:
            messagebox.showwarning("Warning", "Backtest is already running")
            return
        
        # Get selected symbols
        symbols = []
        if self.eth_checkbox_var.get():
            symbols.append("ETHUSDT")
        if self.xrp_checkbox_var.get():
            symbols.append("XRPUSDT")
        
        if not symbols:
            messagebox.showerror("Error", "Please select at least one symbol")
            return
        
        self.backtest_active = True
        self.start_backtest_btn.config(state=tk.DISABLED)
        self.stop_backtest_btn.config(state=tk.NORMAL)
        
        # Clear backtest data
        self.backtest_data = {
            'time': deque(maxlen=100),
            'portfolio_value': deque(maxlen=100),
            'profit_pct': deque(maxlen=100),
        }
        
        self.log_message(f"Starting backtest for {', '.join(symbols)}...")
        self.backtest_thread = threading.Thread(target=self.run_backtest, args=(symbols,), daemon=True)
        self.backtest_thread.start()
    
    def stop_backtest(self):
        """Stop backtest"""
        if not self.backtest_active:
            return
        
        self.backtest_active = False
        self.start_backtest_btn.config(state=tk.NORMAL)
        self.stop_backtest_btn.config(state=tk.DISABLED)
        self.log_message("Stopping backtest...")
    
    def run_backtest(self, symbols):
        """Run backtest in background thread"""
        try:
            client = MexcSpotClient("", "")
            period_years = int(self.period_var.get())
            
            for symbol in symbols:
                if not self.backtest_active:
                    break
                
                self.log_message(f"Backtesting {symbol}...")
                
                # Create wallet
                wallet = SpotWallet(initial_usdt=Decimal("1000"))
                initial_value = Decimal("1000")
                
                # Create strategy
                if symbol == "ETHUSDT":
                    strategy = EthMq4Strategy(
                        client=None,
                        params=EthMq4Params(
                            ema_fast=50,
                            ema_slow=200,
                            rsi_period=14,
                            rsi_buy_level=float(self.rsi_buy_var.get()),
                            rsi_sell_level=float(self.rsi_sell_var.get()),
                            atr_period=14,
                            pullback_atr_mult=float(self.pullback_atr_var.get()),
                            min_trend_strength=float(self.trend_strength_var.get()),
                            dynamic_atr_enabled=True,
                            atr_lookback=50,
                            rsi_upper_limit=52.0,
                            rsi_exit_overbought=68.0,
                            price_momentum_periods=3,
                            min_momentum_pct=0.0,
                        ),
                        quote_per_trade=Decimal("50"),
                    )
                    interval = "60m"
                else:  # XRPUSDT
                    strategy = XrpMq4Strategy(
                        client=None,
                        params=XrpMq4Params(),
                        quote_per_trade=Decimal("40"),
                    )
                    interval = "4h"
                
                # Fetch data
                needed_candles = (24 * 365 * period_years) if interval == "60m" else (6 * 365 * period_years)
                self.log_message(f"Fetching {needed_candles} candles for {symbol}...")
                klines = fetch_klines(client, symbol, interval, limit=5000, max_candles=needed_candles + 500)
                
                if len(klines) < 300:
                    self.log_message(f"Not enough data for {symbol}, skipping")
                    continue
                
                lookback_candles = needed_candles
                if len(klines) > lookback_candles:
                    klines = klines[-lookback_candles:]
                
                self.log_message(f"Running backtest on {len(klines)} candles...")
                
                # Custom backtest loop with progress tracking
                base = symbol.replace("USDT", "")
                for i in range(200, len(klines)):
                    if not self.backtest_active:
                        break
                    
                    window = klines[:i]
                    candle = klines[i]
                    ts = candle[0]
                    close_price = Decimal(candle[4])
                    
                    signal = strategy.generate_from_klines(symbol, window)
                    
                    if signal and signal.side == "BUY":
                        usdt_amount = signal.size_quote if signal.size_quote else Decimal("50") if symbol == "ETHUSDT" else Decimal("40")
                        wallet.buy(symbol, close_price, usdt_amount, ts)
                        self.log_message(f"[{i}] {symbol} BUY @ {close_price:.4f} | {signal.reason}")
                    
                    elif signal and signal.side == "SELL":
                        holdings_before = wallet.assets.get(base, Decimal("0"))
                        
                        if holdings_before > 0:
                            if symbol == "ETHUSDT":
                                min_holdings = Decimal("0.15")
                                min_profit = Decimal("0.15")
                                
                                if holdings_before >= min_holdings and wallet.is_profitable(symbol, close_price, min_profit):
                                    sell_pct = Decimal("0.15")
                                    wallet.sell_partial(symbol, close_price, sell_pct, ts)
                                    avg_cost = wallet.get_avg_cost(symbol)
                                    profit_pct = (close_price - avg_cost) / avg_cost * Decimal("100") if avg_cost > 0 else Decimal("0")
                                    self.log_message(f"[{i}] {symbol} SELL {float(sell_pct)*100:.0f}% @ {close_price:.4f} | Profit: {profit_pct:.1f}%")
                            else:
                                sell_pct = Decimal("0.5")
                                wallet.sell_partial(symbol, close_price, sell_pct, ts)
                                self.log_message(f"[{i}] {symbol} SELL {float(sell_pct)*100:.0f}% @ {close_price:.4f}")
                    
                    # Update graph every 50 candles
                    if i % 50 == 0:
                        base_qty = wallet.assets.get(base, Decimal("0"))
                        portfolio_value = wallet.usdt + base_qty * close_price
                        profit_pct = float((portfolio_value / initial_value - Decimal("1")) * Decimal("100"))
                        
                        self.backtest_data['time'].append(i)
                        self.backtest_data['portfolio_value'].append(float(portfolio_value))
                        self.backtest_data['profit_pct'].append(profit_pct)
                        
                        self.root.after(0, self.update_graph)
                
                # Final results
                last_close = Decimal(klines[-1][4])
                base = symbol.replace("USDT", "")
                base_qty = wallet.assets.get(base, Decimal("0"))
                portfolio_value = wallet.usdt + base_qty * last_close
                profit_pct = float((portfolio_value / initial_value - Decimal("1")) * Decimal("100"))
                
                self.log_message(f"{symbol} Backtest Complete:")
                self.log_message(f"  Final Value: ${float(portfolio_value):.2f}")
                self.log_message(f"  Profit: {profit_pct:.2f}%")
                self.log_message(f"  Trades: {len(wallet.trades)}")
            
            self.log_message("Backtest completed")
            self.backtest_active = False
            self.root.after(0, lambda: self.start_backtest_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.stop_backtest_btn.config(state=tk.DISABLED))
            
        except Exception as e:
            self.log_message(f"Backtest error: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())
            self.backtest_active = False
            self.root.after(0, lambda: self.start_backtest_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.stop_backtest_btn.config(state=tk.DISABLED))


def main():
    root = tk.Tk()
    app = TradingBotGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
