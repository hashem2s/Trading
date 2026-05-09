# ============================================================
# 🚀 Universal Engine | المحرك الشامل للاختبار (v54.0)
# المصدر: تم تعديله ليتوافق مع المعايير البرمجية العالمية
# ============================================================
import pandas as pd
import datetime

class UniversalBacktest:
    def __init__(self, core, adapter, config):
        self.core = core
        self.adapter = adapter
        self.config = config
        self.trade_history = []
        # ميزانية كل سهم = إجمالي رأس المال / أقصى عدد أسهم مسموح بها
        self.allocation = self.config.get('initial_capital', 100000) / self.config.get('max_falcons', 7)

    def run(self, tickers):
        all_data = self.adapter.fetch_all(tickers)
        # محاولة جلب بيانات QQQ إذا كانت موجودة كفلتر للسوق
        qqq_df = getattr(self.adapter, 'fetch_qqq', lambda: None)()
        self._run_loop(tickers, all_data, qqq_df)
        self._print_final_report()

    def _run_loop(self, tickers, all_data, qqq_df):
        # تصفية الأسهم التي ليس لها بيانات لتجنب الانهيار
        valid_tickers = [t for t in tickers if t in all_data and not all_data[t].empty]
        if not valid_tickers:
            print("⚠️ لا توجد بيانات كافية للبدء.")
            return

        positions = {t: {'open': False} for t in valid_tickers}
        timestamps = all_data[valid_tickers[0]].index
        
        print(f"🚀 بدء الاختبار | النطاق: {len(timestamps)} شمعة")

        for i in range(100, len(timestamps)):
            current_time = timestamps[i]
            
            for t in valid_tickers:
                if positions[t]['open']:
                    # منطق الخروج (Stop Loss / Take Profit)
                    h, l = all_data[t]['high'].iloc[i], all_data[t]['low'].iloc[i]
                    if l <= positions[t]['sl']:
                        self._close_trade(t, positions[t]['sl'], "Stop Loss", current_time, positions)
                    elif h >= positions[t]['tp']:
                        self._close_trade(t, positions[t]['tp'], "Take Profit", current_time, positions)

            # استدعاء الـ Core للحصول على إشارات دخول جديدة
            sliced_data = {t: all_data[t].iloc[:i+1] for t in valid_tickers}
            instructions = self.core.tick(current_time, positions, sliced_data, qqq_df)
            
            for inst in instructions:
                t, s = inst['ticker'], inst['signal']
                if not positions[t]['open']:
                    positions[t] = {
                        'open': True, 
                        'entry': s['entry_price'], 
                        'sl': s['stop_loss'], 
                        'tp': s['take_profit'], 
                        'buy_reason': s.get('reason', 'Fib Touch'),
                        'entry_time': current_time
                    }

    def _close_trade(self, ticker, exit_p, reason, time, positions):
        p = positions[ticker]
        profit_pct = ((exit_p - p['entry']) / p['entry']) * 100
        profit_usd = self.allocation * (profit_pct / 100)
        
        # حفظ الصفقة بمفاتيح إنجليزية لضمان ثبات الكود
        self.trade_history.append({
            'Ticker': ticker,
            'Entry': round(p['entry'], 2),
            'Exit': round(exit_p, 2),
            'Profit_%': round(profit_pct, 2),
            'Profit_USD': round(profit_usd, 2),
            'Buy_Reason': p['buy_reason'],
            'Exit_Reason': reason,
            'Time': time
        })
        positions[ticker] = {'open': False}
        self.core.register_exit(ticker, reason, time)

    def _calc_metrics(self, df_slice):
        if df_slice.empty: return {"trades": 0, "win_rate": 0, "pnl": 0, "usd": 0}
        wins = len(df_slice[df_slice['Profit_%'] > 0])
        return {
            "trades": len(df_slice),
            "win_rate": round((wins / len(df_slice)) * 100, 1),
            "pnl": round(df_slice['Profit_%'].sum(), 2),
            "usd": round(df_slice['Profit_USD'].sum(), 2)
        }

    def _print_final_report(self):
        df = pd.DataFrame(self.trade_history)
        
        # تعريب رؤوس الأعمدة للعرض فقط
        display_map = {
            'Ticker': 'السهم', 'Entry': 'دخول', 'Exit': 'خروج', 
            'Profit_%': 'ربح %', 'Profit_USD': 'ربح $',
            'Buy_Reason': 'سبب الشراء', 'Exit_Reason': 'سبب البيع', 'Time': 'الوقت'
        }

        print("\n" + "="*110)
        print("📊 تقرير صفقات المحفظة الموحد (Sovereign Engine v54.0)")
        print("="*110)
        
        if not df.empty:
            print(df.rename(columns=display_map).to_markdown(index=False))
            
            # ملخص الأسهم
            ticker_summary = []
            for t in df['Ticker'].unique():
                m = self._calc_metrics(df[df['Ticker'] == t])
                ticker_summary.append({
                    'السهم': t, 'الصفقات': m['trades'], 
                    'النجاح %': f"{m['win_rate']}%", 'الربح %': f"{m['pnl']}%",
                    'الربح $': f"${m['usd']:,.2f}"
                })
            
            print("\n" + "🔍 تحليل أداء الأسهم:")
            print(pd.DataFrame(ticker_summary).to_markdown(index=False))

            # الملخص المالي النهائي
            total_m = self._calc_metrics(df)
            print("\n" + "📈 ملخص الأداء الكلي")
            print("-" * 30)
            print(f"✅ إجمالي الصفقات  : {total_m['trades']}")
            print(f"🎯 نسبة النجاح     : {total_m['win_rate']}%")
            print(f"💰 صافي الربح ($)  : ${total_m['usd']:,.2f}")
            print(f"🚀 العائد على المحفظة: {((total_m['usd']/self.config.get('initial_capital', 100000))*100):.2f}%")
        else:
            print("⚠️ لم يتم العثور على صفقات تطابق الشروط.")
        print("="*45)
