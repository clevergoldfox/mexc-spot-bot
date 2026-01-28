import os
import sys
import time
import queue
import threading
import subprocess
from pathlib import Path
from decimal import Decimal, InvalidOperation
import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext

import yaml
from dotenv import dotenv_values, load_dotenv

from mexc_bot.mexc.client import MexcSpotClient
from mexc_bot.services.cost_basis import CostBasisTracker
from mexc_bot.backtest.run_backtest import run as run_backtest


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
        "Bot started": "ボット開始",
        "Stopping": "停止中",
        "Signal": "シグナル",
        "BUY": "買い",
        "SELL": "売り",
        "price": "価格",
        "reason": "理由",
        "size": "サイズ",
        "Holdings": "保有",
        "Profit": "利益",
        "Loop error": "ループエラー",
        "baseline set failed": "基準設定失敗",
        "profit sweep failed": "利益スイープ失敗",
        "Final USDT": "最終USDT",
        "Base holdings": "保有資産",
        "Portfolio value (USDT)": "評価額(USDT)",
        "Profit %": "利益率",
        "Trades": "取引回数",
        "Fetched candles": "取得ローソク数",
        "Using last": "直近の本数を使用",
        "Not enough data": "データ不足",
        "Backtest started": "バックテスト開始",
        "Backtest already running": "バックテストは実行中です",
        "Trading already running": "運用は実行中です",
    }
    translated = line
    for key, value in replacements.items():
        translated = translated.replace(key, value)
    return translated


def reader_thread(proc, log_queue, prefix):
    try:
        for line in iter(proc.stdout.readline, ""):
            if not line:
                break
            translated = translate_log_line(line.rstrip())
            log_queue.put(f"{prefix}{translated}")
    except Exception as exc:
        log_queue.put(f"{prefix}ログ読込エラー: {exc}")


def terminate_process(proc, log_queue, label):
    if not proc:
        return None
    if proc.poll() is None:
        log_queue.put(f"{label}を停止します...")
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    return None


