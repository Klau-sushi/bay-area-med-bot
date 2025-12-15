import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import math
from openai import OpenAI
import os

# -----------------------------------------------------------------------------
# 1. 页面配置
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="湾区跨境医疗AI助手", 
    page_icon="🏥", 
    layout="wide", 
    initial_sidebar_state="expanded" 
)

# 定义网络头像地址 (使用你指定的机器人头和中性人脸)
AVATAR_BOT = "https://img.icons8.com/fluency/96/bot.png" 
AVATAR_USER = "https://img.icons8.com/color/96/user-male-circle--v1.png"

# -----------------------------------------------------------------------------
# 2. 数据加载
# -----------------------------------------------------------------------------
@st.cache_data
def load_data_hybrid():
    try:
        df = pd.read_csv("shenzhen_poi_enriched.csv")
        
        if 'latitude' in df.columns and 'longitude' in df.columns:
            df = df.rename(columns={'latitude': 'lat', 'longitude': 'lon'})
            
        if '类型' not in df.columns and 'type' in df.columns:
            def map_type(val):
                val = str(val)
                if 'Policy_Designated' in val: return '港澳药械通'
                if 'Tier_A_Only' in val: return '公立三甲'
                return '私立/诊所' 
            df['类型'] = df['type'].apply(map_type)
        elif '类型' not in df.columns:
             df['类型'] = '未知'

        if 'name' not in df.columns and '医院名称' in df.columns:
            df = df.rename(columns={'医院名称': 'name'})

        return df
        
    except FileNotFoundError:
        st.error("❌ 找不到数据文件，请检查 GitHub 仓库。")
        return pd.DataFrame() 
    except Exception as e:
        st.error(f"❌ 数据加载错误: {e}")
        return pd.DataFrame()

df = load_data_hybrid()

# -----------------------------------------------------------------------------
# 3. 主题与配色 (核心修复：颜色适配)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("🎨 界面设置")
    theme = st.selectbox("选择主题", ["默认 (微信风)", "护眼 (柔和绿)", "夜间 (深邃黑)"])
    st.markdown("---")
    st.info("💡 提示：左侧地图仅供参考，请以医院官方信息为准。")

# --- 定义 CSS 变量 (确保字体和气泡颜色都适配) ---
if theme == "默认 (微信风)":
    main_bg = "#F5F5F5"
    text_color = "#000000"
    chat_area_bg = "#ECECEC"
    
    # 气泡配色
    user_bubble_bg = "#95EC69" # 经典微信绿
    user_text_color = "#000000"
    bot_bubble_bg = "#FFFFFF"
    bot_text_color = "#000000"
    
elif theme == "护眼 (柔和绿)":
    main_bg = "#F0F9EB" 
    text_color = "#2E4033"
    chat_area_bg = "#E1F0D8"
    
    # 气泡配色
    user_bubble_bg = "#C6E0C4" 
    user_text_color = "#1A2F1D"
    bot_bubble_bg = "#FFFFFF"
    bot_text_color = "#2E4033"

else: # 夜间模式
    main_bg = "#1E1E1E"
    text_color = "#E0E0E0"
    chat_area_bg = "#2D2D2D"
    
    # 气泡配色
    user_bubble_bg = "#3B71CA" # 深夜蓝
    user_text_color = "#FFFFFF"
    bot_bubble_bg = "#424242" # 深灰
    bot_text_color = "#FFFFFF"

