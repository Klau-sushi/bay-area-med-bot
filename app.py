import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
from openai import OpenAI
import os

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
AVATAR_BOT = "https://img.icons8.com/fluency/96/bot.png" 
AVATAR_USER = "https://img.icons8.com/color/96/user-male-circle--v1.png"

# -----------------------------------------------------------------------------
# 2. 数据加载 (适配你的真实 CSV 结构)
# -----------------------------------------------------------------------------
@st.cache_data
def load_data_hybrid():
    """
    直接读取 GitHub/本地 的 CSV 文件。
    并进行关键的数据清洗。
    """
    try:
        # 读取 CSV 文件
        df = pd.read_csv("shenzhen_poi_enriched.csv")
        
        # --- 关键修复：列名与数据清洗 ---
        # 1. 确保经纬度列名正确 (folium 需要 lat/lon)
        if 'latitude' in df.columns and 'longitude' in df.columns:
            df = df.rename(columns={'latitude': 'lat', 'longitude': 'lon'})
            
        # 2. 确保'类型'列存在 (用于中文筛选)
        # 你的 CSV raw column 是 'type'
        if '类型' not in df.columns and 'type' in df.columns:
            def map_type(val):
                val = str(val)
                if 'Policy_Designated' in val: return '港澳药械通'
                if 'Tier_A_Only' in val: return '公立三甲'
                return '私立/诊所' # 兜底
            df['类型'] = df['type'].apply(map_type)
        elif '类型' not in df.columns:
             df['类型'] = '未知'

        # 3. 确保 'name' 列存在 (用于地图 Tooltip)
        if 'name' not in df.columns and '医院名称' in df.columns:
            df = df.rename(columns={'医院名称': 'name'})

        return df
        
    except FileNotFoundError:
        st.error("❌ 错误：找不到 'shenzhen_poi_enriched.csv' 文件。")
        return pd.DataFrame() 
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
    st.info("本助手旨在为湾区居民提供跨境医疗指引。")

# --- 定义 CSS 变量 ---
if theme == "默认 (微信风)":
    main_bg = "#F5F5F5"
    text_color = "#000000"
    chat_area_bg = "#ECECEC"
    user_bubble_bg = "#95EC69"
    user_text_color = "#000000"
    bot_bubble_bg = "#FFFFFF"
    bot_text_color = "#000000"
    
elif theme == "护眼 (柔和绿)":
    main_bg = "#F0F9EB" 
    text_color = "#2E4033"
    chat_area_bg = "#E1F0D8"
    user_bubble_bg = "#C6E0C4" 
    user_text_color = "#1A2F1D"
    bot_bubble_bg = "#FFFFFF"
    bot_text_color = "#2E4033"

else: # 夜间模式
    main_bg = "#1E1E1E"
    text_color = "#E0E0E0"
    chat_area_bg = "#2D2D2D"
    user_bubble_bg = "#3B71CA"
    user_text_color = "#FFFFFF"
    bot_bubble_bg = "#424242"
    bot_text_color = "#FFFFFF"

