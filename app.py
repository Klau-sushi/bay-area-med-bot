import streamlit as st
import pandas as pd
from openai import OpenAI
import os
import folium
from streamlit_folium import st_folium

# -----------------------------------------------------------------------------
# 1. 页面配置 & CSS 美化 (微信风格主题)
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="湾区跨境医疗AI助手", 
    page_icon="🏥", 
    layout="wide", 
    initial_sidebar_state="collapsed"
)

# 注入自定义 CSS 样式
st.markdown("""
<style>
    /* 1. 全局背景颜色 - 类似微信的浅灰色 */
    .stApp {
        background-color: #F5F5F5;
    }
    
    /* 2. 调整地图的高度，防止它太长 */
    iframe[title="streamlit.map"] {
        height: 400px !important;
    }

    /* 3. 给右侧对话区加一个白色卡片背景，让它更聚光 */
    .chat-container {
        background-color: white;
        border-radius: 15px;
        padding: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. 数据加载
# -----------------------------------------------------------------------------
@st.cache_data
def load_data_hybrid():
    try:
        df = pd.read_csv("shenzhen_poi_enriched.csv")
        # 自动补全颜色列
        if 'color' not in df.columns:
            def get_color(type_str):
                if pd.isna(type_str): return '#00FF00'
                if '港澳' in type_str or '药械通' in type_str: return '#FF0000' # 红
                if '三甲' in type_str: return '#0000FF' # 蓝
                return '#00FF00' # 绿
            df['color'] = df['类型'].apply(get_color)
        return df
    except Exception as e:
        # 如果报错，返回一个空的 DataFrame 防止崩溃
        return pd.DataFrame(columns=['lat', 'lon', '类型', 'color'])

df = load_data_hybrid()

# -----------------------------------------------------------------------------
# 3. 核心逻辑：获取对话历史并筛选数据
# -----------------------------------------------------------------------------

# 初始化聊天记录
if "messages" not in st.session_state:
    st.session_state.messages = []

# 获取用户最近一次提问 (用于控制地图)
user_query = ""
if len(st.session_state.messages) > 0:
    last_msg = st.session_state.messages[-1]
    if last_msg["role"] == "user":
        user_query = last_msg["content"]

# 筛选数据
filtered_data = df.copy()
filter_tips = "" # 用于在界面提示筛选状态

if not filtered_data.empty and user_query:
    if "三甲" in user_query:
        filter_tips = "🔵 已筛选：三甲医院"
        filtered_data = filtered_data[filtered_data['类型'].str.contains('三甲', na=False)]
    elif "港澳" in user_query or "药械通" in user_query or "医疗券" in user_query:
        filter_tips = "🔴 已筛选：港澳指定医院"
        filtered_data = filtered_data[filtered_data['类型'].str.contains('港澳', na=False)]
    elif "私立" in user_query or "诊所" in user_query:
        filter_tips = "🟢 已筛选：私立/诊所"
        filtered_data = filtered_data[filtered_data['类型'].str.contains('私立', na=False)]

# -----------------------------------------------------------------------------
# 4. 页面布局 (左右分栏：左地图，右对话)
# -----------------------------------------------------------------------------

st.title("🏥 湾区跨境医疗 AI 助手")
st.markdown("---")

# 创建两列：左侧占 2/5 (40%)，右侧占 3/5 (60%)
col_left, col_right = st.columns([2, 3], gap="large")

# === 左侧：地图与图例 ===
with col_left:
    st.markdown("### 🗺️ 医疗资源分布")
    
    # 如果有筛选状态，显示一个小提示
    if filter_tips:
        st.info(filter_tips)
    
    # 图例 (改用更紧凑的显示方式)
    st.markdown("""
    <div style="display: flex; justify-content: space-between; font-size: 14px; margin-bottom: 10px;">
        <span>🔴 港澳指定</span>
        <span>🔵 公立三甲</span>
        <span>🟢 私立/诊所</span>
    </div>
    """, unsafe_allow_html=True)

    # 地图展示
    if not filtered_data.empty:
        st.map(filtered_data, latitude='lat', longitude='lon', size=25, color='color')
    else:
        st.warning("数据加载失败或筛选结果为空")

# === 右侧：AI 咨询对话框 ===
with col_right:
    st.markdown("### 🤖 智能咨询顾问")
    
    # 创建一个容器来包裹聊天记录
    chat_container = st.container()
    
    with chat_container:
        # 显示历史消息
        # 如果没有消息，显示欢迎语
        if len(st.session_state.messages) == 0:
            st.chat_message("assistant", avatar="👩‍⚕️").markdown("您好！我是您的跨境医疗助手。您可以问我：\n- 附近的**三甲医院**在哪里？\n- **港大深圳医院**怎么走？\n- 哪里可以用**长者医疗券**？")

        for message in st.session_state.messages:
            # 设置头像：用户用🧑‍💻，AI用👩‍⚕️
            avatar = "🧑‍💻" if message["role"] == "user" else "👩‍⚕️"
            with st.chat_message(message["role"], avatar=avatar):
                st.markdown(message["content"])

# -----------------------------------------------------------------------------
# 5. 底部输入框 (全局固定)
# -----------------------------------------------------------------------------
# st.chat_input 默认固定在页面底部，支持回车发送
if prompt := st.chat_input("请输入您的问题... (按回车发送)"):
    # 1. 记录用户输入
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # 2. 强制刷新 (为了让新消息立即显示在上面，并触发左侧地图更新)
    st.rerun()

# -----------------------------------------------------------------------------
# 6. 处理 AI 回复 (在刷新后执行)
# -----------------------------------------------------------------------------
# 检查最后一条消息是不是用户的，如果是，AI 需要回复
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    with col_right: # 确保 AI 回复显示在右侧栏
        with st.chat_message("assistant", avatar="👩‍⚕️"):
            # 模拟 AI 思考过程
            with st.spinner("正在查询医疗政策库..."):
                last_user_msg = st.session_state.messages[-1]["content"]
                
                # 这里替换成你的真实 LLM 逻辑
                response_text = f"收到！关于“{last_user_msg}”，我已经为您更新了左侧地图数据。建议您查看地图上的高亮区域。"
                
                st.markdown(response_text)
                
                # 将 AI 回复存入历史
                st.session_state.messages.append({"role": "assistant", "content": response_text})
