# --- 注入 CSS 样式 (自定义气泡 & FontAwesome) ---
st.markdown(f"""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
<style>
    /* 全局背景 */
    .stApp {{ background-color: {main_bg}; color: {text_color}; }}
    
    /* 聊天容器 */
    .chat-container {{
        background-color: {chat_area_bg};
        border-radius: 15px;
        padding: 20px;
        height: 550px;
        overflow-y: auto;
        border: 1px solid rgba(0,0,0,0.1);
        display: flex;
        flex-direction: column;
        gap: 15px;
    }}
    
    /* 聊天行布局 */
    .chat-row {{ display: flex; align-items: flex-start; width: 100%; }}
    .chat-row.user {{ justify-content: flex-end; }}
    .chat-row.bot {{ justify-content: flex-start; }}
    
    /* 头像样式 */
    .avatar {{
        width: 40px; height: 40px; border-radius: 50%;
        margin: 0 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        background-color: #fff; /* 防止透明图片在深色背景看不清 */
        padding: 2px;
    }}
    
    /* 气泡样式 */
    .bubble {{
        max-width: 70%; padding: 10px 14px; border-radius: 10px;
        font-size: 15px; line-height: 1.5; position: relative;
        box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        word-wrap: break-word;
    }}
    
    /* 气泡颜色适配 */
    .bubble.user {{ 
        background-color: {user_bubble_bg}; 
        color: {user_text_color}; 
        border-top-right-radius: 2px; 
    }}
    .bubble.bot {{ 
        background-color: {bot_bubble_bg}; 
        color: {bot_text_color}; 
        border-top-left-radius: 2px; 
    }}
    
    /* 隐藏多余元素 */
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    .stChatInputContainer {{ background-color: {main_bg} !important; }}
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 4. 核心逻辑
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
        filter_tips = "已聚焦：公立三甲医院"
        filtered_data = filtered_data[filtered_data['类型'].str.contains('三甲', na=False)]
    elif "港澳" in user_query or "药械通" in user_query or "医疗券" in user_query:
        filter_tips = "已聚焦：港澳药械通指定医院"
        filtered_data = filtered_data[filtered_data['类型'].str.contains('港澳|药械通', na=False, regex=True)]
    elif "私立" in user_query or "诊所" in user_query:
        filter_tips = "已聚焦：私立/专科诊所"
        filtered_data = filtered_data[filtered_data['类型'].str.contains('私立|诊所', na=False, regex=True)]

# -----------------------------------------------------------------------------
# 5. 布局
# -----------------------------------------------------------------------------
st.title("🏥 湾区跨境医疗 AI 助手")
st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

col_left, col_right = st.columns([2, 3], gap="large")

# === 左侧：Folium 地图 ===
with col_left:
    st.markdown("### 🗺️ 医疗资源分布")
    
    if filter_tips:
        st.info(f"🔍 {filter_tips}")
    
    # HTML 图例
    st.markdown(f"""
    <div style="display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 10px; color: {text_color}; opacity: 0.9;">
        <span><i class="fa fa-star" style="color:red;"></i> 港澳药械通</span>
        <span><i class="fa fa-plus" style="color:blue;"></i> 公立三甲</span>
        <span><i class="fa fa-leaf" style="color:green;"></i> 私立/诊所</span>
    </div>
    """, unsafe_allow_html=True)

    if not filtered_data.empty:
        avg_lat = filtered_data['lat'].mean()
        avg_lon = filtered_data['lon'].mean()
        
        m = folium.Map(location=[avg_lat, avg_lon], zoom_start=11, tiles="CartoDB positron")
        
        sw = filtered_data[['lat', 'lon']].min().values.tolist()
        ne = filtered_data[['lat', 'lon']].max().values.tolist()
        
        for idx, row in filtered_data.iterrows():
            h_type = str(row.get('type', ''))
            h_name = row.get('name', '未知医院')
            h_addr = row.get('Adress', '暂无地址')

            if 'Policy_Designated' in h_type:
                icon_arg = {'color': 'red', 'icon': 'star', 'prefix': 'fa'}
                type_label = "港澳药械通"
            elif 'Tier_A_Only' in h_type:
                icon_arg = {'color': 'blue', 'icon': 'plus', 'prefix': 'fa'}
                type_label = "公立三甲"
            else:
                icon_arg = {'color': 'green', 'icon': 'leaf', 'prefix': 'fa'}
                type_label = "非三甲/私立"

            folium.Marker(
                [row['lat'], row['lon']],
                popup=folium.Popup(f"<b>{h_name}</b><br>{type_label}<br>{h_addr}", max_width=250),
                tooltip=f"{h_name}",
                icon=folium.Icon(**icon_arg)
            ).add_to(m)

        if len(filtered_data) > 0:
            m.fit_bounds([sw, ne])

        st_folium(m, height=500, use_container_width=True)
    else:
        st.warning("⚠️ 未找到匹配的医院数据")

# === 右侧：HTML 气泡对话框 (恢复你想要的设计) ===
with col_right:
    st.markdown("### 🤖 智能咨询顾问")
    
    # 构造 HTML 字符串
    chat_html = f'<div class="chat-container">'
    
    # 欢迎语
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
    
    # 遍历历史消息生成 HTML
    for msg in st.session_state.messages:
        content = msg["content"].replace('\n', '<br>')
        
        if msg["role"] == "user":
            row_html = f"""
            <div class="chat-row user">
                <div class="bubble user">{content}</div>
                <img src="{AVATAR_USER}" class="avatar">
            </div>
            """
        else:
            row_html = f"""
            <div class="chat-row bot">
                <img src="{AVATAR_BOT}" class="avatar">
                <div class="bubble bot">{content}</div>
            </div>
            """
        chat_html += row_html
        
    chat_html += '</div>'
    
    # 渲染 HTML
    st.markdown(chat_html, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 6. 输入与回复
# -----------------------------------------------------------------------------
if prompt := st.chat_input("请输入您的问题... (按回车发送)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.rerun()

# AI 回复逻辑
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    with col_right:
        # 这里使用 st.spinner 占位，等生成完后通过 rerun 更新 HTML
        with st.spinner("🤖 正在查询医疗数据库..."):
            last_msg = st.session_state.messages[-1]["content"]
            
            # ==========================================================
            # ⬇️ 真实 OpenAI 调用 (配置 Key 后可启用) ⬇️
            # ==========================================================
            # api_key = os.getenv("OPENAI_API_KEY") 
            # if api_key:
            #     try:
            #         client = OpenAI(api_key=api_key)
            #         completion = client.chat.completions.create(
            #             model="gpt-3.5-turbo",
            #             messages=[
            #                 {"role": "system", "content": "你是一个专业的跨境医疗助手，请简短回答用户问题。"},
            #                 {"role": "user", "content": last_msg}
            #             ]
            #         )
            #         response_text = completion.choices[0].message.content
            #     except Exception as e:
            #         response_text = f"API 错误: {e}"
            # else:
            # ==========================================================
            
            # ⬇️ 默认回复 ⬇️
            response_text = f"收到，关于“{last_msg}”：\n\n左侧地图已为您筛选相关医院。建议优先参考地图上的高亮区域。"
            
            st.session_state.messages.append({"role": "assistant", "content": response_text})
            st.rerun()
