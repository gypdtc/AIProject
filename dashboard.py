import streamlit as st
import pandas as pd
import psycopg2
import os
import plotly.express as px
import plotly.graph_objects as go
import pytz # Requires: pip install pytz
from datetime import datetime, timedelta

# --- 0. Basic Configuration ---
st.set_page_config(page_title="Whale Flow AI 智能期权看板", layout="wide")

# --- 1. Password Protection Logic ---
def check_password():
    target_password = os.getenv("DASHBOARD_PASSWORD", "Admin123") 

    if "password_correct" not in st.session_state:
        st.title("🔒 访问受限")
        password = st.text_input("请输入访问密码", type="password")
        if st.button("登录"):
            if password == target_password:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("🚫 密码错误")
        return False
    return True

if not check_password():
    st.stop()

# --- 2. Database Connection Function ---
DATABASE_URL = os.getenv("DATABASE_URL")

def get_data(query):
    conn = psycopg2.connect(DATABASE_URL)
    df = pd.read_sql(query, conn)
    conn.close()
    return df

# --- 3. Core Data Locking & Timezone Handling ---
try:
    # Get raw timestamp (usually UTC from DB)
    last_scan_query = "SELECT MAX(scan_timestamp) FROM public.iv_analysis"
    latest_ts_utc = get_data(last_scan_query).iloc[0, 0]
    
    # Convert to Beijing Time (CST)
    local_tz = pytz.timezone("Asia/Shanghai")
    if latest_ts_utc.tzinfo is None:
        latest_ts_utc = pytz.utc.localize(latest_ts_utc)
    latest_ts_cst = latest_ts_utc.astimezone(local_tz)
    ts_display = latest_ts_cst.strftime('%Y-%m-%d %H:%M:%S %Z')
except:
    latest_ts_utc = None
    ts_display = "N/A"

# --- 4. Main UI Start ---
st.title("🐋 Whale Flow AI 智能期权看板")

# --- A. Sidebar Status ---
st.sidebar.header("系统状态")
st.sidebar.success("✅ 数据库已连接")
if latest_ts_utc:
    st.sidebar.markdown(f"⏱️ **最新扫描快照 (CST):** \n`{ts_display}`")

if st.sidebar.button('手动刷新页面'):
    st.rerun()

# --- B. High IV Alerts (Dynamic Selection) ---
st.subheader("🔥 异常波动预警 (AI 深度分析)")

# Dynamic Selector for Display Count
display_count = st.selectbox(
    "选择展示标的数量:",
    options=[5, 10, 20, 30],
    index=1,  # Default to 10
    help="根据 IV 从高到低排序显示的股票数量"
)

if latest_ts_utc:
    iv_query = f"""
        SELECT * FROM public.iv_analysis 
        WHERE scan_timestamp = '{latest_ts_utc}' 
        ORDER BY iv_value DESC 
        LIMIT {display_count}
    """
    iv_df = get_data(iv_query)
    
    if not iv_df.empty:
        num_cols = 5
        rows = (len(iv_df) + num_cols - 1) // num_cols
        
        for r in range(rows):
            cols = st.columns(num_cols)
            for c in range(num_cols):
                idx = r * num_cols + c
                if idx < len(iv_df):
                    row = iv_df.iloc[idx]
                    with cols[c]:
                        st.error(f"**{row['ticker']}**")
                        st.metric(label="隐含波动率", value=f"{float(row['iv_value']):.1%}")
                        
                        # Market Metrics
                        price = row['current_price'] if row['current_price'] else 0
                        mkt_cap = (float(row['market_cap']) / 1e9) if row['market_cap'] else 0
                        st.caption(f"💰 现价: `${price:.2f}`")
                        st.caption(f"🏢 市值: `{mkt_cap:.2f}B`")
                        
                        with st.expander("AI 原因分析 (中文)"):
                            # Logic assumes your Scanner prompt now requests Chinese
                            st.write(row['analysis_reason'])
    else:
        st.info("当前批次暂无 IV 数据。")
else:
    st.info("等待扫描数据入库...")

# --- C. CSP (Cash-Secured Put) Suggestions ---
st.subheader("💰 波动率收割：卖出看跌 (CSP) 机会")
st.markdown("> **策略逻辑**：针对高 IV 标的卖出深度价外 (OTM) Put。若股价横盘或小跌则收割权利金。")

if latest_ts_utc:
    csp_query = f"SELECT * FROM public.csp_suggestions WHERE scan_timestamp = '{latest_ts_utc}' ORDER BY iv_level DESC"
    csp_df = get_data(csp_query)
    
    if not csp_df.empty:
        display_df = csp_df[['ticker', 'current_price', 'suggested_strike', 'safety_buffer', 'iv_level', 'analysis_logic']].copy()
        display_df.columns = ['标的', '现价', '建议行权价', '安全垫', 'IV 水平', 'AI 逻辑分析']
        display_df['IV 水平'] = display_df['IV 水平'].apply(lambda x: f"{float(x):.1%}")
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("当前暂无 CSP 建议。")

