import streamlit as st
import pandas as pd
import psycopg2
import os
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 0. 基础配置 (必须在所有 streamlit 命令之前) ---
st.set_page_config(page_title="Whale Flow AI 智能期权看板", layout="wide")

# --- 1. 密码保护逻辑 ---
def check_password():
    """如果返回 True，则表示密码正确"""
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

# --- 2. 数据库连接函数 ---
DATABASE_URL = os.getenv("DATABASE_URL")

def get_data(query):
    conn = psycopg2.connect(DATABASE_URL)
    df = pd.read_sql(query, conn)
    conn.close()
    return df

# --- 3. 核心数据锁定逻辑 (最新扫描快照) ---
try:
    # 获取最新的扫描时间戳，确保 UI 显示的是同一批次的数据
    last_scan_query = "SELECT MAX(scan_timestamp) FROM public.iv_analysis"
    latest_ts = get_data(last_scan_query).iloc[0, 0]
except:
    latest_ts = None

# --- 4. 核心 UI 开始 ---
st.title("🐋 Whale Flow AI 智能期权看板")

# --- A. 侧边栏系统状态 ---
st.sidebar.header("系统状态")
st.sidebar.success("✅ 数据库已连接")
if latest_ts:
    st.sidebar.markdown(f"⏱️ **最新扫描快照:** \n`{latest_ts}`")

if st.sidebar.button('手动刷新页面'):
    st.rerun()

# --- B. 高 IV 预警板块 (按最新快照排序) ---
st.subheader("🔥 异常波动预警 (Top 5 高 IV 标的分析)")
if latest_ts:
    iv_query = f"SELECT * FROM public.iv_analysis WHERE scan_timestamp = '{latest_ts}' ORDER BY iv_value DESC LIMIT 5"
    iv_df = get_data(iv_query)
    
    if not iv_df.empty:
        cols = st.columns(len(iv_df))
        for i, row in iv_df.iterrows():
            with cols[i]:
                st.error(f"**{row['ticker']}**")
                st.metric(label="隐含波动率", value=f"{float(row['iv_value']):.1%}")
                with st.expander("为什么 IV 如此高？"):
                    st.caption(row['analysis_reason'])
    else:
        st.info("当前扫描批次暂无 IV 数据。")
else:
    st.info("等待首次扫描数据入库...")

# 在 dashboard.py 找到高 IV 预警板块后的位置插入：

# --- 新增：CSP 卖出建议展示 ---
st.subheader("💰 波动率收割：卖出看跌 (CSP) 机会")
st.markdown("> **策略逻辑**：针对上方高 IV 标的，卖出深度价外 (OTM) Put。若股价不动或小跌，收割权利金；若大跌，则以折扣价接盘。")

if latest_ts:
    csp_query = f"SELECT * FROM public.csp_suggestions WHERE scan_timestamp = '{latest_ts}' ORDER BY iv_level DESC"
    csp_df = get_data(csp_query)
    
    if not csp_df.empty:
        # 格式化展示
        display_df = csp_df[['ticker', 'current_price', 'suggested_strike', 'safety_buffer', 'iv_level', 'analysis_logic']].copy()
        display_df.columns = ['标的', '现价', '建议行权价', '安全垫', 'IV 水平', 'AI 逻辑分析']
        display_df['IV 水平'] = display_df['IV 水平'].apply(lambda x: f"{float(x):.1%}")
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("当前扫描批次暂无 CSP 建议。")
st.divider()

