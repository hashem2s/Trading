import os

# ============================================================
# 🔱 Sovereign v52.7 | config_alpaca.py
# البروكر: Alpaca Paper Trading
# الفرق عن config.py: broker = alpaca بدل ibkr
# ============================================================

CONFIG = {

    # ── Alpaca API ────────────────────────────────────────────
    "broker": "alpaca",
    "alpaca": {
        "api_key":    os.environ.get("ALPACA_API_KEY", ""),   # from /etc/environment
        "api_secret": os.environ.get("ALPACA_API_SECRET", ""),  # from /etc/environment
        "base_url":   "https://paper-api.alpaca.markets",  # Paper Trading
        "feed":       "iex"    # iex مجاني | sip يحتاج اشتراك
    },

    # ── الأوزان المالية المعتمدة ──────────────────────────────
    "portfolio": {
        "ARM":  30029,
        "AMD":  22921,
        "TENB": 14943,
        "SNOW": 10311,
        "CRWD": 10243,
        "NET":   8991,
        "PLTR":  2562
    },

    "total_capital": 100_000,

    # ── معاملات الترجيح ───────────────────────────────────────
    "mult_high": ["TENB", "CRWD", "NET"],
    "mult_high_val": 1.5,
    "mult_normal_val": 1.2,

    # ── منطق v52.7 ────────────────────────────────────────────
    "fib_window":         15,
    "fib_default":        0.618,
    "fib_momentum":       0.382,
    "fib_normal":         0.618,
    "momentum_threshold": 0.03,
    "calibration_period": 98,
    "touch_tolerance":    0.002,

    # ── Stop / TP ─────────────────────────────────────────────
    "atr_mult_normal":  2.5,
    "atr_mult_danger":  1.5,
    "rr_ratio":         2.0,

    # ── درع QQQ ──────────────────────────────────────────────
    "qqq_sma_period":    20,
    "shield_mult_factor": 0.5,

    # ── DynamoDB ──────────────────────────────────────────────
    "dynamo": {
        "region":             "us-east-1",
        "table_trades":       "sovereign_trades",
        "table_portfolio":    "sovereign_portfolio",
        "table_calibration":  "sovereign_calibration",
        "table_stats":        "sovereign_stats",
        "table_alerts":       "sovereign_alerts"
    },

    # ── Alerts ────────────────────────────────────────────────
    "alert_daily_loss_pct":  -3.0,
    "alert_trade_loss_pct":  -2.5,

    # ── ساعات التداول (ET) ────────────────────────────────────
    "market_open":  "09:30",
    "market_close": "15:30",
    "bar_timeframe": "1Hour",   # Options: 1Min, 5Min, 15Min, 30Min, 1Hour, 1Day   # Alpaca timeframe format
    "history_days":  60
}