class PlotCanvas:
    def __init__(self, canvas, label_y, label_x):
        self.canvas = canvas
        self.label_y = label_y
        self.label_x = label_x
        self.series = {}
        self.padding = (55, 15, 20, 35)
        self._last_size = (0, 0)

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
        self._last_size = (width, height)

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
        font = ("Arial", 9)

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
        self.canvas.create_text(left, top - 8, text=self.label_y, font=font, anchor="sw")
        self.canvas.create_text(left + plot_w, top + plot_h + 25, text=self.label_x, font=font, anchor="se")

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
        self.root.title("MEXC スポットボット UI")
        self.root.geometry("1100x780")

        self.log_queue = queue.Queue()
        self.graph_queue = queue.Queue()
        self.trading_proc = None
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

        self._build_ui()
        self._schedule_updates()

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

        settings_tab = ttk.Frame(notebook)
        results_tab = ttk.Frame(notebook)
        notebook.add(settings_tab, text="設定")
        notebook.add(results_tab, text="結果")

        self._build_settings_tab(settings_tab)
        self._build_results_tab(results_tab)

        footer = ttk.Frame(main)
        footer.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        footer.columnconfigure(4, weight=1)

        ttk.Button(footer, text="運用開始", command=self.start_trading).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(footer, text="運用停止", command=self.stop_trading).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(footer, text="バックテスト開始", command=self.start_backtest).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(footer, text="バックテスト停止", command=self.stop_backtest).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(footer, text="終了", command=self.on_exit).grid(row=0, column=5, sticky="e")

    def _build_settings_tab(self, parent):
        parent.columnconfigure(0, weight=1)

        api_frame = ttk.LabelFrame(parent, text="API 設定", padding=10)
        api_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        api_frame.columnconfigure(1, weight=1)

        ttk.Label(api_frame, text="APIキー (MEXC_API_KEY)").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(api_frame, textvariable=self.api_key_var).grid(row=0, column=1, sticky="ew")

        ttk.Label(api_frame, text="APIシークレット (MEXC_API_SECRET)").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Entry(api_frame, textvariable=self.api_secret_var, show="*").grid(row=1, column=1, sticky="ew", pady=(8, 0))

        btn_frame = ttk.Frame(api_frame)
        btn_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(btn_frame, text=".env 再読込", command=self.reload_env).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(btn_frame, text=".env 保存", command=self.save_env).grid(row=0, column=1)

        backtest_frame = ttk.LabelFrame(parent, text="バックテスト設定", padding=10)
        backtest_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        backtest_frame.columnconfigure(1, weight=1)

        ttk.Label(backtest_frame, text="期間(年)").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(backtest_frame, textvariable=self.years_var, width=8).grid(row=0, column=1, sticky="w")

        symbols_frame = ttk.Frame(backtest_frame)
        symbols_frame.grid(row=0, column=2, sticky="w", padx=(20, 0))
        ttk.Label(symbols_frame, text="対象通貨").grid(row=0, column=0, padx=(0, 8))
        ttk.Checkbutton(symbols_frame, text="ETH", variable=self.symbol_eth_var).grid(row=0, column=1, padx=(0, 8))
        ttk.Checkbutton(symbols_frame, text="XRP", variable=self.symbol_xrp_var).grid(row=0, column=2)

        config_frame = ttk.Frame(parent, padding=(5, 0))
        config_frame.grid(row=2, column=0, sticky="ew")
        ttk.Label(config_frame, text="取引設定ファイル").grid(row=0, column=0, sticky="w", padx=(0, 8))
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

        op_tab = ttk.Frame(graph_tabs)
        bt_tab = ttk.Frame(graph_tabs)
        graph_tabs.add(op_tab, text="運用グラフ")
        graph_tabs.add(bt_tab, text="バックテストグラフ")

        op_tab.rowconfigure(0, weight=1)
        op_tab.columnconfigure(0, weight=1)
        bt_tab.rowconfigure(0, weight=1)
        bt_tab.columnconfigure(0, weight=1)

        self.op_canvas = tk.Canvas(op_tab, background="#ffffff", highlightthickness=0)
        self.op_canvas.grid(row=0, column=0, sticky="nsew")

        self.bt_canvas = tk.Canvas(bt_tab, background="#ffffff", highlightthickness=0)
        self.bt_canvas.grid(row=0, column=0, sticky="nsew")

        self.op_graph = PlotCanvas(self.op_canvas, "残高(USDT)", "時間")
        self.op_graph.set_series("運用", "#1f77b4")
        self.bt_graph = PlotCanvas(self.bt_canvas, "残高(USDT)", "バー")
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

        log_tab = ttk.Frame(log_tabs)
        result_tab = ttk.Frame(log_tabs)
        log_tabs.add(log_tab, text="ログ")
        log_tabs.add(result_tab, text="結果")

        log_tab.columnconfigure(0, weight=1)
        log_tab.rowconfigure(1, weight=1)

        log_header = ttk.Frame(log_tab)
        log_header.grid(row=0, column=0, sticky="ew")
        log_header.columnconfigure(0, weight=1)
        ttk.Label(log_header, text="ログ表示").grid(row=0, column=0, sticky="w")
        ttk.Button(log_header, text="ログクリア", command=self.clear_logs).grid(row=0, column=1, sticky="e")

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
        self.log_queue.put("`.env` を再読込しました。")

    def save_env(self):
        save_env_value("MEXC_API_KEY", self.api_key_var.get().strip())
        save_env_value("MEXC_API_SECRET", self.api_secret_var.get().strip())
        load_env()
        self.log_queue.put("`.env` を保存しました。")

    def start_trading(self):
        if self.trading_proc and self.trading_proc.poll() is None:
            self.log_queue.put("運用はすでに実行中です。")
            return
        env_copy = os.environ.copy()
        env_copy["MEXC_API_KEY"] = self.api_key_var.get().strip()
        env_copy["MEXC_API_SECRET"] = self.api_secret_var.get().strip()
        env_copy["PYTHONUNBUFFERED"] = "1"
        cmd = [
            sys.executable,
            "-u",
            "-m",
            "mexc_bot",
            "run",
            "--config",
            str(DEFAULT_CONFIG_PATH),
        ]
        self.trading_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env_copy,
            bufsize=1,
        )
        threading.Thread(
            target=reader_thread,
            args=(self.trading_proc, self.log_queue, "[運用] "),
            daemon=True,
        ).start()
        self.log_queue.put("運用を開始しました。")

    def stop_trading(self):
        self.trading_proc = terminate_process(self.trading_proc, self.log_queue, "運用")

    def start_backtest(self):
        if self.backtest_thread and self.backtest_thread.is_alive():
            self.log_queue.put("バックテストはすでに実行中です。")
            return
        symbols = []
        if self.symbol_eth_var.get():
            symbols.append("ETHUSDT")
        if self.symbol_xrp_var.get():
            symbols.append("XRPUSDT")
        if not symbols:
            self.log_queue.put("バックテスト対象の通貨を選択してください。")
            return
        try:
            years = int(self.years_var.get().strip())
        except ValueError:
            self.log_queue.put("期間(年)の入力が正しくありません。")
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
        self.log_queue.put(f"バックテストを開始しました。期間={years}年, 通貨={symbols}")

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
            self.log_queue.put(f"バックテストエラー: {exc}")
            return

        if stop_event.is_set():
            self.log_queue.put("バックテストを停止しました。")
            return

        self._update_backtest_results(results)

    def stop_backtest(self):
        if self.backtest_stop_event:
            self.backtest_stop_event.set()
        self.log_queue.put("バックテスト停止を要求しました。")

    def _update_backtest_results(self, results):
        lines = ["バックテスト結果"]
        for symbol, data in results.items():
            lines.append(f"\n[{symbol}]")
            lines.append(f"最終USDT: {data['final_usdt']}")
            holdings = data.get("base_holdings", {})
            if isinstance(holdings, dict):
                holdings_text = ", ".join([f"{k}: {v}" for k, v in holdings.items()]) or "なし"
            else:
                holdings_text = str(holdings)
            lines.append(f"保有資産: {holdings_text}")
            lines.append(f"評価額(USDT): {data['portfolio_value']}")
            lines.append(f"利益率(%): {data['profit_pct']}")
            lines.append(f"取引回数: {data['trades']}")
        self._set_results_text("\n".join(lines))

    def _set_results_text(self, text):
        self.results_text.configure(state="normal")
        self.results_text.delete("1.0", "end")
        self.results_text.insert("end", text)
        self.results_text.configure(state="disabled")

    def _schedule_updates(self):
        self._poll_logs()
        self._poll_graph_updates()
        self._maybe_update_portfolio()
        self.root.after(100, self._schedule_updates)

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
        if not self.trading_proc or self.trading_proc.poll() is not None:
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
            lines = ["運用結果 (最新)"]
            usdt = balances.get("USDT", Decimal("0"))
            total_value += usdt
            lines.append(f"USDT 残高: {usdt}")

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
                line = f"{base}: {qty} / 価格 {price} / 評価 {value}"
                if cost_tracker:
                    avg_cost = cost_tracker.get_avg_cost(symbol)
                    if avg_cost and avg_cost > 0:
                        profit_pct = (price - avg_cost) / avg_cost * Decimal("100")
                        line += f" / 損益 {profit_pct:.2f}%"
                lines.append(line)

            lines.append(f"総評価額(USDT): {total_value}")
            self.live_x += 1
            self.graph_queue.put(("live", "運用", self.live_x, float(total_value)))
            self._set_results_text("\n".join(lines))
        except (InvalidOperation, KeyError, ValueError) as exc:
            self.log_queue.put(f"評価取得エラー: {exc}")
        except Exception as exc:
            self.log_queue.put(f"評価取得エラー: {exc}")

    def clear_logs(self):
        self.logs.configure(state="normal")
        self.logs.delete("1.0", "end")
        self.logs.configure(state="disabled")
        self.log_queue.put("ログをクリアしました。")

    def on_exit(self):
        self.stop_trading()
        self.stop_backtest()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = MexcGuiApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_exit)
    root.mainloop()


if __name__ == "__main__":
    main()