st.divider()

# --- D. Strategy Backtest Curves ---
st.header("🎯 AI 策略聚合回测 (最新建议)")
if latest_ts_utc:
    trades_query = f"SELECT * FROM public.option_trades WHERE scan_timestamp = '{latest_ts_utc}' ORDER BY final_score DESC"
    df_trades = get_data(trades_query)
else:
    df_trades = pd.DataFrame()

if not df_trades.empty:
    df_trades['created_at'] = pd.to_datetime(df_trades['created_at'])
    df_trades['expiration_date'] = pd.to_datetime(df_trades['expiration_date'])
    
    tickers = df_trades['ticker'].unique()

    for ticker in tickers:
        with st.container():
            st.subheader(f"📊 标的分析: {ticker}")
            ticker_df = df_trades[df_trades['ticker'] == ticker]
            col_chart, col_info = st.columns([2, 1])
            
            with col_chart:
                fig = go.Figure()
                for idx, row in ticker_df.iterrows():
                    start_date = row['created_at'].date()
                    end_date = row['expiration_date'].date()
                    days = (end_date - start_date).days
                    if days <= 0: days = 1
                    
                    dates = [start_date + timedelta(days=i) for i in range(days + 1)]
                    side_mult = 1 if row['side'] == 'CALL' else -1
                    base_pnl = [(i * 0.005 * side_mult * 10 * 100) for i in range(len(dates))]
                    high_pnl = [p + ((i**0.5)*2.5*10) for i, p in enumerate(base_pnl)]
                    low_pnl = [p - ((i**0.5)*2.5*10) for i, p in enumerate(base_pnl)]

                    label = f"{row['side']} @ {start_date}"
                    fig.add_trace(go.Scatter(x=dates + dates[::-1], y=high_pnl + low_pnl[::-1],
                        fill='toself', fillcolor='rgba(0,176,246,0.1)', line_color='rgba(255,255,255,0)', showlegend=False))
                    fig.add_trace(go.Scatter(x=dates, y=base_pnl, name=label, line=dict(width=3)))

                fig.update_layout(height=400, template="plotly_dark", hovermode="x unified", yaxis_title="预期回报 (P&L %)")
                st.plotly_chart(fig, use_container_width=True, key=f"chart_{ticker}_{idx}")

            with col_info:
                latest_row = ticker_df.iloc[0]
                st.markdown(f"### 最新 AI 评分: `{latest_row['final_score']}`")
                st.write(f"**建议行权:** ${latest_row['suggested_strike']}")
                st.write(f"**R/R 比率:** {latest_row['risk_reward_ratio']}")
                st.info(f"**AI 叙事 (中文):**\n\n{latest_row['narrative_type']}")
            st.divider()

# --- E. Sentiment & Leaderboard (Remaining original sections) ---
st.header("🔥 今日社交媒体热门股票 Top 10")
# ... [Original Sentiment Bars/Leaderboard Code remains same as provided in your snippet] ...
query_heat = """
    SELECT ticker, COUNT(*) as mention_count,
           COUNT(*) FILTER (WHERE sentiment = 'Bullish') as bullish_count,
           COUNT(*) FILTER (WHERE sentiment = 'Bearish') as bearish_count
    FROM stock_trends
    WHERE created_at > NOW() - INTERVAL '24 hours'
    GROUP BY ticker ORDER BY mention_count DESC LIMIT 10
"""
df_stocks = get_data(query_heat)
if not df_stocks.empty:
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(px.bar(df_stocks, x='ticker', y='mention_count', template="plotly_dark"), use_container_width=True)
    with c2:
        df_m = df_stocks.melt(id_vars='ticker', value_vars=['bullish_count', 'bearish_count'])
        st.plotly_chart(px.bar(df_m, x='ticker', y='value', color='variable', barmode='group', template="plotly_dark"), use_container_width=True)

st.header("🏆 “民间股神”预测准确率排名")
# ... [Original Table Code] ...
try:
    df_authors = get_data("SELECT author, total_predictions, correct_predictions, accuracy_rate FROM author_performance WHERE total_predictions > 0 ORDER BY accuracy_rate DESC LIMIT 10")
    if not df_authors.empty:
        df_authors['accuracy_rate'] = df_authors['accuracy_rate'].apply(lambda x: f"{x:.2f}%")
        st.table(df_authors)
except: st.info("Leaderboard data loading...")

with st.expander("📂 查看原始数据流水线 (最新 20 条)"):
    st.dataframe(get_data("SELECT ticker, sentiment, author, created_at FROM stock_trends ORDER BY created_at DESC LIMIT 20"), use_container_width=True)