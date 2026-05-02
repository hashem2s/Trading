# ============================================================
# 🔱 Sovereign v52.7 | sovereign_core.py
# THE BRAIN — Single Source of Truth
# 
# Architecture: Pilot & Drone
#   Core  = Pilot  — all logic, all timing, all decisions
#   Runner = Drone  — executes instructions blindly
#
# Main entry point: core.tick()
# ============================================================

import pandas as pd
import numpy as np
from datetime import datetime, timezone, date


class SovereignCore:

    def __init__(self, config):
        self.cfg = config

        # ── Internal State ────────────────────────────────────
        self.curr_fib        = {t: self.cfg['fib_default'] for t in self.cfg['portfolio']}
        self.last_calib_time = {t: None for t in self.cfg['portfolio']}
        self.morning_check_done = {}   # date string → set of tickers checked

    # ══════════════════════════════════════════════════════════
    # 🎯 MAIN ENTRY POINT — Runner calls ONLY this
    # ══════════════════════════════════════════════════════════
    def tick(self, current_time: datetime, positions: dict,
             all_data: dict, qqq_df) -> list:
        """
        The single entry point for all decisions.
        Runner calls this every 60 seconds.
        Returns a list of instructions to execute.

        Instruction format:
        {'action': 'BUY',         'ticker': 'ARM',  'signal': {...}}
        {'action': 'UPDATE_TP',   'ticker': 'CRWD', 'new_tp': 464.0, 'new_sl': 444.0}
        {'action': 'TIGHTEN_TP',  'ticker': 'NET',  'new_tp': 218.0, 'new_sl': 210.0}
        {'action': 'BREAKEVEN',   'ticker': 'AMD',  'new_sl': 324.75, 'new_tp': 338.0}
        {'action': 'PROFIT_LOCK', 'ticker': 'PLTR', 'new_sl': 142.0,  'new_tp': 150.0}
        """
        instructions = []

        now_et    = current_time - __import__('datetime').timedelta(hours=4)
        today_str = now_et.strftime('%Y-%m-%d')

        market_open  = current_time.replace(hour=13, minute=30, second=0, microsecond=0)
        market_close = current_time.replace(hour=20, minute=0,  second=0, microsecond=0)
        is_market_open = (market_open <= current_time <= market_close
                          and current_time.weekday() < 5)

        if not is_market_open:
            return []

        # ── 1. Morning Check (9:30 AM ET — once per day) ──────
        is_morning = (now_et.hour == 9 and now_et.minute < 31)
        if is_morning:
            if today_str not in self.morning_check_done:
                self.morning_check_done[today_str] = set()

            for ticker, pos in positions.items():
                if not pos.get('open'):
                    continue
                if ticker in self.morning_check_done.get(today_str, set()):
                    continue

                df = all_data.get(ticker)
                inst = self._morning_check(
                    ticker=ticker, df=df, qqq_df=qqq_df,
                    entry_price=pos['entry_price'],
                    current_tp=pos.get('current_tp', 0),
                    current_sl=pos.get('current_sl', 0),
                    qty=pos.get('qty', 0)
                )
                if inst:
                    instructions.append(inst)

                self.morning_check_done[today_str].add(ticker)

        # ── 2. Stop Update (every 30 min for open positions) ──
        minute = now_et.minute
        is_30min_mark = (minute % 30 == 0)

        if is_30min_mark:
            for ticker, pos in positions.items():
                if not pos.get('open'):
                    continue

                df = all_data.get(ticker)
                inst = self._stop_update(
                    ticker=ticker, df=df, qqq_df=qqq_df,
                    entry_price=pos['entry_price'],
                    current_sl=pos.get('current_sl', 0),
                    current_tp=pos.get('current_tp', 0),
                    qty=pos.get('qty', 0)
                )
                if inst:
                    instructions.append(inst)

        # ── 0. Calibrate all tickers (uses current_time not clock) ──
        for ticker in self.cfg['portfolio']:
            df = all_data.get(ticker)
            if df is not None and len(df) > 0:
                self._calibrate_fib(ticker, df, current_time)

        # ── 2b. Exit Signals — check open positions vs TP/SL ──
        for ticker, pos in positions.items():
            if not pos.get('open', False):
                continue

            df = all_data.get(ticker)
            if df is None or len(df) == 0:
                continue

            current_price = float(df.iloc[-1]['close'])
            tp = pos.get('tp') or pos.get('current_tp')
            sl = pos.get('sl') or pos.get('current_sl')

            if tp and current_price >= tp:
                instructions.append({
                    'action': 'SELL',
                    'ticker': ticker,
                    'signal': {
                        'exit_price': current_price,
                        'exit_reason': 'TP_HIT',
                        'pnl_pct': (current_price - pos.get('entry_p', pos.get('entry_price', current_price))) / pos.get('entry_p', pos.get('entry_price', current_price)) * 100
                    }
                })
                continue

            if sl and current_price <= sl:
                instructions.append({
                    'action': 'SELL',
                    'ticker': ticker,
                    'signal': {
                        'exit_price': current_price,
                        'exit_reason': 'SL_HIT',
                        'pnl_pct': (current_price - pos.get('entry_p', pos.get('entry_price', current_price))) / pos.get('entry_p', pos.get('entry_price', current_price)) * 100
                    }
                })

        # ── 3. Entry Signals (every tick) ─────────────────────
        for ticker in self.cfg['portfolio']:
            pos = positions.get(ticker, {})
            if pos.get('open'):
                continue

            df = all_data.get(ticker)
            signal = self._get_entry_signal(ticker, df, qqq_df)
            if signal:
                instructions.append({
                    'action': 'BUY',
                    'ticker': ticker,
                    'signal': signal
                })

        return instructions

    # ══════════════════════════════════════════════════════════
    # PRIVATE — Internal Logic
    # ══════════════════════════════════════════════════════════

    # ── Entry Signal — v52.7 original ────────────────────────
    def _get_entry_signal(self, ticker: str, df, qqq_df) -> dict:
        if df is None or len(df) < 20:
            return None

        # Fib already calibrated in tick() — just read current value
        fib = self.curr_fib[ticker]

        atr = self._calc_atr(df)
        if atr is None or atr <= 0:
            return None

        is_danger, qqq_val, sma_val = self._check_qqq_shield(qqq_df)
        mult       = self.cfg['mult_high_val'] if ticker in self.cfg['mult_high'] \
                     else self.cfg['mult_normal_val']
        curr_mult  = mult * self.cfg['shield_mult_factor'] if is_danger else mult
        curr_atr_m = self.cfg['atr_mult_danger'] if is_danger \
                     else self.cfg['atr_mult_normal']
        shield_str = 'DANGER' if is_danger else 'NORMAL'

        levels  = self._get_fib_levels(df, fib)
        entry_l = levels['entry']

        current_low   = float(df.iloc[-1]['low'])
        current_close = float(df.iloc[-1]['close'])

        if current_low <= entry_l * (1 + self.cfg['touch_tolerance']):
            entry_p = current_close
            stop_l  = entry_p - (atr * curr_atr_m)

            # ── TP Method ─────────────────────────────────────
            tp_method = self.cfg.get('tp_method', 'atr')
            if tp_method == 'fib':
                tp1 = levels['high']   # Fib High = natural resistance
            else:
                tp1 = entry_p + (atr * curr_atr_m * self.cfg['rr_ratio'])

            return {
                'entry_price': entry_p,
                'stop_loss':   stop_l,
                'take_profit': tp1,
                'fib_level':   fib,
                'shield':      shield_str,
                'curr_mult':   curr_mult,
                'atr':         atr,
                'qqq_price':   qqq_val,
                'qqq_sma':     sma_val,
            }

        return None

    # ── Morning Check — Rule 1 + Rule 2 ──────────────────────
    def _morning_check(self, ticker: str, df, qqq_df,
                        entry_price: float, current_tp: float,
                        current_sl: float, qty: int) -> dict:
        if df is None or len(df) < 20 or not current_tp:
            return None

        atr = self._calc_atr(df)
        if not atr:
            return None

        is_danger, qqq_val, sma_val = self._check_qqq_shield(qqq_df)
        curr_atr_m = self.cfg['atr_mult_danger'] if is_danger \
                     else self.cfg['atr_mult_normal']

        # Rule 1: QQQ Shield Flip → tighten TP
        if is_danger:
            tightened_tp = entry_price + (atr * curr_atr_m * 1.5)
            if tightened_tp < current_tp:
                return {
                    'action': 'TIGHTEN_TP',
                    'ticker': ticker,
                    'new_tp': round(tightened_tp, 2),
                    'new_sl': current_sl,
                    'qty':    qty,
                    'reason': f'Rule 1: QQQ DANGER | {qqq_val:.2f} < SMA {sma_val:.2f}'
                }

        # Rule 2: Fib resistance update
        fib    = self.curr_fib.get(ticker, self.cfg['fib_default'])
        levels = self._get_fib_levels(df, fib)
        new_resistance = levels['high']

        if new_resistance < current_tp * 0.95:
            updated_tp = entry_price + (atr * curr_atr_m * self.cfg['rr_ratio'])
            if updated_tp < current_tp:
                return {
                    'action': 'UPDATE_TP',
                    'ticker': ticker,
                    'new_tp': round(updated_tp, 2),
                    'new_sl': current_sl,
                    'qty':    qty,
                    'reason': f'Rule 2: Fib resistance {new_resistance:.2f} < TP {current_tp:.2f}'
                }

        return None

    # ── 3-Phase Stop Update ───────────────────────────────────
    def _stop_update(self, ticker: str, df, qqq_df,
                      entry_price: float, current_sl: float,
                      current_tp: float, qty: int) -> dict:
        if df is None or len(df) < 4 or not current_sl:
            return None

        current_price = float(df.iloc[-1]['close'])
        pnl_pct       = (current_price - entry_price) / entry_price

        is_danger, _, _ = self._check_qqq_shield(qqq_df)
        decaying        = self._is_momentum_decaying(df)

        # Phase 1: Static
        if pnl_pct < 0.015:
            return None

        # Phase 3: Profit Lock (all 3 conditions)
        dist_to_tp    = (current_tp - current_price) / current_tp if current_tp else 1
        profit_locked = entry_price * 1.015

        if pnl_pct >= 0.03 and dist_to_tp <= 0.10 and is_danger:
            new_sl = round(profit_locked, 2)
            if new_sl > current_sl:
                return {
                    'action': 'PROFIT_LOCK',
                    'ticker': ticker,
                    'new_sl': new_sl,
                    'new_tp': current_tp,
                    'qty':    qty,
                    'reason': f'Phase 3: {pnl_pct*100:.1f}% profit | '
                              f'{dist_to_tp*100:.1f}% from TP | QQQ DANGER'
                }

        # Phase 2: Breakeven
        if pnl_pct >= 0.015 and decaying:
            new_sl = round(entry_price, 2)
            if new_sl > current_sl:
                return {
                    'action': 'BREAKEVEN',
                    'ticker': ticker,
                    'new_sl': new_sl,
                    'new_tp': current_tp,
                    'qty':    qty,
                    'reason': f'Phase 2: {pnl_pct*100:.1f}% profit | '
                              f'3 consecutive lower 1H closes'
                }

        return None

    # ══════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════

    def _get_fib_levels(self, df, fib_level: float) -> dict:
        window    = self.cfg['fib_window']
        recent_df = df.tail(window)
        high      = float(recent_df['high'].max())
        low       = float(recent_df['low'].min())
        diff      = high - low
        return {
            'entry': high - (fib_level * diff),
            'high':  high,
            'low':   low,
        }

    def _calc_atr(self, df, periods: int = 14) -> float:
        if len(df) < periods:
            return None
        window = df.tail(periods)
        atr    = float((window['high'] - window['low']).mean())
        return atr if not pd.isna(atr) else None

    def _check_qqq_shield(self, qqq_df) -> tuple:
        if qqq_df is None or len(qqq_df) < self.cfg['qqq_sma_period']:
            return False, 0.0, 0.0
        qqq_close = float(qqq_df['close'].iloc[-1])
        sma_val   = float(qqq_df['close'].rolling(
                        self.cfg['qqq_sma_period']).mean().iloc[-1])
        return qqq_close < sma_val, qqq_close, sma_val

    def _is_momentum_decaying(self, df) -> bool:
        if len(df) < 4:
            return False
        last_4 = df.tail(4)['close'].values
        return (last_4[-1] < last_4[-2] < last_4[-3] < last_4[-4])

    def _calibrate_fib(self, ticker: str, df, current_time: datetime):
        # Use passed time — not datetime.now() — ensures backtest accuracy
        now  = current_time
        last = self.last_calib_time.get(ticker)
        if last is not None and (now - last).days < 14:
            return

        lookback    = df.tail(self.cfg['calibration_period'])
        mean_14d    = float(lookback['close'].mean())
        close_now   = float(df.iloc[-1]['close'])
        is_momentum = close_now > mean_14d * (1 + self.cfg['momentum_threshold'])

        old_fib                      = self.curr_fib[ticker]
        self.curr_fib[ticker]        = self.cfg['fib_momentum'] if is_momentum \
                                       else self.cfg['fib_normal']
        self.last_calib_time[ticker] = now
        print(f"🔄 [{now.strftime('%Y-%m-%d')}] Calibrated {ticker}: {old_fib} -> {self.curr_fib[ticker]}")

    # ── Public helpers (for backtest / reporting) ─────────────
    def get_fib_state(self) -> dict:
        return dict(self.curr_fib)

    def get_calibration_state(self) -> dict:
        return {t: str(v) for t, v in self.last_calib_time.items()}

    def calc_atr(self, df, periods=14):
        return self._calc_atr(df, periods)

    def check_qqq_shield(self, qqq_df):
        return self._check_qqq_shield(qqq_df)