# --- 注入 CSS 样式 ---
st.markdown(f"""
<style>
    .stApp {{ background-color: {main_bg}; color: {text_color}; }}
    
    .chat-container {{
        background-color: {chat_area_bg};
        border-radius: 15px;
        padding: 20px;
        height: 500px;
        overflow-y: auto;
        border: 1px solid rgba(0,0,0,0.1);
        display: flex;
        flex-direction: column;
        gap: 15px;
    }}
    
    .chat-row {{ display: flex; align-items: flex-start; width: 100%; }}
    .chat-row.user {{ justify-content: flex-end; }}
    .chat-row.bot {{ justify-content: flex-start; }}
    
    .avatar {{
        width: 40px; height: 40px; border-radius: 50%;
        margin: 0 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }}
    
    .bubble {{
        max-width: 70%; padding: 10px 14px; border-radius: 10px;
        font-size: 15px; line-height: 1.5; position: relative;
        box-shadow: 0 1px 2px rgba(0,0,0,0.1);
    }}
    
    .bubble.user {{ background-color: {user_bubble_bg}; color: {user_text_color}; border-top-right-radius: 2px; }}
    .bubble.bot {{ background-color: {bot_bubble_bg}; color: {bot_text_color}; border-top-left-radius: 2px; }}
    
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    .stChatInputContainer {{ background-color: {main_bg} !important; }}
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

# === 左侧：Folium 地图 ===
with col_left:
    st.markdown("### 🗺️ 医疗资源分布")
    
    if filter_tips:
        st.info(filter_tips, icon="🔍")
    
    # HTML 图例
    st.markdown(f"""
    <div style="display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 10px; color: {text_color}; opacity: 0.8;">
        <span><i class="fa fa-star" style="color:red;"></i> 港澳药械通</span>
        <span><i class="fa fa-plus" style="color:blue;"></i> 公立三甲</span>
        <span><i class="fa fa-leaf" style="color:green;"></i> 私立/诊所</span>
    </div>
    """, unsafe_allow_html=True)

    if not filtered_data.empty:
        # 1. 计算地图中心点 (取平均值，或者默认深圳中心)
        avg_lat = filtered_data['lat'].mean()
        avg_lon = filtered_data['lon'].mean()
        
        # 2. 创建 Folium 地图对象
        m = folium.Map(location=[avg_lat, avg_lon], zoom_start=11, tiles="CartoDB positron")

        # 3. 遍历数据添加自定义 Marker
        for idx, row in filtered_data.iterrows():
            # 原始 type 字段用于逻辑判断
            h_type = str(row.get('type', ''))
            h_name = row.get('name', '未知医院')
            h_addr = row.get('Adress', '暂无地址')

            # 你的自定义图标逻辑
            if 'Policy_Designated' in h_type:
                icon_color = 'red'
                icon_name = 'star'  # 星星
                type_label = "港澳药械通"
            elif 'Tier_A_Only' in h_type:
                icon_color = 'blue'
                icon_name = 'plus'  # 加号
                type_label = "公立三甲"
            else:
                icon_color = 'green'
                icon_name = 'leaf'  # 叶子
                type_label = "非三甲/私立"

            # 创建 Marker
            folium.Marker(
                [row['lat'], row['lon']],
                popup=folium.Popup(f"<b>{h_name}</b><br>{type_label}<br>{h_addr}", max_width=250),
                tooltip=f"{h_name} ({type_label})",
                icon=folium.Icon(color=icon_color, icon=icon_name, prefix='fa') # 使用 FontAwesome
            ).add_to(m)

        # 4. 渲染地图到 Streamlit
        st_folium(m, height=500, use_container_width=True)
        
    else:
        st.warning("数据加载失败或筛选结果为空")

# === 右侧：AI 对话 (自定义气泡渲染) ===
with col_right:
    st.markdown("### 🤖 智能咨询顾问")
    
    chat_html = f'<div class="chat-container">'
    
    if len(st.session_state.messages) == 0:
        chat_html += f"""
        <div class="chat-row bot">
            <img src="{AVATAR_BOT}" class="avatar">
            <div class="bubble bot">
                👋 您好！我是您的跨境医疗助手。<br><br>
                您可以问我：<br>
                1. “附近的<b>港大深圳医院</b>在哪里？”<br>
                2. “哪家牙科可以用<b>长者医疗券</b>？”
            </div>
        </div>
        """
        
    for msg in st.session_state.messages:
        role_class = "user" if msg["role"] == "user" else "bot"
        avatar_src = AVATAR_USER if msg["role"] == "user" else AVATAR_BOT
        content = msg["content"].replace('\n', '<br>')
        
        if msg["role"] == "user":
            row_html = f"""
            <div class="chat-row user">
                <div class="bubble user">{content}</div>
                <img src="{avatar_src}" class="avatar">
            </div>
            """
        else:
            row_html = f"""
            <div class="chat-row bot">
                <img src="{avatar_src}" class="avatar">
                <div class="bubble bot">{content}</div>
            </div>
            """
        chat_html += row_html
        
    chat_html += '</div>'
    st.markdown(chat_html, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 6. 底部输入与回复
# -----------------------------------------------------------------------------

if prompt := st.chat_input("请输入您的问题... (按回车发送)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.rerun()

if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    with col_right:
        with st.spinner("🤖 正在检索政策库..."):
            last_msg = st.session_state.messages[-1]["content"]
            
            # --- 模拟 LLM 回复 (如果你有 API Key，可以在这里接入 OpenAI) ---
            # client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            # ... 你的调用逻辑 ...
            
            response_text = f"收到，关于“{last_msg}”：\n\n根据政策库检索，我已经为您筛选了左侧地图。建议优先参考地图上的高亮区域。"
            
            st.session_state.messages.append({"role": "assistant", "content": response_text})
            st.rerun()
