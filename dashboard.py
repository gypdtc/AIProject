import streamlit as st
import pandas as pd
import psycopg2
import os
import plotly.express as px

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
st.header("🐋 Whale Flow 高质量期权异动 (6步量化协议)")
st.caption("基于昨日收盘数据、20日均线趋势、IV估值及 Gemini 叙事检查")
query_options = "SELECT * FROM option_trades ORDER BY final_score DESC LIMIT 5"
df_options = get_data(query_options)

if not df_options.empty:
    for _, row in df_options.iterrows():
        with st.expander(f"🎯 {row['ticker']} - 综合评分: {row['final_score']}"):
            col1, col2, col3 = st.columns(3)
            col1.metric("叙事类型", row['narrative_type'])
            col2.metric("情感分", row['sentiment_score'])
            col3.metric("盈亏比", f"{row['risk_reward_ratio']}x")
            st.write(f"建议策略：买入代码 {row['ticker']}， strike 调整至当前价 2% 以内，到期日延长 14 天。")
else:
    st.info("尚未发现符合 6 步过滤协议的期权机会。")

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