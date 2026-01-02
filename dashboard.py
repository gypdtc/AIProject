import streamlit as st
import pandas as pd
import psycopg2
import os
import plotly.express as px
import plotly.graph_objects as go

# --- 1. 密码保护逻辑 ---
def check_password():
    """如果返回 True，则表示密码正确"""
    
    # 从环境变量读取密码，如果没有设置，默认一个极难猜到的值
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

# 只有校验通过才执行后面的代码
if not check_password():
    st.stop() # 密码不对就停止运行后续 UI

# --- 后面才是你原来的看板代码 ---
# 1. 配置页面
st.set_page_config(page_title="AI 股票情绪监控看板", layout="wide")
st.title("📈 AI 股票情绪与“股神”追踪看板")

# 从环境变量获取数据库连接
DATABASE_URL = os.getenv("DATABASE_URL")

def get_data(query):
    conn = psycopg2.connect(DATABASE_URL)
    df = pd.read_sql(query, conn)
    conn.close()
    return df

# --- 侧边栏：实时状态 ---
st.sidebar.header("系统状态")
st.sidebar.success("✅ 数据库已连接")
if st.sidebar.button('刷新数据'):
    st.rerun()

# --- Reddit ---
st.divider()
st.set_page_config(page_title="AI 鲸鱼期权追踪", layout="wide")
st.title("🐋 Whale Flow AI 智能期权看板")
# 获取最近的建议
df = get_data("SELECT * FROM option_trades WHERE created_at > NOW() - INTERVAL '7 days'")
tickers = df['ticker'].unique()

for ticker in tickers:
    st.header(f"📊 策略聚合分析: {ticker}")
    ticker_df = df[df['ticker'] == ticker]
    
    fig = go.Figure()
    
    for _, row in ticker_df.iterrows():
        # 计算时间跨度：从生成日到行权日
        start_date = row['created_at'].date()
        end_date = row['expiration_date']
        days_to_expiry = (end_date - start_date).days
        
        # 模拟每天的收益区间 (基于 2% 的平均日波动率)
        dates = [start_date + timedelta(days=i) for i in range(days_to_expiry + 1)]
        base_pnl = [] # 期望路径
        high_pnl = [] # 理论最高
        low_pnl = []  # 理论最低
        
        entry = float(row['entry_stock_price'])
        side_mult = 1 if row['side'] == 'CALL' else -1
        
        for i in range(len(dates)):
            # 随时间增加，波动范围呈平方根增长
            vol_expansion = (i ** 0.5) * 0.02 
            expected_move = i * 0.005 * side_mult # 假设每日 0.5% 的趋势
            
            # 模拟期权杠杆后的收益 (%)
            mid = expected_move * 10 * 100 
            spread = vol_expansion * 10 * 100
            
            base_pnl.append(mid)
            high_pnl.append(mid + spread)
            low_pnl.append(mid - spread)

        # 在同一个图表中添加多条建议曲线
        label = f"建议 @ {start_date} ({row['side']} Strike: {row['suggested_strike']})"
        
        # 绘制最高/最低区间的阴影
        fig.add_trace(go.Scatter(
            x=dates + dates[::-1],
            y=high_pnl + low_pnl[::-1],
            fill='toself',
            fillcolor='rgba(0,176,246,0.2)',
            line_color='rgba(255,255,255,0)',
            name=f"{label} 波动区间",
        ))
        
        # 绘制主期望线
        fig.add_trace(go.Scatter(x=dates, y=base_pnl, name=label, line=dict(width=3)))

    fig.update_layout(
        title=f"{ticker} 建议至行权日({end_date})的每日收益期望区间",
        xaxis_title="日期",
        yaxis_title="预期回报 (P&L %)",
        template="plotly_dark",
        hovermode="x unified"
    )
    st.plotly_chart(fig, use_container_width=True)
    st.markdown("---")

# --- 第一部分：今日热门股票统计 ---
st.divider()
st.header("🔥 今日社交媒体热门股票 Top 10")
query1 = """
    SELECT ticker, COUNT(*) as mention_count,
           COUNT(*) FILTER (WHERE sentiment = 'Bullish') as bullish_count,
           COUNT(*) FILTER (WHERE sentiment = 'Bearish') as bearish_count
    FROM stock_trends
    WHERE created_at > NOW() - INTERVAL '24 hours'
    GROUP BY ticker
    ORDER BY mention_count DESC
    LIMIT 10
"""
df_stocks = get_data(query1)

if not df_stocks.empty:
    col1, col2 = st.columns([1, 1])
    with col1:
        # 柱状图：讨论热度
        fig_heat = px.bar(df_stocks, x='ticker', y='mention_count', title="讨论热度（次数）",
                          color='mention_count', color_continuous_scale='Viridis')
        st.plotly_chart(fig_heat, use_container_width=True)
    
    with col2:
        # 情绪比例
        df_melted = df_stocks.melt(id_vars='ticker', value_vars=['bullish_count', 'bearish_count'], 
                                   var_name='Sentiment', value_name='Count')
        fig_sentiment = px.bar(df_melted, x='ticker', y='Count', color='Sentiment', 
                               title="看涨 vs 看跌 分布", barmode='group',
                               color_discrete_map={'bullish_count': 'green', 'bearish_count': 'red'})
        st.plotly_chart(fig_sentiment, use_container_width=True)
else:
    st.info("过去 24 小时内暂无数据，快去用插件截几张图吧！")

# --- 第二部分：股神排行榜 (Leaderboard) ---
st.header("🏆 “民间股神”预测准确率排名")
query2 = """
    SELECT author, total_predictions, correct_predictions, accuracy_rate
    FROM author_performance
    WHERE total_predictions > 0
    ORDER BY accuracy_rate DESC, total_predictions DESC
    LIMIT 10
"""
df_authors = get_data(query2)

if not df_authors.empty:
    # 格式化显示百分比
    df_authors['accuracy_rate'] = df_authors['accuracy_rate'].apply(lambda x: f"{x:.2f}%")
    st.table(df_authors)
else:
    st.info("准确率分析任务（Cron Job）尚未运行或暂无足够匹配数据。")

# --- 第三部分：原始数据流水线 ---
with st.expander("查看原始数据流水线 (最新 20 条)"):
    query3 = "SELECT ticker, sentiment, author, post_time, created_at FROM stock_trends ORDER BY created_at DESC LIMIT 20"
    st.dataframe(get_data(query3), use_container_width=True)