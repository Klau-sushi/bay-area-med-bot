import streamlit as st
import pandas as pd
from openai import OpenAI
import os
import folium
from streamlit_folium import st_folium

# -----------------------------------------------------------------------------
# 1. 页面配置 & 数据初始化
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="湾区跨境医疗AI助手", 
    page_icon="🏥", 
    layout="wide", 
    initial_sidebar_state="expanded" 
)

# 定义网络头像地址
AVATAR_BOT = "https://img.icons8.com/color/96/robot-2.png"   # 医疗机器人头像
AVATAR_USER = "https://img.icons8.com/color/96/user-male-circle--v1.png" # 中性用户头像

# -----------------------------------------------------------------------------
# 2. 数据加载 (适配你的真实 CSV 结构)
# -----------------------------------------------------------------------------
@st.cache_data
def load_data_hybrid():
    """
    直接读取 GitHub/本地 的 CSV 文件。
    并进行关键的数据清洗，确保列名匹配。
    """
    try:
        # 读取 CSV 文件
        df = pd.read_csv("shenzhen_poi_enriched.csv")
        
        # --- 关键修复：列名与数据清洗 ---
        # 1. 确保经纬度列名正确 (CSV是 latitude/longitude -> 代码需要 lat/lon)
        if 'latitude' in df.columns and 'longitude' in df.columns:
            df = df.rename(columns={'latitude': 'lat', 'longitude': 'lon'})
            
        # 2. 确保'类型'列存在 (CSV是 type: 'Policy_Designated' -> 代码需要中文 '类型')
        if '类型' not in df.columns and 'type' in df.columns:
            def map_type(val):
                val = str(val)
                if 'Policy_Designated' in val: return '港澳药械通'
                if 'Tier_A_Only' in val: return '公立三甲'
                return '私立/诊所' # 兜底
            df['类型'] = df['type'].apply(map_type)
        elif '类型' not in df.columns:
             # 如果既没有'类型'也没有'type'，给个默认值防止报错
             df['类型'] = '未知'

        # 3. 自动补全颜色列
        if 'color' not in df.columns:
            def get_color(type_str):
                if pd.isna(type_str): return '#00FF00'
                if '港澳' in type_str or '药械通' in type_str: return '#FF0000' # 红
                if '三甲' in type_str: return '#0000FF' # 蓝
                return '#00FF00' # 绿
            df['color'] = df['类型'].apply(get_color)
            
        return df
        
    except FileNotFoundError:
        st.error("❌ 错误：找不到 'shenzhen_poi_enriched.csv' 文件。请确保该文件已上传到 GitHub 仓库的根目录。")
        return pd.DataFrame() # 返回空表
    except Exception as e:
        st.error(f"❌ 数据加载发生未知错误: {e}")
        return pd.DataFrame()

df = load_data_hybrid()

# -----------------------------------------------------------------------------
# 3. 侧边栏 & 主题配色设置
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("🎨 界面设置")
    theme = st.selectbox("选择主题", ["默认 (微信风)", "护眼 (柔和绿)", "夜间 (深邃黑)"])
    
    st.markdown("---")
    st.markdown("#### 关于助手")
    st.info("本助手旨在为湾区居民提供跨境医疗指引。")

# 根据选择的主题定义 CSS 变量
if theme == "默认 (微信风)":
    bg_color = "#F5F5F5"
    chat_bg = "#FFFFFF"
    text_color = "#000000"
    input_border = "#E0E0E0"
elif theme == "护眼 (柔和绿)":
    bg_color = "#F0F9EB"
    chat_bg = "#FFFFFF"
    text_color = "#2E4033"
    input_border = "#C6E0C4"
else: # 夜间模式
    bg_color = "#1E1E1E"
    chat_bg = "#2D2D2D"
    text_color = "#E0E0E0"
    input_border = "#444444"

