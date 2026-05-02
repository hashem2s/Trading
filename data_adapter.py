# ============================================================
# 🔱 Sovereign v52.7 | data_adapter.py
# The Translator — unified data fetching
#
# Supported modes:
#   'backtest'  → yfinance
#   'live'      → Alpaca API
#   'csv'       → local CSV files
# ============================================================

import pandas as pd
from datetime import datetime, timezone, timedelta


class DataAdapter:

    def __init__(self, mode: str = 'backtest', config: dict = None,
                 broker_client=None, csv_dir: str = None):
        self.mode       = mode
        self.cfg        = config or {}
        self.client     = broker_client
        self.csv_dir    = csv_dir   # path to folder with CSV files

        # Timeframe from config — not hardcoded
        self._timeframe = self.cfg.get('bar_timeframe') or self.cfg.get('interval', '1Hour')

    # ── Fetch single ticker ───────────────────────────────────
    def fetch_data(self, ticker: str) -> pd.DataFrame:
        if self.mode == 'csv':
            return self._fetch_csv(ticker)
        elif self.mode == 'backtest':
            return self._fetch_yfinance(ticker)
        else:
            return self._fetch_alpaca(ticker)

    # ── Fetch QQQ for Shield ──────────────────────────────────
    def fetch_qqq(self) -> pd.DataFrame:
        if self.mode == 'csv':
            return self._fetch_csv('QQQ')
        elif self.mode == 'backtest':
            return self._fetch_yfinance('QQQ')
        else:
            return self._fetch_alpaca('QQQ')

    # ── Fetch all tickers at once ─────────────────────────────
    def fetch_all(self, tickers: list) -> dict:
        if self.mode == 'csv':
            return {t: self._fetch_csv(t) for t in tickers}
        elif self.mode == 'backtest':
            return self._fetch_yfinance_bulk(tickers)
        else:
            return self._fetch_alpaca_bulk(tickers)

    # ── Warm-up period — dynamic from config ─────────────────
    def get_warmup_period(self) -> int:
        """
        Returns the minimum number of candles needed
        before Core can make reliable decisions.
        Uses the longest indicator period + buffer.
        """
        return max(
            self.cfg.get('calibration_period', 98),
            self.cfg.get('fib_window', 15),
            self.cfg.get('qqq_sma_period', 20)
        ) + 10

    # ── Capital Allocation ────────────────────────────────────
    @staticmethod
    def get_allocation(ticker: str, config: dict) -> float:
        """
        Returns capital allocated to ticker.
        Supports two modes:
          1. Fixed weights: {'ARM': 30029, 'AMD': 22921, ...}
          2. Equal weight:  total_capital / num_tickers
        """
        portfolio = config.get('portfolio', {})

        # Mode 1: fixed weights (dict with values)
        if isinstance(portfolio, dict) and portfolio:
            val = portfolio.get(ticker, 0)
            if isinstance(val, (int, float)) and val > 0:
                return float(val)

        # Mode 2: equal weight (list of tickers or missing values)
        tickers = list(portfolio.keys()) if isinstance(portfolio, dict) \
                  else portfolio
        total   = config.get('total_capital', 100_000)
        n       = len(tickers)
        return total / n if n > 0 else 0

    # ── CSV Mode ──────────────────────────────────────────────
    def _fetch_csv(self, ticker: str) -> pd.DataFrame:
        """
        Reads from local CSV file.
        Expected filename: {csv_dir}/{ticker}.csv
        Expected columns: date/datetime, open, high, low, close, volume
        """
        import os
        if not self.csv_dir:
            raise ValueError("csv_dir must be set when mode='csv'")

        path = os.path.join(self.csv_dir, f"{ticker}.csv")
        if not os.path.exists(path):
            print(f"⚠️  CSV not found: {path}")
            return None

        df = pd.read_csv(path)

        # Normalize column names
        df.columns = [c.lower().strip() for c in df.columns]

        # Find datetime column
        date_col = next((c for c in df.columns
                         if c in ['date', 'datetime', 'timestamp', 'time']), None)
        if date_col:
            df[date_col] = pd.to_datetime(df[date_col])
            df = df.set_index(date_col).sort_index()

        # Ensure required columns exist
        required = ['open', 'high', 'low', 'close']
        missing  = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"{ticker}.csv missing columns: {missing}")

        return df

    # ── Backtest: Yahoo Finance ───────────────────────────────
    def _fetch_yfinance(self, ticker: str) -> pd.DataFrame:
        import yfinance as yf

        # Map config timeframe to yfinance interval
        tf_map = {
            '1Min': '1m', '5Min': '5m', '15Min': '15m',
            '30Min': '30m', '1Hour': '1h', '1Day': '1d'
        }
        interval = tf_map.get(self._timeframe, '1h')

        data = yf.download(
            ticker,
            period=f"{self.cfg.get('history_days', 60)}d",
            interval=interval,
            progress=False,
            auto_adjust=True
        )
        if data.empty:
            return None
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        data.columns = [c.lower() for c in data.columns]
        return data

    def _fetch_yfinance_bulk(self, tickers: list) -> dict:
        import yfinance as yf

        tf_map = {
            '1Min': '1m', '5Min': '5m', '15Min': '15m',
            '30Min': '30m', '1Hour': '1h', '1Day': '1d'
        }
        interval = tf_map.get(self._timeframe, '1h')

        raw = yf.download(
            tickers,
            period=f"{self.cfg.get('history_days', 60)}d",
            interval=interval,
            progress=False,
            auto_adjust=True
        )
        result = {}
        for t in tickers:
            try:
                df = raw.xs(t, axis=1, level=1).copy()
                df.columns = [c.lower() for c in df.columns]
                result[t] = df
            except Exception:
                result[t] = None
        return result

    # ── Live: Alpaca ──────────────────────────────────────────
    def _fetch_alpaca(self, ticker: str) -> pd.DataFrame:
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        tf_map = {
            '1Min':  TimeFrame(1,  TimeFrameUnit.Minute),
            '5Min':  TimeFrame(5,  TimeFrameUnit.Minute),
            '15Min': TimeFrame(15, TimeFrameUnit.Minute),
            '30Min': TimeFrame(30, TimeFrameUnit.Minute),
            '1Hour': TimeFrame.Hour,
            '1Day':  TimeFrame.Day
        }
        tf = tf_map.get(self._timeframe, TimeFrame.Hour)

        end   = datetime.now(timezone.utc)
        start = end - timedelta(days=self.cfg.get('history_days', 60))

        req = StockBarsRequest(
            symbol_or_symbols=ticker,
            timeframe=tf,
            start=start, end=end,
            feed=self.cfg.get('alpaca', {}).get('feed', 'iex')
        )
        bars = self.client.get_stock_bars(req)
        df   = bars.df

        if isinstance(df.index, pd.MultiIndex):
            df = df.reset_index(level=0, drop=True)

        df.columns = [c.lower() for c in df.columns]
        return df if not df.empty else None

    def _fetch_alpaca_bulk(self, tickers: list) -> dict:
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        tf_map = {
            '1Min':  TimeFrame(1,  TimeFrameUnit.Minute),
            '5Min':  TimeFrame(5,  TimeFrameUnit.Minute),
            '15Min': TimeFrame(15, TimeFrameUnit.Minute),
            '30Min': TimeFrame(30, TimeFrameUnit.Minute),
            '1Hour': TimeFrame.Hour,
            '1Day':  TimeFrame.Day
        }
        tf = tf_map.get(self._timeframe, TimeFrame.Hour)

        end   = datetime.now(timezone.utc)
        start = end - timedelta(days=self.cfg.get('history_days', 60))

        req = StockBarsRequest(
            symbol_or_symbols=tickers,
            timeframe=tf,
            start=start, end=end,
            feed=self.cfg.get('alpaca', {}).get('feed', 'iex')
        )
        bars_df = self.client.get_stock_bars(req).df
        result  = {}

        for t in tickers:
            try:
                df = bars_df.loc[t].copy()
                df.columns = [c.lower() for c in df.columns]
                result[t] = df
            except Exception:
                result[t] = None

        return result
