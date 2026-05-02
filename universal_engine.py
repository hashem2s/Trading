# ============================================================
# 🚀 Universal Engine | المحرك الشامل للاختبار (v53.2)
# التحديث: إضافة تقارير تفصيلية لكل سهم بشكل منفصل (Detailed Per-Ticker Metrics)
# ============================================================
import pandas as pd

class UniversalBacktest:
    def __init__(self, core, adapter, config):
        self.core = core
        self.adapter = adapter
        self.config = config
        self.trade_history = []

    def run(self, tickers):
        all_data = self.adapter.fetch_all(tickers)
        qqq_df = getattr(self.adapter, 'fetch_qqq', lambda: None)()
        self._run_loop(tickers, all_data, qqq_df)
        self._print_final_report()

    def _run_loop(self, tickers, all_data, qqq_df):
        positions = {t: {'open': False} for t in tickers}
        timestamps = all_data[tickers[0]].index
        tf = self.config.get('bar_timeframe', '1Hour')
        print(f"🚀 Backtest Engine | Timeframe: {tf} | Bars: {len(timestamps)}")

        for i in range(100, len(timestamps)):
            current_time = timestamps[i]
            for t in tickers:
                if positions[t]['open']:
                    h, l = all_data[t]['high'].iloc[i], all_data[t]['low'].iloc[i]
                    if l <= positions[t]['sl']:
                        self._close_trade(t, positions[t]['sl'], "SL_HIT", current_time, positions)
                    elif h >= positions[t]['tp']:
                        self._close_trade(t, positions[t]['tp'], "TP_HIT", current_time, positions)

            sliced_data = {t: all_data[t].iloc[:i+1] for t in tickers}
            instructions = self.core.tick(current_time, positions, sliced_data, qqq_df)
            for inst in instructions:
                t, s = inst['ticker'], inst['signal']
                positions[t] = {
                    'open': True, 'entry': s['entry_price'], 'sl': s['stop_loss'], 
                    'tp': s['take_profit'], 'buy_reason': s.get('reason', 'Fib Touch')
                }

    def _close_trade(self, ticker, exit_p, reason, time, positions):
        p = positions[ticker]
        profit = ((exit_p - p['entry']) / p['entry']) * 100
        self.trade_history.append({
            'الرمز': ticker, 'دخول': round(p['entry'], 2), 'خروج': round(exit_p, 2),
            'سبب الشراء': p['buy_reason'], 'سبب البيع': reason, 'الربح %': round(profit, 2)
        })
        positions[ticker] = {'open': False}
        self.core.register_exit(ticker, reason, time)

    def _calc_metrics(self, df_slice):
        if df_slice.empty: return {"trades": 0, "win_rate": 0, "pnl": 0}
        wins = len(df_slice[df_slice['الربح %'] > 0])
        return {
            "trades": len(df_slice),
            "win_rate": round((wins / len(df_slice)) * 100, 1),
            "pnl": round(df_slice['الربح %'].sum(), 2)
        }

    def _print_final_report(self):
        df = pd.DataFrame(self.trade_history)
        print("\n" + "="*95)
        print("📊 تقرير صفقات المحفظة الموحد (Sovereign v53.2)")
        print("="*95)
        
        if not df.empty:
            print(df.to_markdown(index=False))
            
            print("\n" + "🔍 تحليل أداء كل سهم على حدة:")
            print("-" * 45)
            ticker_summary = []
            for t in df['الرمز'].unique():
                m = self._calc_metrics(df[df['الرمز'] == t])
                ticker_summary.append({
                    'السهم': t, 
                    'عدد الصفقات': m['trades'], 
                    'نسبة النجاح %': f"{m['win_rate']}%", 
                    'صافي الربح %': f"{m['pnl']}%"
                })
            
            summary_df = pd.DataFrame(ticker_summary)
            print(summary_df.to_markdown(index=False))

            print("\n" + "="*45)
            print("📈 ملخص الأداء الكلي للمحفظة")
            print("-" * 45)
            total_m = self._calc_metrics(df)
            print(f"✅ إجمالي الصفقات  : {total_m['trades']}")
            print(f"🎯 نسبة نجاح عامة : {total_m['win_rate']}%")
            print(f"💰 صافي PnL الكلي  : {total_m['pnl']:+.2f}%")
        else:
            print("⚠️ لم يتم تنفيذ أي صفقات.")
        print("="*45)