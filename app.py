import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
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

# 定义网络头像
AVATAR_BOT = "https://img.icons8.com/fluency/96/bot.png" 
AVATAR_USER = "https://img.icons8.com/color/96/user-male-circle--v1.png"

# -----------------------------------------------------------------------------
# 2. 数据加载 & 知识库构建
# -----------------------------------------------------------------------------
@st.cache_data
def load_data_hybrid():
    try:
        df = pd.read_csv("shenzhen_poi_enriched.csv")
        
        # 1. 清洗经纬度
        if 'latitude' in df.columns and 'longitude' in df.columns:
            df = df.rename(columns={'latitude': 'lat', 'longitude': 'lon'})
            
        # 2. 清洗类型 (用于地图筛选)
        if '类型' not in df.columns and 'type' in df.columns:
            def map_type(val):
                val = str(val)
                if 'Policy_Designated' in val: return '港澳药械通'
                if 'Tier_A_Only' in val: return '公立三甲'
                return '私立/诊所' 
            df['类型'] = df['type'].apply(map_type)
        elif '类型' not in df.columns:
             df['类型'] = '未知'

        # 3. 清洗名称
        if 'name' not in df.columns and '医院名称' in df.columns:
            df = df.rename(columns={'医院名称': 'name'})
            
        # 4. 清洗地址 (兼容 Adress 拼写错误)
        if 'address' not in df.columns:
            if 'Adress' in df.columns:
                df = df.rename(columns={'Adress': 'address'})
            elif '地址' in df.columns:
                df = df.rename(columns={'地址': 'address'})

        # 5. 构建 AI 上下文知识库
        if 'ai_context' not in df.columns:
            df['ai_context'] = df.apply(lambda x: f"医院名：{x.get('name')} | 类型：{x.get('类型')} | 地址：{x.get('address', '未知')}", axis=1)
        
        return df
        
    except FileNotFoundError:
        st.error("❌ 找不到数据文件，请检查 GitHub 仓库。")
        return pd.DataFrame() 
    except Exception as e:
        st.error(f"❌ 数据加载错误: {e}")
        return pd.DataFrame()

df = load_data_hybrid()

# 准备 System Prompt
hospital_knowledge_base = "\n".join(df['ai_context'].astype(str).tolist()) if not df.empty else "暂无数据"

# -----------------------------------------------------------------------------
# 3. 主题与配色
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("🎨 界面设置")
    theme = st.selectbox("选择主题", ["默认 (微信风)", "护眼 (柔和绿)", "夜间 (深邃黑)"])
    st.markdown("---")
    st.info("💡 提示：左侧地图自动展示，右侧 AI 负责解答。")

# --- CSS 样式 (适配气泡) ---
if theme == "默认 (微信风)":
    main_bg, text_color, chat_area_bg = "#F5F5F5", "#000000", "#ECECEC"
    user_bubble, user_text = "#95EC69", "#000000"
    bot_bubble, bot_text = "#FFFFFF", "#000000"
elif theme == "护眼 (柔和绿)":
    main_bg, text_color, chat_area_bg = "#F0F9EB", "#2E4033", "#E1F0D8"
    user_bubble, user_text = "#C6E0C4", "#1A2F1D"
    bot_bubble, bot_text = "#FFFFFF", "#2E4033"
else: # 夜间
    main_bg, text_color, chat_area_bg = "#1E1E1E", "#E0E0E0", "#2D2D2D"
    user_bubble, user_text = "#3B71CA", "#FFFFFF"
    bot_bubble, bot_text = "#424242", "#FFFFFF"

