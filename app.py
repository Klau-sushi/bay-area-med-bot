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

# 定义头像 (使用更稳定的图源)
AVATAR_BOT = "https://img.icons8.com/fluency/96/robot-2.png" 
AVATAR_USER = "https://img.icons8.com/color/96/user-male-circle--v1.png"

# -----------------------------------------------------------------------------
# 2. 数据加载
# -----------------------------------------------------------------------------
@st.cache_data
def load_data_hybrid():
    try:
        df = pd.read_csv("shenzhen_poi_enriched.csv")
        
        # 清洗列名
        if 'latitude' in df.columns and 'longitude' in df.columns:
            df = df.rename(columns={'latitude': 'lat', 'longitude': 'lon'})
            
        # 清洗类型列
        if '类型' not in df.columns and 'type' in df.columns:
            def map_type(val):
                val = str(val)
                if 'Policy_Designated' in val: return '港澳药械通'
                if 'Tier_A_Only' in val: return '公立三甲'
                return '私立/诊所' 
            df['类型'] = df['type'].apply(map_type)
        elif '类型' not in df.columns:
             df['类型'] = '未知'

        # 清洗名称列
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
# 3. 主题与样式 (修复图标库)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("🎨 界面设置")
    theme = st.selectbox("选择主题", ["默认 (微信风)", "护眼 (柔和绿)", "夜间 (深邃黑)"])
    st.markdown("---")
    st.info("💡 提示：左侧地图仅供参考，请以医院官方信息为准。")

# 定义主题颜色
if theme == "默认 (微信风)":
    bg_color = "#F5F5F5"
    text_color = "#000000"
    card_bg = "#FFFFFF"
elif theme == "护眼 (柔和绿)":
    bg_color = "#F0F9EB"
    text_color = "#2E4033"
    card_bg = "#FFFFFF"
else: # 夜间
    bg_color = "#1E1E1E"
    text_color = "#E0E0E0"
    card_bg = "#2D2D2D"

# 注入 CSS (包含 FontAwesome 修复图例图标)
st.markdown(f"""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
<style>
    .stApp {{ background-color: {bg_color}; color: {text_color}; }}
    
    /* 聊天区卡片样式 */
    .chat-card {{
        background-color: {card_bg};
        border-radius: 15px;
        padding: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }}
    
    /* 隐藏多余元素 */
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    .stChatInputContainer {{ padding-bottom: 20px; }}
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 4. 核心逻辑
# -----------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

# 获取最新问题
user_query = ""
if len(st.session_state.messages) > 0:
    last_msg = st.session_state.messages[-1]
    if last_msg["role"] == "user":
        user_query = last_msg["content"]

# 筛选数据
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
# 5. 布局：左地图 | 右对话
# -----------------------------------------------------------------------------
st.title("🏥 湾区跨境医疗 AI 助手")
st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

col_left, col_right = st.columns([2, 3], gap="large")

# === 左侧：地图 (带自动缩放) ===
with col_left:
    st.markdown("### 🗺️ 医疗资源分布")
    
    if filter_tips:
        st.info(f"🔍 {filter_tips}")
    
    # HTML 图例 (引入了 FontAwesome CSS 后，图标可以显示了)
    st.markdown(f"""
    <div style="display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 10px; color: {text_color}; opacity: 0.9;">
        <span><i class="fa fa-star" style="color:red;"></i> 港澳药械通</span>
        <span><i class="fa fa-plus" style="color:blue;"></i> 公立三甲</span>
        <span><i class="fa fa-leaf" style="color:green;"></i> 私立/诊所</span>
    </div>
    """, unsafe_allow_html=True)

    if not filtered_data.empty:
        # 1. 计算地图中心
        avg_lat = filtered_data['lat'].mean()
        avg_lon = filtered_data['lon'].mean()
        
        # 2. 初始化地图
        m = folium.Map(location=[avg_lat, avg_lon], zoom_start=11, tiles="CartoDB positron")
        
        # 3. 收集坐标点用于自动缩放 (Fit Bounds)
        sw = filtered_data[['lat', 'lon']].min().values.tolist()
        ne = filtered_data[['lat', 'lon']].max().values.tolist()
        
        # 4. 绘制标记
        for idx, row in filtered_data.iterrows():
            h_type = str(row.get('type', ''))
            h_name = row.get('name', '未知医院')
            h_addr = row.get('Adress', '暂无地址')

            # 图标逻辑
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

        # 5. 自动缩放地图以适应筛选结果
        if len(filtered_data) > 0:
            m.fit_bounds([sw, ne])

        st_folium(m, height=500, use_container_width=True)
    else:
        st.warning("⚠️ 未找到匹配的医院数据")

# === 右侧：对话框 (回归原生组件以确保稳定) ===
with col_right:
    st.markdown("### 🤖 智能咨询顾问")
    
    # 使用容器包裹，未来可以用 CSS 针对 container 做背景
    with st.container():
        # 欢迎语
        if len(st.session_state.messages) == 0:
            with st.chat_message("assistant", avatar=AVATAR_BOT):
                st.markdown("您好！我是您的跨境医疗助手。您可以问我：\n\n* “附近的**港大深圳医院**在哪里？”\n* “哪家牙科可以用**长者医疗券**？”")
        
        # 渲染历史记录
        for message in st.session_state.messages:
            avatar = AVATAR_USER if message["role"] == "user" else AVATAR_BOT
            with st.chat_message(message["role"], avatar=avatar):
                st.markdown(message["content"])

# -----------------------------------------------------------------------------
# 6. 输入与回复
# -----------------------------------------------------------------------------
if prompt := st.chat_input("请输入您的问题... (按回车发送)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.rerun()

# AI 回复逻辑
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    with col_right:
        with st.chat_message("assistant", avatar=AVATAR_BOT):
            with st.spinner("思考中..."):
                last_msg = st.session_state.messages[-1]["content"]
                
                # ==========================================================
                # ⬇️ 真实 OpenAI 调用代码 (如果你有 Key，请取消注释以下代码) ⬇️
                # ==========================================================
                # api_key = os.getenv("OPENAI_API_KEY") # 或者直接填入 "sk-xxxx..."
                # if api_key:
                #     try:
                #         client = OpenAI(api_key=api_key)
                #         completion = client.chat.completions.create(
                #             model="gpt-3.5-turbo",
                #             messages=[
                #                 {"role": "system", "content": "你是一个专业的跨境医疗助手，请简短回答用户关于深圳医院的问题。"},
                #                 {"role": "user", "content": last_msg}
                #             ]
                #         )
                #         response_text = completion.choices[0].message.content
                #     except Exception as e:
                #         response_text = f"API 调用出错: {e}"
                # else:
                # ==========================================================
                
                # ⬇️ 默认模拟回复 (无 Key 时使用) ⬇️
                response_text = f"收到，正在为您查询关于“{last_msg}”的信息。\n\n根据政策库：\n如果您正在寻找相关医疗服务，左侧地图已为您筛选出符合条件的机构，您可以点击地图上的图标查看具体地址和特色。"
                
                st.markdown(response_text)
                st.session_state.messages.append({"role": "assistant", "content": response_text})
