# ============================================================
# 🔱 Sovereign | regime_detector.py
# Market Regime Detection — Composite Score
#
# Completely standalone — does not modify any existing code.
# Enable/disable via checkbox in GUI.
# Reversible: OFF = exact same behavior as before.
#
# Score logic:
#   0     = STRONG  → full size, full TP
#   1     = NORMAL  → 75% size
#   2     = CAUTION → 50% size, smaller TP
#   3     = WEAK    → 25% size, smaller TP
#   4+    = DANGER  → 10% size, minimal TP
# ============================================================

import pandas as pd
import numpy as np


# ── Default thresholds — all overridable from GUI ──────────────
DEFAULT_CONFIG = {
    # QQQ signals
    'qqq_below_sma20_score':   1,    # QQQ below 20-day SMA
    'qqq_5d_drop_pct':        -3.0,  # QQQ dropped >3% in 5 days
    'qqq_5d_drop_score':       1,

    # VIX signals
    'vix_warn_level':         25,    # VIX above this = warning
    'vix_warn_score':          1,
    'vix_danger_level':       35,    # VIX above this = danger
    'vix_danger_score':        2,    # extra weight

    # Win rate signals (last N trades)
    'wr_lookback':            10,    # last 10 trades
    'wr_caution_pct':         35.0,  # WR below 35% = caution
    'wr_caution_score':        1,
    'wr_danger_pct':          25.0,  # WR below 25% = danger
    'wr_danger_score':         2,
}

# ── Regime levels → position size multiplier + TP/SL ──────────
REGIME_LEVELS = {
    0: {'label': 'STRONG',  'emoji': '🟢', 'size_mult': 1.00, 'tp': 0.075, 'sl': 0.038},
    1: {'label': 'NORMAL',  'emoji': '🟡', 'size_mult': 0.75, 'tp': 0.075, 'sl': 0.038},
    2: {'label': 'CAUTION', 'emoji': '🟠', 'size_mult': 0.50, 'tp': 0.050, 'sl': 0.025},
    3: {'label': 'WEAK',    'emoji': '🔴', 'size_mult': 0.25, 'tp': 0.030, 'sl': 0.015},
    4: {'label': 'DANGER',  'emoji': '⛔', 'size_mult': 0.10, 'tp': 0.020, 'sl': 0.015},
}


def get_regime(qqq_df=None, vix_df=None,
               recent_trades=None, cfg=None) -> dict:
    """
    Calculate current market regime score.

    Parameters
    ----------
    qqq_df       : DataFrame with 'close' column (daily QQQ)
    vix_df       : DataFrame with 'close' column (daily VIX)
    recent_trades: list of dicts with 'pnl_pct' key (last N trades)
    cfg          : dict of threshold overrides (from GUI)

    Returns
    -------
    dict with: score, label, emoji, size_mult, tp, sl, reasons
    """
    c       = {**DEFAULT_CONFIG, **(cfg or {})}
    score   = 0
    reasons = []

    # ── Signal 1: QQQ below 20-day SMA ────────────────────────
    if qqq_df is not None and len(qqq_df) >= 20:
        try:
            qqq_close = float(qqq_df['close'].iloc[-1])
            qqq_sma20 = float(qqq_df['close'].tail(20).mean())
            if qqq_close < qqq_sma20:
                score += c['qqq_below_sma20_score']
                reasons.append(
                    f"QQQ {qqq_close:.1f} < SMA20 {qqq_sma20:.1f} "
                    f"(+{c['qqq_below_sma20_score']})"
                )
        except Exception:
            pass

    # ── Signal 2: QQQ 5-day return ────────────────────────────
    if qqq_df is not None and len(qqq_df) >= 6:
        try:
            qqq_now  = float(qqq_df['close'].iloc[-1])
            qqq_5d   = float(qqq_df['close'].iloc[-6])
            qqq_ret  = (qqq_now - qqq_5d) / qqq_5d * 100
            if qqq_ret < c['qqq_5d_drop_pct']:
                score += c['qqq_5d_drop_score']
                reasons.append(
                    f"QQQ 5d return {qqq_ret:.1f}% < {c['qqq_5d_drop_pct']}% "
                    f"(+{c['qqq_5d_drop_score']})"
                )
        except Exception:
            pass

    # ── Signal 3: VIX level ────────────────────────────────────
    if vix_df is not None and len(vix_df) > 0:
        try:
            vix_now = float(vix_df['close'].iloc[-1])
            if vix_now > c['vix_danger_level']:
                score += c['vix_danger_score']
                reasons.append(
                    f"VIX {vix_now:.1f} > {c['vix_danger_level']} DANGER "
                    f"(+{c['vix_danger_score']})"
                )
            elif vix_now > c['vix_warn_level']:
                score += c['vix_warn_score']
                reasons.append(
                    f"VIX {vix_now:.1f} > {c['vix_warn_level']} WARNING "
                    f"(+{c['vix_warn_score']})"
                )
        except Exception:
            pass

    # ── Signal 4: Recent win rate ──────────────────────────────
    if recent_trades and len(recent_trades) >= c['wr_lookback']:
        try:
            last_n = recent_trades[-c['wr_lookback']:]
            wins   = sum(1 for t in last_n if float(t.get('pnl_pct', 0)) > 0)
            wr     = wins / len(last_n) * 100
            if wr < c['wr_danger_pct']:
                score += c['wr_danger_score']
                reasons.append(
                    f"Win rate {wr:.0f}% < {c['wr_danger_pct']}% DANGER "
                    f"(+{c['wr_danger_score']})"
                )
            elif wr < c['wr_caution_pct']:
                score += c['wr_caution_score']
                reasons.append(
                    f"Win rate {wr:.0f}% < {c['wr_caution_pct']}% CAUTION "
                    f"(+{c['wr_caution_score']})"
                )
        except Exception:
            pass

    # ── Map score to regime level ──────────────────────────────
    level  = min(score, 4)
    regime = REGIME_LEVELS[level].copy()
    regime['score']   = score
    regime['reasons'] = reasons

    return regime


def regime_summary(regime: dict) -> str:
    """Human-readable summary for logging."""
    r = regime
    lines = [
        f"{r['emoji']} Regime: {r['label']} (score={r['score']}) | "
        f"Size: {r['size_mult']*100:.0f}% | "
        f"TP: {r['tp']*100:.1f}% | "
        f"SL: {r['sl']*100:.1f}%"
    ]
    for reason in r.get('reasons', []):
        lines.append(f"   ↳ {reason}")
    return '\n'.join(lines)
