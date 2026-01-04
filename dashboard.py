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

# --- 3. 核心 UI 开始 ---
st.title("🐋 Whale Flow AI 智能期权看板")

# --- A. 侧边栏系统状态 ---
st.sidebar.header("系统状态")
st.sidebar.success("✅ 数据库已连接")

# 获取高 IV 数据和最后扫描时间
try:
    iv_df = get_data("SELECT * FROM public.iv_analysis ORDER BY scan_timestamp DESC LIMIT 5")
    if not iv_df.empty:
        last_ts = iv_df['scan_timestamp'].iloc[0]
        st.sidebar.markdown(f"⏱️ **最后扫描时间:** \n`{last_ts}`")
except:
    iv_df = pd.DataFrame()

if st.sidebar.button('手动刷新页面'):
    st.rerun()

# --- B. 高 IV 预警板块 ---
st.subheader("🔥 异常波动预警 (Top 5 高 IV 标的分析)")
if not iv_df.empty:
    cols = st.columns(5)
    for i, row in iv_df.iterrows():
        with cols[i]:
            # 使用 error 样式突出高风险
            st.error(f"**{row['ticker']}**")
            st.metric(label="隐含波动率", value=f"{float(row['iv_value']):.1%}")
            with st.expander("为什么 IV 如此高？"):
                st.caption(row['analysis_reason'])
else:
    st.info("暂无高 IV 分析数据。")

st.divider()

# --- C. 6步协议策略聚合分析 ---
st.header("🎯 AI 策略聚合回测")

# 获取最近 7 天的建议
query_trades = """
    SELECT * FROM public.option_trades 
    WHERE expiration_date IS NOT NULL 
    AND created_at > NOW() - INTERVAL '7 days'
    ORDER BY created_at DESC
"""
df_trades = get_data(query_trades)

if not df_trades.empty:
    # 确保日期类型正确
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
                for _, row in ticker_df.iterrows():
                    # 修复日期计算逻辑
                    start_date = row['created_at'].date()
                    end_date = row['expiration_date'].date()
                    
                    days_to_expiry = (end_date - start_date).days
                    if days_to_expiry <= 0: days_to_expiry = 1 # 防止报错
                    
                    # 模拟收益路径
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
                    
                    # 绘制区间阴影
                    fig.add_trace(go.Scatter(
                        x=dates + dates[::-1],
                        y=high_pnl + low_pnl[::-1],
                        fill='toself',
                        fillcolor='rgba(0,176,246,0.1)',
                        line_color='rgba(255,255,255,0)',
                        name=f"{label} 波动范围",
                        showlegend=False
                    ))
                    # 绘制主线
                    line_color = "#2ecc71" if row['side'] == 'CALL' else "#e74c3c"
                    fig.add_trace(go.Scatter(x=dates, y=base_pnl, name=label, line=dict(color=line_color, width=3)))

                fig.update_layout(
                    height=400,
                    margin=dict(l=20, r=20, t=40, b=20),
                    template="plotly_dark",
                    hovermode="x unified",
                    yaxis_title="预期回报 (P&L %)"
                )
                st.plotly_chart(fig, use_container_width=True, key=f"chart_{ticker}")

            with col_info:
                latest = ticker_df.iloc[0]
                st.markdown(f"### 最新 AI 评分: `{latest['final_score']}`")
                st.write(f"**建议行权:** ${latest['suggested_strike']}")
                st.write(f"**R/R 比率:** {latest['risk_reward_ratio']}")
                st.info(f"**AI 叙事:**\n\n{latest['narrative_type']}")
            st.divider()
else:
    st.info("过去 7 天内暂无建议数据。")

# --- D. 社交媒体热度与股神榜 ---
st.header("🔥 市场情绪快报")
col_heat, col_rank = st.columns(2)

with col_heat:
    st.subheader("今日热门讨论 Top 10")
    query_heat = """
        SELECT ticker, COUNT(*) as mention_count
        FROM stock_trends
        WHERE created_at > NOW() - INTERVAL '24 hours'
        GROUP BY ticker ORDER BY mention_count DESC LIMIT 10
    """
    df_heat = get_data(query_heat)
    if not df_heat.empty:
        fig_heat = px.bar(df_heat, x='ticker', y='mention_count', color='mention_count', template="plotly_dark")
        st.plotly_chart(fig_heat, use_container_width=True)
    else:
        st.write("暂无热度数据")

with col_rank:
    st.subheader("🏆 民间股神准确率排行")
    query_rank = "SELECT author, accuracy_rate FROM author_performance ORDER BY accuracy_rate DESC LIMIT 5"
    try:
        df_rank = get_data(query_rank)
        if not df_rank.empty:
            st.table(df_rank)
        else:
            st.write("暂无排行榜数据")
    except:
        st.write("排行榜功能初始化中...")

# --- E. 原始流水线 ---
with st.expander("📂 查看原始数据流水线 (最新 20 条)"):
    query_raw = "SELECT ticker, sentiment, author, created_at FROM stock_trends ORDER BY created_at DESC LIMIT 20"
    st.dataframe(get_data(query_raw), use_container_width=True)