# 注入动态 CSS
st.markdown(f"""
<style>
    .stApp {{ background-color: {bg_color}; color: {text_color}; }}
    .chat-container {{
        background-color: {chat_bg};
        border-radius: 15px;
        padding: 20px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        border: 1px solid {input_border};
    }}
    iframe[title="streamlit.map"] {{ height: 450px !important; border-radius: 12px; }}
    .stChatInputContainer {{ padding-bottom: 20px; }}
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 4. 核心逻辑：对话筛选
# -----------------------------------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []

user_query = ""
if len(st.session_state.messages) > 0:
    last_msg = st.session_state.messages[-1]
    if last_msg["role"] == "user":
        user_query = last_msg["content"]

filtered_data = df.copy()
filter_tips = "" 

if not filtered_data.empty and user_query:
    if "三甲" in user_query:
        filter_tips = "🔵 已筛选：三甲医院"
        filtered_data = filtered_data[filtered_data['类型'].str.contains('三甲', na=False)]
    elif "港澳" in user_query or "药械通" in user_query:
        filter_tips = "🔴 已筛选：港澳指定医院"
        filtered_data = filtered_data[filtered_data['类型'].str.contains('港澳|药械通', na=False, regex=True)]
    elif "私立" in user_query or "诊所" in user_query:
        filter_tips = "🟢 已筛选：私立/诊所"
        filtered_data = filtered_data[filtered_data['类型'].str.contains('私立|诊所', na=False, regex=True)]

# -----------------------------------------------------------------------------
# 5. 页面布局
# -----------------------------------------------------------------------------

st.title("🏥 湾区跨境医疗 AI 助手")
st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

col_left, col_right = st.columns([2, 3], gap="large")

# === 左侧：地图 ===
with col_left:
    st.markdown("### 🗺️ 医疗资源分布")
    
    if filter_tips:
        st.info(filter_tips, icon="🔍")
    
    st.markdown(f"""
    <div style="display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 10px; color: {text_color}; opacity: 0.8;">
        <span>🔴 港澳/药械通</span>
        <span>🔵 公立三甲</span>
        <span>🟢 私立/诊所</span>
    </div>
    """, unsafe_allow_html=True)

    # 地图展示 (使用你指定的逻辑)
    if not filtered_data.empty:
        # 注意：这里我们明确使用 'lat' 和 'lon'，因为上面 load_data_hybrid 已经完成了列名重命名
        st.map(filtered_data, latitude='lat', longitude='lon', size=30, color='color', zoom=11)
    else:
        st.warning("数据加载失败或筛选结果为空")

# === 右侧：AI 对话 ===
with col_right:
    st.markdown("### 🤖 智能咨询顾问")
    
    chat_container = st.container()
    
    with chat_container:
        st.markdown('<div class="chat-container">', unsafe_allow_html=True)
        
        if len(st.session_state.messages) == 0:
            with st.chat_message("assistant", avatar=AVATAR_BOT):
                st.markdown("您好！我是您的跨境医疗助手。您可以问我：\n\n* “附近的**港大深圳医院**在哪里？”\n* “我想找一家能用**长者医疗券**的牙科。”")

        for message in st.session_state.messages:
            current_avatar = AVATAR_USER if message["role"] == "user" else AVATAR_BOT
            with st.chat_message(message["role"], avatar=current_avatar):
                st.markdown(message["content"])
        
        st.markdown('</div>', unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 6. 底部输入与回复
# -----------------------------------------------------------------------------

if prompt := st.chat_input("请输入您的问题... (按回车发送)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.rerun()

if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    with col_right:
        with st.chat_message("assistant", avatar=AVATAR_BOT):
            with st.spinner("正在检索医疗数据库..."):
                last_msg = st.session_state.messages[-1]["content"]
                
                # --- 简单回复逻辑 ---
                response_text = f"收到，关于“{last_msg}”：\n\n我已经为您更新了左侧地图。如果您正在寻找医疗机构，请参考左侧地图上的红点（港澳指定）或蓝点（三甲医院）。"
                
                st.markdown(response_text)
                st.session_state.messages.append({"role": "assistant", "content": response_text})