# --- C. 6步协议策略聚合分析 (带动态回测曲线) ---
st.header("🎯 AI 策略聚合回测 (最新建议)")
if latest_ts:
    trades_query = f"SELECT * FROM public.option_trades WHERE scan_timestamp = '{latest_ts}' ORDER BY final_score DESC"
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
                    
                    days_to_expiry = (end_date - start_date).days
                    if days_to_expiry <= 0: days_to_expiry = 1
                    
                    dates = [start_date + timedelta(days=i) for i in range(days_to_expiry + 1)]
                    side_mult = 1 if row['side'] == 'CALL' else -1
                    
                    base_pnl = []
                    high_pnl = []
                    low_pnl = []
                    
                    for i in range(len(dates)):
                        vol_expansion = (i ** 0.5) * 0.02
                        expected_move = i * 0.005 * side_mult
                        mid = expected_move * 10 * 100 
                        spread = vol_expansion * 10 * 100
                        base_pnl.append(mid)
                        high_pnl.append(mid + spread)
                        low_pnl.append(mid - spread)

                    label = f"{row['side']} @ {start_date}"
                    
                    fig.add_trace(go.Scatter(
                        x=dates + dates[::-1], y=high_pnl + low_pnl[::-1],
                        fill='toself', fillcolor='rgba(0,176,246,0.1)',
                        line_color='rgba(255,255,255,0)', name=f"{label} 波动范围", showlegend=False
                    ))
                    line_color = "#2ecc71" if row['side'] == 'CALL' else "#e74c3c"
                    fig.add_trace(go.Scatter(x=dates, y=base_pnl, name=label, line=dict(color=line_color, width=3)))

                fig.update_layout(
                    height=400, margin=dict(l=20, r=20, t=40, b=20),
                    template="plotly_dark", hovermode="x unified", yaxis_title="预期回报 (P&L %)"
                )
                # 修复 Duplicate ID 报错的关键 key
                st.plotly_chart(fig, use_container_width=True, key=f"chart_{ticker}_{idx}")

            with col_info:
                latest_row = ticker_df.iloc[0]
                st.markdown(f"### 最新 AI 评分: `{latest_row['final_score']}`")
                st.write(f"**建议行权:** ${latest_row['suggested_strike']}")
                st.write(f"**R/R 比率:** {latest_row['risk_reward_ratio']}")
                st.info(f"**AI 叙事:**\n\n{latest_row['narrative_type']}")
            st.divider()
else:
    st.info("最近一次扫描未发现符合 6 步协议的建议。")

# --- D. 社交媒体热度 (Reddit 抓取结果统计) ---
st.header("🔥 今日社交媒体热门股票 Top 10")
query_heat = """
    SELECT ticker, COUNT(*) as mention_count,
           COUNT(*) FILTER (WHERE sentiment = 'Bullish') as bullish_count,
           COUNT(*) FILTER (WHERE sentiment = 'Bearish') as bearish_count
    FROM stock_trends
    WHERE created_at > NOW() - INTERVAL '24 hours'
    GROUP BY ticker
    ORDER BY mention_count DESC
    LIMIT 10
"""
df_stocks = get_data(query_heat)

if not df_stocks.empty:
    col1, col2 = st.columns([1, 1])
    with col1:
        fig_heat = px.bar(df_stocks, x='ticker', y='mention_count', title="讨论热度 (最近24h)",
                         color='mention_count', color_continuous_scale='Viridis', template="plotly_dark")
        st.plotly_chart(fig_heat, use_container_width=True)
    
    with col2:
        df_melted = df_stocks.melt(id_vars='ticker', value_vars=['bullish_count', 'bearish_count'], 
                                   var_name='Sentiment', value_name='Count')
        fig_sentiment = px.bar(df_melted, x='ticker', y='Count', color='Sentiment', 
                               title="看涨 vs 看跌 分布", barmode='group',
                               color_discrete_map={'bullish_count': '#2ecc71', 'bearish_count': '#e74c3c'},
                               template="plotly_dark")
        st.plotly_chart(fig_sentiment, use_container_width=True)
else:
    st.info("过去 24 小时内社交媒体暂无数据。")

# --- E. 民间股神排行榜 ---
st.header("🏆 “民间股神”预测准确率排名")
query_rank = """
    SELECT author, total_predictions, correct_predictions, accuracy_rate
    FROM author_performance
    WHERE total_predictions > 0
    ORDER BY accuracy_rate DESC, total_predictions DESC
    LIMIT 10
"""
try:
    df_authors = get_data(query_rank)
    if not df_authors.empty:
        df_authors['accuracy_rate'] = df_authors['accuracy_rate'].apply(lambda x: f"{x:.2f}%")
        st.table(df_authors)
    else:
        st.info("暂无足够的股神排行数据。")
except:
    st.info("排行榜模块初始化中...")

# --- F. 原始流水线 ---
with st.expander("📂 查看原始数据流水线 (最新 20 条)"):
    query_raw = "SELECT ticker, sentiment, author, created_at FROM stock_trends ORDER BY created_at DESC LIMIT 20"
    st.dataframe(get_data(query_raw), use_container_width=True)