# -*- coding: utf-8 -*-
import os
import time
import queue
import threading
import logging
from pathlib import Path
from decimal import Decimal, InvalidOperation
import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext
import tkinter.font as tkfont

import yaml
from dotenv import dotenv_values, load_dotenv

from mexc_bot.mexc.client import MexcSpotClient
from mexc_bot.services.cost_basis import CostBasisTracker
from mexc_bot.backtest.run_backtest import run as run_backtest
from mexc_bot.cli import run as run_trading


ENV_PATH = Path(".env")
DEFAULT_CONFIG_PATH = Path("config.yaml")
DEFAULT_SYMBOLS = ["ETHUSDT", "XRPUSDT"]


def load_env():
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH)
        return dotenv_values(ENV_PATH)
    return {}


def save_env_value(key, value):
    lines = []
    found = False
    if ENV_PATH.exists():
        raw_lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
        for line in raw_lines:
            if line.strip().startswith(f"{key}="):
                lines.append(f"{key}={value}")
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_allow_symbols():
    if not DEFAULT_CONFIG_PATH.exists():
        return DEFAULT_SYMBOLS
    try:
        data = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return DEFAULT_SYMBOLS
    symbols = data.get("safety", {}).get("allow_symbols")
    if not symbols:
        symbols = data.get("trading", {}).get("symbols")
    if not symbols:
        return DEFAULT_SYMBOLS
    return symbols


def translate_log_line(line):
    replacements = {
        "Bot started": "\u904b\u7528\u3092\u958b\u59cb\u3057\u307e\u3057\u305f",
        "Stopping": "\u505c\u6b62\u4e2d",
        "Signal": "\u30b7\u30b0\u30ca\u30eb",
        "BUY": "\u8cb7\u3044",
        "SELL": "\u58f2\u308a",
        "price": "\u4fa1\u683c",
        "reason": "\u7406\u7531",
        "size": "\u6570\u91cf",
        "Holdings": "\u4fdd\u6709",
        "Profit": "\u5229\u76ca",
        "Loop error": "\u30eb\u30fc\u30d7\u30a8\u30e9\u30fc",
        "baseline set failed": "\u57fa\u6e96\u5024\u8a2d\u5b9a\u5931\u6557",
        "profit sweep failed": "\u5229\u76ca\u78ba\u5b9a\u5931\u6557",
        "Final USDT": "\u6700\u7d42USDT",
        "Base holdings": "\u4fdd\u6709\u6570\u91cf",
        "Portfolio value (USDT)": "\u8cc7\u7523\u5408\u8a08(USDT)",
        "Profit %": "\u5229\u76ca\u7387",
        "Trades": "\u53d6\u5f15\u56de\u6570",
        "Fetched candles": "\u30ed\u30fc\u30bd\u30af\u53d6\u5f97",
        "Using last": "\u6700\u65b0\u3092\u4f7f\u7528",
        "Not enough data": "\u30c7\u30fc\u30bf\u4e0d\u8db3",
        "Backtest started": "\u30d0\u30c3\u30af\u30c6\u30b9\u30c8\u958b\u59cb",
        "Backtest already running": "\u30d0\u30c3\u30af\u30c6\u30b9\u30c8\u306f\u65e2\u306b\u5b9f\u884c\u4e2d",
        "Trading already running": "\u904b\u7528\u306f\u65e2\u306b\u5b9f\u884c\u4e2d",
        "Skip BUY": "\u8cb7\u3044\u3092\u30b9\u30ad\u30c3\u30d7",
        "budget reached": "\u4e0a\u9650\u5230\u9054",
    }
    translated = line
    for key, value in replacements.items():
        translated = translated.replace(key, value)
    return translated