st.markdown(f"""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
<style>
    .stApp {{ background-color: {main_bg}; color: {text_color}; }}
    .chat-container {{
        background-color: {chat_area_bg};
        border-radius: 15px;
        padding: 20px;
        height: 600px;
        overflow-y: auto;
        border: 1px solid rgba(0,0,0,0.1);
        display: flex; flex-direction: column; gap: 15px;
    }}
    .chat-row {{ display: flex; align-items: flex-start; width: 100%; margin-bottom: 10px; }}
    .chat-row.user {{ justify-content: flex-end; }}
    .chat-row.bot {{ justify-content: flex-start; }}
    .avatar {{
        width: 40px; height: 40px; border-radius: 50%;
        margin: 0 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        background-color: #fff; padding: 2px; flex-shrink: 0;
    }}
    .bubble {{
        max-width: 75%; padding: 12px 16px; border-radius: 10px;
        font-size: 15px; line-height: 1.6; position: relative;
        box-shadow: 0 1px 2px rgba(0,0,0,0.1); word-wrap: break-word;
    }}
    .bubble.user {{ background-color: {user_bubble}; color: {user_text}; border-top-right-radius: 2px; }}
    .bubble.bot {{ background-color: {bot_bubble}; color: {bot_text}; border-top-left-radius: 2px; }}
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    .stChatInputContainer {{ background-color: {main_bg} !important; }}
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 4. 逻辑处理
# -----------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

# 获取最新问题 (仅用于左侧地图筛选)
user_query = ""
if len(st.session_state.messages) > 0:
    last_msg = st.session_state.messages[-1]
    if last_msg["role"] == "user":
        user_query = last_msg["content"]

# === 左侧地图逻辑：独立运行，不干扰 AI ===
filtered_data = df.copy()
filter_tips = "" 

if not filtered_data.empty and user_query:
    if "三甲" in user_query or "公立" in user_query:
        filter_tips = "已聚焦：公立三甲医院"
        filtered_data = filtered_data[filtered_data['类型'].str.contains('三甲', na=False)]
    elif "港澳" in user_query or "药械通" in user_query or "医疗券" in user_query:
        filter_tips = "已聚焦：港澳药械通指定医院"
        filtered_data = filtered_data[filtered_data['类型'].str.contains('港澳|药械通', na=False, regex=True)]
    elif "私立" in user_query or "诊所" in user_query:
        filter_tips = "已聚焦：私立/专科诊所"
        filtered_data = filtered_data[filtered_data['类型'].str.contains('私立|诊所', na=False, regex=True)]

# -----------------------------------------------------------------------------
# 5. 页面布局
# -----------------------------------------------------------------------------
st.title("🏥 湾区跨境医疗 AI 助手")
st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

col_left, col_right = st.columns([2, 3], gap="large")

# === 左侧：Folium 地图 (纯展示，无跳转) ===
with col_left:
    st.markdown("### 🗺️ 医疗资源分布")
    
    if filter_tips:
        st.success(f"🔍 {filter_tips}")
    
    # 图例
    legend_html = f"""<div style="display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 10px; color: {text_color}; opacity: 0.9;"><span><i class="fa fa-star" style="color:red;"></i> 港澳药械通</span><span><i class="fa fa-plus" style="color:blue;"></i> 公立三甲</span><span><i class="fa fa-leaf" style="color:green;"></i> 私立/诊所</span></div>"""
    st.markdown(legend_html, unsafe_allow_html=True)

    if not filtered_data.empty:
        avg_lat, avg_lon = filtered_data['lat'].mean(), filtered_data['lon'].mean()
        m = folium.Map(location=[avg_lat, avg_lon], zoom_start=11, tiles="CartoDB positron")
        sw = filtered_data[['lat', 'lon']].min().values.tolist()
        ne = filtered_data[['lat', 'lon']].max().values.tolist()
        
        for idx, row in filtered_data.iterrows():
            h_type = str(row.get('type', ''))
            h_name = row.get('name', '未知医院')
            h_addr = row.get('address', '暂无地址')

            if 'Policy_Designated' in h_type:
                icon_arg = {'color': 'red', 'icon': 'star', 'prefix': 'fa'}
                type_label = "港澳药械通"
            elif 'Tier_A_Only' in h_type:
                icon_arg = {'color': 'blue', 'icon': 'plus', 'prefix': 'fa'}
                type_label = "公立三甲"
            else:
                icon_arg = {'color': 'green', 'icon': 'leaf', 'prefix': 'fa'}
                type_label = "非三甲/私立"

            # 纯展示型 Marker
            folium.Marker(
                [row['lat'], row['lon']],
                popup=folium.Popup(f"<b>{h_name}</b><br>{type_label}<br>{h_addr}", max_width=200),
                tooltip=f"{h_name}",
                icon=folium.Icon(**icon_arg)
            ).add_to(m)

        if len(filtered_data) > 0: m.fit_bounds([sw, ne])
        st_folium(m, height=550, use_container_width=True)
    else:
        st.warning("⚠️ 未找到匹配的医院数据")

# === 右侧：AI 对话 (核心功能) ===
with col_right:
    st.markdown("### 🤖 智能咨询顾问")
    
    chat_html = f'<div class="chat-container">'
    if len(st.session_state.messages) == 0:
        chat_html += f"""<div class="chat-row bot"><img src="{AVATAR_BOT}" class="avatar"><div class="bubble bot">👋 您好！我是您的跨境医疗助手。<br><br>我已学习了最新的湾区医疗数据。您可以问我：<br>1. “附近的<b>港大深圳医院</b>在哪里？”<br>2. “哪家牙科可以用<b>长者医疗券</b>？”</div></div>"""
    
    for msg in st.session_state.messages:
        content = msg["content"].replace('\n', '<br>')
        if msg["role"] == "user":
            chat_html += f"""<div class="chat-row user"><div class="bubble user">{content}</div><img src="{AVATAR_USER}" class="avatar"></div>"""
        else:
            chat_html += f"""<div class="chat-row bot"><img src="{AVATAR_BOT}" class="avatar"><div class="bubble bot">{content}</div></div>"""
    chat_html += '</div>'
    st.markdown(chat_html, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 6. AI 响应逻辑 (使用 Streamlit Secrets 隐藏 Key)
# -----------------------------------------------------------------------------
if prompt := st.chat_input("请输入您的问题... (按回车发送)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.rerun()

if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    with col_right:
        with st.spinner("🤖 AI 正在思考中..."):
            last_msg = st.session_state.messages[-1]["content"]
            
            # === 安全获取 API Key (适配火山引擎 / DeepSeek) ===
            # 从 Secrets 或环境变量获取火山引擎的 API Key 和 Endpoint ID
            volc_api_key = st.secrets.get("VOLC_API_KEY") or os.getenv("VOLC_API_KEY")
            volc_endpoint_id = st.secrets.get("VOLC_ENDPOINT_ID") or os.getenv("VOLC_ENDPOINT_ID")
            
            if volc_api_key and volc_endpoint_id:
                try:
                    # 初始化 OpenAI Client，并指向火山引擎的 Base URL
                    client = OpenAI(
                        api_key=volc_api_key,
                        base_url="https://ark.cn-beijing.volces.com/api/v3"
                    )
                    
                    # 构建 Prompt: 明确要求不提及“跳转”
                    messages = [
                        {"role": "system", "content": f"""
                        你是一个专业的湾区跨境医疗助手。请根据以下[知识库]中的医院数据回答用户问题。
                        
                        [回答要求]：
                        1. 必须基于知识库回答，不要编造。
                        2. 直接给出医院名称、地址、类型和相关特色。
                        3. 严禁提及“点击地图”、“地图高亮”、“跳转链接”等交互操作，因为前端已去除这些功能。
                        4. 语气亲切、专业。
                        
                        [知识库]:
                        {hospital_knowledge_base[:30000]} 
                        """},
                        {"role": "user", "content": last_msg}
                    ]
                    
                    # 使用 Endpoint ID 作为 model 参数
                    completion = client.chat.completions.create(
                        model=volc_endpoint_id, 
                        messages=messages,
                        temperature=0.7
                    )
                    response_text = completion.choices[0].message.content
                    
                except Exception as e:
                    response_text = f"⚠️ AI 服务暂时不可用 (Error: {str(e)[:50]}...)"
            else:
                response_text = "⚠️ 系统未配置火山引擎 Key。请管理员在 Streamlit 后台 Secrets 配置 VOLC_API_KEY 和 VOLC_ENDPOINT_ID。"
            
            st.session_state.messages.append({"role": "assistant", "content": response_text})
            st.rerun()