class PlotCanvas:
    def __init__(self, canvas, label_y, label_x, font=None):
        self.canvas = canvas
        self.label_y = label_y
        self.label_x = label_x
        self.series = {}
        self.padding = (65, 30, 20, 45)
        self.font = font or ("Arial", 9)

    def set_series(self, name, color):
        if name not in self.series:
            self.series[name] = {"points": [], "color": color}

    def clear(self):
        for series in self.series.values():
            series["points"].clear()
        self.redraw()

    def add_point(self, name, x, y):
        if name not in self.series:
            return
        self.series[name]["points"].append((x, y))
        if len(self.series[name]["points"]) > 2000:
            self.series[name]["points"] = self.series[name]["points"][-2000:]

    def redraw(self):
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        if width <= 10 or height <= 10:
            return

        self.canvas.delete("all")
        self.canvas.configure(background="#ffffff")

        left, top, right, bottom = self.padding
        plot_w = max(1, width - left - right)
        plot_h = max(1, height - top - bottom)

        all_points = [pt for s in self.series.values() for pt in s["points"]]
        if all_points:
            xs = [pt[0] for pt in all_points]
            ys = [pt[1] for pt in all_points]
            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)
        else:
            x_min, x_max = 0, 1
            y_min, y_max = 0, 1

        if x_min == x_max:
            x_max = x_min + 1
        if y_min == y_max:
            y_max = y_min + 1

        y_pad = (y_max - y_min) * 0.05
        y_min -= y_pad
        y_max += y_pad

        grid_color = "#d9d9d9"
        axis_color = "#000000"
        font = self.font

        for i in range(11):
            x = left + (plot_w / 10) * i
            self.canvas.create_line(x, top, x, top + plot_h, fill=grid_color)
            label_val = x_min + (x_max - x_min) * (i / 10)
            self.canvas.create_text(x, top + plot_h + 15, text=f"{label_val:.0f}", font=font)

        for i in range(11):
            y = top + (plot_h / 10) * i
            self.canvas.create_line(left, y, left + plot_w, y, fill=grid_color)
            label_val = y_max - (y_max - y_min) * (i / 10)
            self.canvas.create_text(left - 10, y, text=f"{label_val:.0f}", font=font, anchor="e")

        self.canvas.create_rectangle(left, top, left + plot_w, top + plot_h, outline=axis_color)
        self.canvas.create_text(left + 4, top + 4, text=self.label_y, font=font, anchor="nw")
        self.canvas.create_text(left + plot_w - 4, top + plot_h - 4, text=self.label_x, font=font, anchor="se")

        for series in self.series.values():
            points = series["points"]
            if len(points) < 2:
                continue
            mapped = []
            for x_val, y_val in points:
                x = left + (x_val - x_min) / (x_max - x_min) * plot_w
                y = top + (y_max - y_val) / (y_max - y_min) * plot_h
                mapped.append((x, y))
            for i in range(1, len(mapped)):
                self.canvas.create_line(
                    mapped[i - 1][0],
                    mapped[i - 1][1],
                    mapped[i][0],
                    mapped[i][1],
                    fill=series["color"],
                    width=2,
                )


class MexcGuiApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MEXC \u30b9\u30dd\u30c3\u30c8\u30dc\u30c3\u30c8 UI")
        self.root.geometry("1100x780")

        self._style = ttk.Style()
        self._tab_style_counter = 0
        self._apply_japanese_font()
        self._tab_font = tkfont.nametofont("TkDefaultFont")

        self.log_queue = queue.Queue()
        self.graph_queue = queue.Queue()
        self.trading_thread = None
        self.trading_stop_event = None
        self.trading_log_handler = None
        self.backtest_thread = None
        self.backtest_stop_event = None
        self.last_portfolio_fetch = 0.0
        self.allow_symbols = load_allow_symbols()
        self.bt_series_colors = {"ETHUSDT": "#1f77b4", "XRPUSDT": "#2ca02c"}
        self.live_x = 0

        env = load_env()
        self.api_key_var = tk.StringVar(value=env.get("MEXC_API_KEY", ""))
        self.api_secret_var = tk.StringVar(value=env.get("MEXC_API_SECRET", ""))
        self.years_var = tk.StringVar(value="3")
        self.symbol_eth_var = tk.BooleanVar(value=True)
        self.symbol_xrp_var = tk.BooleanVar(value=True)
        self.trade_eth_var = tk.BooleanVar(value=True)
        self.trade_xrp_var = tk.BooleanVar(value=True)
        self.trade_eth_budget_var = tk.StringVar(value="1000")
        self.trade_xrp_budget_var = tk.StringVar(value="1000")
        self.trade_eth_amount_var = tk.StringVar(value="50")
        self.trade_xrp_amount_var = tk.StringVar(value="40")

        self._build_ui()
        self._schedule_updates()

    def _apply_japanese_font(self):
        preferred_fonts = ["Yu Gothic UI", "Meiryo UI", "Meiryo", "MS Gothic"]
        available = set(tkfont.families(self.root))
        chosen = None
        for name in preferred_fonts:
            if name in available:
                chosen = name
                break
        if chosen is None:
            return
        default_font = tkfont.nametofont("TkDefaultFont")
        default_font.configure(family=chosen, size=9)
        for font_name in (
            "TkTextFont",
            "TkFixedFont",
            "TkMenuFont",
            "TkHeadingFont",
            "TkCaptionFont",
            "TkTooltipFont",
        ):
            try:
                tkfont.nametofont(font_name).configure(family=chosen, size=9)
            except tk.TclError:
                pass

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        main = ttk.Frame(self.root, padding=10)
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=1)
        main.rowconfigure(1, weight=0)

        notebook = ttk.Notebook(main)
        notebook.grid(row=0, column=0, sticky="nsew")
        self._register_notebook(notebook)

        settings_tab = ttk.Frame(notebook)
        results_tab = ttk.Frame(notebook)
        notebook.add(settings_tab, text="\u8a2d\u5b9a")
        notebook.add(results_tab, text="\u7d50\u679c")

        self._build_settings_tab(settings_tab)
        self._build_results_tab(results_tab)

        footer = ttk.Frame(main)
        footer.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        footer.columnconfigure(4, weight=1)

        self.btn_start_trading = ttk.Button(footer, text="\u904b\u7528\u958b\u59cb", command=self.start_trading)
        self.btn_start_trading.grid(row=0, column=0, padx=(0, 8))
        self.btn_stop_trading = ttk.Button(footer, text="\u904b\u7528\u505c\u6b62", command=self.stop_trading)
        self.btn_stop_trading.grid(row=0, column=1, padx=(0, 8))
        self.btn_start_backtest = ttk.Button(footer, text="\u30d0\u30c3\u30af\u30c6\u30b9\u30c8\u958b\u59cb", command=self.start_backtest)
        self.btn_start_backtest.grid(row=0, column=2, padx=(0, 8))
        self.btn_stop_backtest = ttk.Button(footer, text="\u30d0\u30c3\u30af\u30c6\u30b9\u30c8\u505c\u6b62", command=self.stop_backtest)
        self.btn_stop_backtest.grid(row=0, column=3, padx=(0, 8))
        ttk.Button(footer, text="\u7d42\u4e86", command=self.on_exit).grid(row=0, column=5, sticky="e")

        self._update_button_states()

    def _build_settings_tab(self, parent):
        parent.columnconfigure(0, weight=1)

        api_frame = ttk.LabelFrame(parent, text="API \u8a2d\u5b9a", padding=10)
        api_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        api_frame.columnconfigure(1, weight=1)

        ttk.Label(api_frame, text="API\u30ad\u30fc (MEXC_API_KEY)").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(api_frame, textvariable=self.api_key_var).grid(row=0, column=1, sticky="ew")

        ttk.Label(api_frame, text="API\u30b7\u30fc\u30af\u30ec\u30c3\u30c8 (MEXC_API_SECRET)").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Entry(api_frame, textvariable=self.api_secret_var, show="*").grid(row=1, column=1, sticky="ew", pady=(8, 0))

        btn_frame = ttk.Frame(api_frame)
        btn_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(btn_frame, text=".env \u518d\u8aad\u8fbc", command=self.reload_env).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(btn_frame, text=".env \u4fdd\u5b58", command=self.save_env).grid(row=0, column=1)

        backtest_frame = ttk.LabelFrame(parent, text="\u30d0\u30c3\u30af\u30c6\u30b9\u30c8\u8a2d\u5b9a", padding=10)
        backtest_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        backtest_frame.columnconfigure(1, weight=1)

        ttk.Label(backtest_frame, text="\u671f\u9593(\u5e74)").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(backtest_frame, textvariable=self.years_var, width=8).grid(row=0, column=1, sticky="w")

        symbols_frame = ttk.Frame(backtest_frame)
        symbols_frame.grid(row=0, column=2, sticky="w", padx=(20, 0))
        ttk.Label(symbols_frame, text="\u5bfe\u8c61\u901a\u8ca8").grid(row=0, column=0, padx=(0, 8))
        ttk.Checkbutton(symbols_frame, text="ETH", variable=self.symbol_eth_var).grid(row=0, column=1, padx=(0, 8))
        ttk.Checkbutton(symbols_frame, text="XRP", variable=self.symbol_xrp_var).grid(row=0, column=2)

        trading_frame = ttk.LabelFrame(parent, text="\u904b\u7528\u8a2d\u5b9a", padding=10)
        trading_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        trading_frame.columnconfigure(1, weight=1)
        trading_frame.columnconfigure(2, weight=1)
        trading_frame.columnconfigure(3, weight=1)

        ttk.Label(trading_frame, text="\u5bfe\u8c61").grid(row=0, column=0, sticky="w")
        ttk.Label(trading_frame, text="\u6295\u8cc7\u4e0a\u9650(USDT)").grid(row=0, column=1, sticky="w")
        ttk.Label(trading_frame, text="1\u56de\u306e\u53d6\u5f15(USDT)").grid(row=0, column=2, sticky="w")

        eth_row = ttk.Frame(trading_frame)
        eth_row.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        eth_row.columnconfigure(1, weight=1)
        eth_row.columnconfigure(2, weight=1)

        ttk.Checkbutton(eth_row, text="ETH \u3092\u904b\u7528", variable=self.trade_eth_var).grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Entry(eth_row, textvariable=self.trade_eth_budget_var, width=10).grid(row=0, column=1, sticky="w", padx=(0, 12))
        ttk.Entry(eth_row, textvariable=self.trade_eth_amount_var, width=10).grid(row=0, column=2, sticky="w")

        xrp_row = ttk.Frame(trading_frame)
        xrp_row.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        xrp_row.columnconfigure(1, weight=1)
        xrp_row.columnconfigure(2, weight=1)

        ttk.Checkbutton(xrp_row, text="XRP \u3092\u904b\u7528", variable=self.trade_xrp_var).grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Entry(xrp_row, textvariable=self.trade_xrp_budget_var, width=10).grid(row=0, column=1, sticky="w", padx=(0, 12))
        ttk.Entry(xrp_row, textvariable=self.trade_xrp_amount_var, width=10).grid(row=0, column=2, sticky="w")

        config_frame = ttk.Frame(parent, padding=(5, 0))
        config_frame.grid(row=3, column=0, sticky="ew")
        ttk.Label(config_frame, text="\u53d6\u5f15\u8a2d\u5b9a\u30d5\u30a1\u30a4\u30eb").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(config_frame, text=str(DEFAULT_CONFIG_PATH)).grid(row=0, column=1, sticky="w")

    def _build_results_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        graph_container = ttk.Frame(parent)
        graph_container.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        graph_container.columnconfigure(0, weight=1)
        graph_container.rowconfigure(0, weight=1)

        graph_tabs = ttk.Notebook(graph_container)
        graph_tabs.grid(row=0, column=0, sticky="nsew")
        graph_tabs.enable_traversal()
        graph_tabs.configure(takefocus=1)
        self._register_notebook(graph_tabs)

        op_tab = ttk.Frame(graph_tabs)
        bt_tab = ttk.Frame(graph_tabs)
        graph_tabs.add(op_tab, text="\u904b\u7528\u30b0\u30e9\u30d5")
        graph_tabs.add(bt_tab, text="\u30d0\u30c3\u30af\u30c6\u30b9\u30c8\u30b0\u30e9\u30d5")

        op_tab.rowconfigure(0, weight=1)
        op_tab.columnconfigure(0, weight=1)
        bt_tab.rowconfigure(0, weight=1)
        bt_tab.columnconfigure(0, weight=1)

        self.op_canvas = tk.Canvas(op_tab, background="#ffffff", highlightthickness=0)
        self.op_canvas.grid(row=0, column=0, sticky="nsew")

        self.bt_canvas = tk.Canvas(bt_tab, background="#ffffff", highlightthickness=0)
        self.bt_canvas.grid(row=0, column=0, sticky="nsew")

        self.op_graph = PlotCanvas(self.op_canvas, "\u6b8b\u9ad8(USDT)", "\u6642\u9593", font=self._tab_font)
        self.op_graph.set_series("\u6b8b\u9ad8", "#1f77b4")
        self.bt_graph = PlotCanvas(self.bt_canvas, "\u6b8b\u9ad8(USDT)", "\u6642\u9593", font=self._tab_font)
        for symbol in DEFAULT_SYMBOLS:
            self.bt_graph.set_series(symbol, self.bt_series_colors.get(symbol, "#2ca02c"))

        self.op_canvas.bind("<Configure>", lambda _event: self.op_graph.redraw())
        self.bt_canvas.bind("<Configure>", lambda _event: self.bt_graph.redraw())

        lower_container = ttk.Frame(parent)
        lower_container.grid(row=1, column=0, sticky="nsew")
        lower_container.columnconfigure(0, weight=1)
        lower_container.rowconfigure(0, weight=1)

        log_tabs = ttk.Notebook(lower_container)
        log_tabs.grid(row=0, column=0, sticky="nsew")
        self._register_notebook(log_tabs)

        log_tab = ttk.Frame(log_tabs)
        result_tab = ttk.Frame(log_tabs)
        log_tabs.add(log_tab, text="\u30ed\u30b0")
        log_tabs.add(result_tab, text="\u7d50\u679c")

        log_tab.columnconfigure(0, weight=1)
        log_tab.rowconfigure(1, weight=1)

        log_header = ttk.Frame(log_tab)
        log_header.grid(row=0, column=0, sticky="ew")
        log_header.columnconfigure(0, weight=1)
        ttk.Label(log_header, text="\u30ed\u30b0\u8868\u793a").grid(row=0, column=0, sticky="w")
        ttk.Button(log_header, text="\u30ed\u30b0\u30af\u30ea\u30a2", command=self.clear_logs).grid(row=0, column=1, sticky="e")

        self.logs = scrolledtext.ScrolledText(log_tab, wrap="word", height=12, state="disabled")
        self.logs.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        result_tab.columnconfigure(0, weight=1)
        result_tab.rowconfigure(0, weight=1)

        self.results_text = scrolledtext.ScrolledText(result_tab, wrap="word", height=12, state="disabled")
        self.results_text.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

    def reload_env(self):
        env = load_env()
        self.api_key_var.set(env.get("MEXC_API_KEY", ""))
        self.api_secret_var.set(env.get("MEXC_API_SECRET", ""))
        self.log_queue.put(".env \u3092\u518d\u8aad\u8fbc\u3057\u307e\u3057\u305f")

    def save_env(self):
        save_env_value("MEXC_API_KEY", self.api_key_var.get().strip())
        save_env_value("MEXC_API_SECRET", self.api_secret_var.get().strip())
        load_env()
        self.log_queue.put(".env \u3092\u4fdd\u5b58\u3057\u307e\u3057\u305f")

    def start_trading(self):
        if self.trading_thread and self.trading_thread.is_alive():
            self.log_queue.put("\u904b\u7528\u306f\u65e2\u306b\u5b9f\u884c\u4e2d\u3067\u3059")
            return
        symbols = []
        if self.trade_eth_var.get():
            symbols.append("ETHUSDT")
        if self.trade_xrp_var.get():
            symbols.append("XRPUSDT")
        if not symbols:
            self.log_queue.put("\u904b\u7528\u5bfe\u8c61\u3092\u9078\u629e\u3057\u3066\u304f\u3060\u3055\u3044")
            return
        for label, value in [
            ("ETH \u6295\u8cc7\u4e0a\u9650", self.trade_eth_budget_var.get().strip()),
            ("XRP \u6295\u8cc7\u4e0a\u9650", self.trade_xrp_budget_var.get().strip()),
            ("ETH 1\u56de\u306e\u53d6\u5f15", self.trade_eth_amount_var.get().strip()),
            ("XRP 1\u56de\u306e\u53d6\u5f15", self.trade_xrp_amount_var.get().strip()),
        ]:
            if value:
                try:
                    Decimal(value)
                except InvalidOperation:
                    self.log_queue.put(f"{label}\u304c\u6570\u5024\u3067\u306f\u3042\u308a\u307e\u305b\u3093")
                    return

        os.environ["MEXC_API_KEY"] = self.api_key_var.get().strip()
        os.environ["MEXC_API_SECRET"] = self.api_secret_var.get().strip()
        os.environ["PYTHONUNBUFFERED"] = "1"
        os.environ["MEXC_ALLOW_SYMBOLS"] = ",".join(symbols)

        eth_budget = self.trade_eth_budget_var.get().strip()
        xrp_budget = self.trade_xrp_budget_var.get().strip()
        eth_trade = self.trade_eth_amount_var.get().strip()
        xrp_trade = self.trade_xrp_amount_var.get().strip()
        if eth_budget:
            os.environ["MEXC_BUDGET_USDT_ETH"] = eth_budget
        if xrp_budget:
            os.environ["MEXC_BUDGET_USDT_XRP"] = xrp_budget
        if eth_trade:
            os.environ["MEXC_TRADE_USDT_ETH"] = eth_trade
        if xrp_trade:
            os.environ["MEXC_TRADE_USDT_XRP"] = xrp_trade

        self.trading_stop_event = threading.Event()
        self._install_trading_log_handler()
        self.trading_thread = threading.Thread(
            target=self._run_trading_thread,
            args=(self.trading_stop_event,),
            daemon=True,
        )
        self.trading_thread.start()
        self.log_queue.put(f"\u904b\u7528\u3092\u958b\u59cb\u3057\u307e\u3057\u305f\u3002\u5bfe\u8c61={symbols}")
        self._update_button_states()

    def stop_trading(self):
        if self.trading_stop_event:
            self.trading_stop_event.set()
        self.log_queue.put("\u904b\u7528\u505c\u6b62\u3092\u8981\u6c42\u3057\u307e\u3057\u305f")
        self._update_button_states()

    def start_backtest(self):
        if self.backtest_thread and self.backtest_thread.is_alive():
            self.log_queue.put("\u30d0\u30c3\u30af\u30c6\u30b9\u30c8\u306f\u65e2\u306b\u5b9f\u884c\u4e2d\u3067\u3059")
            return
        symbols = []
        if self.symbol_eth_var.get():
            symbols.append("ETHUSDT")
        if self.symbol_xrp_var.get():
            symbols.append("XRPUSDT")
        if not symbols:
            self.log_queue.put("\u30d0\u30c3\u30af\u30c6\u30b9\u30c8\u5bfe\u8c61\u3092\u9078\u629e\u3057\u3066\u304f\u3060\u3055\u3044")
            return
        try:
            years = int(self.years_var.get().strip())
        except ValueError:
            self.log_queue.put("\u671f\u9593(\u5e74)\u304c\u6570\u5024\u3067\u306f\u3042\u308a\u307e\u305b\u3093")
            return

        self.bt_graph.clear()
        for symbol in symbols:
            self.bt_graph.set_series(symbol, self.bt_series_colors.get(symbol, "#2ca02c"))

        self.backtest_stop_event = threading.Event()
        self.backtest_thread = threading.Thread(
            target=self._run_backtest_thread,
            args=(symbols, years, self.backtest_stop_event),
            daemon=True,
        )
        self.backtest_thread.start()
        self.log_queue.put(f"\u30d0\u30c3\u30af\u30c6\u30b9\u30c8\u3092\u958b\u59cb\u3057\u307e\u3057\u305f\u3002\u671f\u9593={years}\u5e74, \u5bfe\u8c61={symbols}")
        self._update_button_states()

    def _run_backtest_thread(self, symbols, years, stop_event):
        def log_fn(message):
            self.log_queue.put(translate_log_line(message))

        def on_step(symbol, index, ts, close_price, portfolio_value):
            if stop_event.is_set():
                return
            if index % 5 == 0:
                self.graph_queue.put(("backtest", symbol, index, float(portfolio_value)))

        try:
            results = run_backtest(
                symbols=symbols,
                years=years,
                on_step=on_step,
                log_fn=log_fn,
                stop_event=stop_event,
            )
        except Exception as exc:
            self.log_queue.put(f"\u30d0\u30c3\u30af\u30c6\u30b9\u30c8\u5931\u6557: {exc}")
            self.root.after(0, self._update_button_states)
            return

        if stop_event.is_set():
            self.log_queue.put("\u30d0\u30c3\u30af\u30c6\u30b9\u30c8\u3092\u505c\u6b62\u3057\u307e\u3057\u305f")
            self.root.after(0, self._update_button_states)
            return

        self._update_backtest_results(results)
        self.root.after(0, self._update_button_states)

    def stop_backtest(self):
        if self.backtest_stop_event:
            self.backtest_stop_event.set()
        self.log_queue.put("\u30d0\u30c3\u30af\u30c6\u30b9\u30c8\u505c\u6b62\u3092\u8981\u6c42\u3057\u307e\u3057\u305f")
        self._update_button_states()

    def _update_backtest_results(self, results):
        lines = ["\u30d0\u30c3\u30af\u30c6\u30b9\u30c8\u7d50\u679c"]
        for symbol, data in results.items():
            lines.append("")
            lines.append(f"[{symbol}]")
            lines.append(f"\u6700\u7d42USDT: {data['final_usdt']}")
            holdings = data.get("base_holdings", {})
            if isinstance(holdings, dict):
                holdings_text = ", ".join([f"{k}: {v}" for k, v in holdings.items()]) or "\u306a\u3057"
            else:
                holdings_text = str(holdings)
            lines.append(f"\u4fdd\u6709\u6570\u91cf: {holdings_text}")
            lines.append(f"\u8cc7\u7523\u5408\u8a08(USDT): {data['portfolio_value']}")
            lines.append(f"\u5229\u76ca\u7387(%): {data['profit_pct']}")
            lines.append(f"\u53d6\u5f15\u56de\u6570: {data['trades']}")
        self._set_results_text("\n".join(lines))

    def _set_results_text(self, text):
        self.results_text.configure(state="normal")
        self.results_text.delete("1.0", "end")
        self.results_text.insert("end", text)
        self.results_text.configure(state="disabled")

    def _schedule_updates(self):
        self._refresh_process_state()
        self._poll_logs()
        self._poll_graph_updates()
        self._maybe_update_portfolio()
        self._update_button_states()
        self.root.after(100, self._schedule_updates)

    def _refresh_process_state(self):
        if self.trading_thread and not self.trading_thread.is_alive():
            self.trading_thread = None
            self.trading_stop_event = None
            self._remove_trading_log_handler()

    def _poll_logs(self):
        while True:
            try:
                msg = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.logs.configure(state="normal")
            self.logs.insert("end", msg + "\n")
            self.logs.see("end")
            self.logs.configure(state="disabled")

    def _poll_graph_updates(self):
        updated = False
        while True:
            try:
                kind, name, x, y = self.graph_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "backtest":
                self.bt_graph.add_point(name, x, y)
                updated = True
            elif kind == "live":
                self.op_graph.add_point(name, x, y)
                updated = True
        if updated:
            self.op_graph.redraw()
            self.bt_graph.redraw()

    def _maybe_update_portfolio(self):
        now = time.time()
        if not self.trading_thread or not self.trading_thread.is_alive():
            return
        if now - self.last_portfolio_fetch < 30:
            return
        self.last_portfolio_fetch = now
        threading.Thread(target=self._fetch_portfolio_snapshot, daemon=True).start()

    def _fetch_portfolio_snapshot(self):
        api_key = self.api_key_var.get().strip()
        api_secret = self.api_secret_var.get().strip()
        if not api_key or not api_secret:
            return
        try:
            client = MexcSpotClient(api_key, api_secret, base_url=os.getenv("MEXC_BASE_URL") or "https://api.mexc.com")
            account = client.account()
            balances = {}
            for entry in account.get("balances", []):
                asset = entry.get("asset")
                if not asset:
                    continue
                free = Decimal(str(entry.get("free", "0")))
                locked = Decimal(str(entry.get("locked", "0")))
                total = free + locked
                if total > 0:
                    balances[asset] = total

            base_assets = [s.replace("USDT", "") for s in self.allow_symbols if s.endswith("USDT")]
            total_value = Decimal("0")
            lines = ["\u4fdd\u6709\u72b6\u6cc1 (\u904b\u7528)"]
            usdt = balances.get("USDT", Decimal("0"))
            total_value += usdt
            lines.append(f"USDT \u6b8b\u9ad8: {usdt}")

            cost_tracker = None
            cost_file = Path("cost_basis.json")
            if cost_file.exists():
                cost_tracker = CostBasisTracker(state_file=str(cost_file))

            for base in base_assets:
                qty = balances.get(base, Decimal("0"))
                if qty <= 0:
                    continue
                symbol = f"{base}USDT"
                ticker = client.book_ticker(symbol)
                price = Decimal(str(ticker.get("bidPrice", "0")))
                value = qty * price
                total_value += value
                line = f"{base}: {qty} / \u4fa1\u683c {price} / \u8a55\u4fa1 {value}"
                if cost_tracker:
                    avg_cost = cost_tracker.get_avg_cost(symbol)
                    if avg_cost and avg_cost > 0:
                        profit_pct = (price - avg_cost) / avg_cost * Decimal("100")
                        line += f" / \u640d\u76ca {profit_pct:.2f}%"
                lines.append(line)

            lines.append(f"\u8cc7\u7523\u5408\u8a08(USDT): {total_value}")
            self.live_x += 1
            self.graph_queue.put(("live", "\u6b8b\u9ad8", self.live_x, float(total_value)))
            self._set_results_text("\n".join(lines))
        except (InvalidOperation, KeyError, ValueError) as exc:
            self.log_queue.put(f"\u6b8b\u9ad8\u53d6\u5f97\u5931\u6557: {exc}")
        except Exception as exc:
            self.log_queue.put(f"\u6b8b\u9ad8\u53d6\u5f97\u5931\u6557: {exc}")

    def clear_logs(self):
        self.logs.configure(state="normal")
        self.logs.delete("1.0", "end")
        self.logs.configure(state="disabled")
        self.log_queue.put("\u30ed\u30b0\u3092\u30af\u30ea\u30a2\u3057\u307e\u3057\u305f")

    def on_exit(self):
        self.stop_trading()
        self.stop_backtest()
        self.root.destroy()

    def _update_button_states(self):
        trading_running = self.trading_thread is not None and self.trading_thread.is_alive()
        backtest_running = self.backtest_thread is not None and self.backtest_thread.is_alive()

        if trading_running:
            self.btn_start_trading.configure(state="disabled")
            self.btn_stop_trading.configure(state="normal")
        else:
            self.btn_start_trading.configure(state="normal")
            self.btn_stop_trading.configure(state="disabled")

        if backtest_running:
            self.btn_start_backtest.configure(state="disabled")
            self.btn_stop_backtest.configure(state="normal")
        else:
            self.btn_start_backtest.configure(state="normal")
            self.btn_stop_backtest.configure(state="disabled")

    def _register_notebook(self, notebook):
        style_name = f"CustomNotebook{self._tab_style_counter}.TNotebook"
        tab_style = f"{style_name}.Tab"
        self._tab_style_counter += 1
        notebook.configure(style=style_name)
        self._style.layout(
            tab_style,
            [
                ("Notebook.tab", {"sticky": "nswe", "children": [
                    ("Notebook.padding", {"sticky": "nswe", "children": [
                        ("Notebook.label", {"sticky": "nswe"})
                    ]})
                ]})
            ],
        )

        def _resize_tabs(event):
            count = notebook.index("end")
            if count <= 0:
                return
            width_px = max(1, event.width)
            char_w = max(1, self._tab_font.measure("0"))
            tab_px = max(1, width_px // count)
            width_chars = max(6, int(tab_px / char_w) - 1)
            self._style.configure(tab_style, width=width_chars, anchor="center")

        notebook.bind("<Configure>", _resize_tabs)

    def _run_trading_thread(self, stop_event):
        try:
            run_trading(config=str(DEFAULT_CONFIG_PATH), dry_run=False, stop_event=stop_event)
        except Exception as exc:
            self.log_queue.put(f"\u904b\u7528\u5931\u6557: {exc}")
        finally:
            self.log_queue.put("\u904b\u7528\u304c\u7d42\u4e86\u3057\u307e\u3057\u305f")

    def _install_trading_log_handler(self):
        if self.trading_log_handler is not None:
            return
        handler = _GuiLogHandler(self.log_queue)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logging.getLogger().addHandler(handler)
        self.trading_log_handler = handler

    def _remove_trading_log_handler(self):
        if self.trading_log_handler is None:
            return
        logging.getLogger().removeHandler(self.trading_log_handler)
        self.trading_log_handler = None


class _GuiLogHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        try:
            msg = self.format(record)
            self.log_queue.put(translate_log_line(msg))
        except Exception:
            pass


def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    root = tk.Tk()
    app = MexcGuiApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_exit)
    root.mainloop()


if __name__ == "__main__":
    main()
