import streamlit as st
import pandas as pd
from openai import OpenAI
import os
import folium
from streamlit_folium import st_folium

# 1. 页面配置
st.set_page_config(page_title="湾区跨境医疗AI助手", page_icon="🏥", layout="wide", initial_sidebar_state="collapsed")
st.title("🏥 湾区跨境医疗AI助手")

# 2. 侧边栏设置
with st.sidebar:
    st.header("🔑 设置")
    
    # === 核心修改逻辑：优先读取云端 Secrets ===
    
    # 1. 处理 API Key
    if "VOLC_API_KEY" in st.secrets:
        # 如果云端配置了，就直接读取，不显示输入框
        api_key = st.secrets["VOLC_API_KEY"]
        st.success("✅ 云端 Key 已自动加载")
    else:
        # 如果没配置（比如你在本地跑），就显示输入框
        api_key = st.text_input("1. API Key", type="password")

    # 2. 处理 Endpoint ID
    if "VOLC_ENDPOINT_ID" in st.secrets:
        endpoint_id = st.secrets["VOLC_ENDPOINT_ID"]
        st.success("✅ 云端 ID 已自动加载")
    else:
        endpoint_id = st.text_input("2. Endpoint ID (ep-xxxx)")
        
# st.markdown("### 🗺️ 图例说明")


# 3. 加载数据 (精准区分三类)
@st.cache_data
def load_data_hybrid():
    # 读取文件
    file_path = "shenzhen_poi_enriched.csv"
    if not os.path.exists(file_path):
        file_path = "shenzhen_poi_data.xlsx"  # 降级读取
        if not os.path.exists(file_path):
            return None, None

    if file_path.endswith('.csv'):
        df = pd.read_csv(file_path)
    else:
        df = pd.read_excel(file_path)

    text_context = ""
    for index, row in df.iterrows():
        # 获取AI简介
        ai_info = str(row.get('ai_context', '暂无详细信息'))

        # ★★★ 核心修改：精准翻译三种类型 ★★★
        h_type = row['type']
        if h_type == "Policy_Designated":
            h_type_cn = "【港澳药械通指定医院】"
        elif h_type == "Tier_A_Only":
            h_type_cn = "【公立三甲医院】"
        elif h_type == "Non_Tier_A_Policy":
            h_type_cn = "【非三甲/私立医院】"  # 修正了这里！
        else:
            h_type_cn = "其他类型医院"

        text_context += f"医院：{row['name']} | 类型：{h_type_cn} | 详情：{ai_info} | 坐标：({row['latitude']}, {row['longitude']})\n"

    return df, text_context


df, context_data = load_data_hybrid()

if df is None:
    st.error("❌ 找不到数据文件！")
    st.stop()

# 4. 页面布局
col_map, col_chat = st.columns([2, 1])

# === 左侧：地图 (三色标记) ===
with col_map:
    st.subheader("📍 医疗资源分布")
    # 使用行 (rows) 将三个说明横向排开，更节省空间也更美观
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("🔴 港澳药械通指定医院")
    
    with col2:
        st.markdown("🔵 公立三甲医院")
    
    with col3:
        st.markdown("🟢 非三甲/私立医院")


    m = folium.Map(location=[22.54, 114.05], zoom_start=11)

    for index, row in df.iterrows():
        # ★★★ 核心修改：三种颜色逻辑 ★★★
        h_type = row['type']

        if h_type == 'Policy_Designated':
            icon_color = 'red'  # 药械通 = 红
            icon_icon = 'star'
            type_label = "药械通指定"
        elif h_type == 'Tier_A_Only':
            icon_color = 'blue'  # 三甲 = 蓝
            icon_icon = 'plus'
            type_label = "公立三甲"
        else:
            icon_color = 'green'  # 其他 = 绿
            icon_icon = 'leaf'  # 用叶子代表非公立/私立
            type_label = "非三甲/私立"

        # 添加标记
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            tooltip=f"{row['name']} ({type_label})",
            popup=f"<b>{row['name']}</b><br>类型：{type_label}<br>{str(row.get('ai_context', ''))[:50]}...",
            icon=folium.Icon(color=icon_color, icon=icon_icon)
        ).add_to(m)

    st_folium(m, height=600, use_container_width=True)

# === 右侧：对话 ===
with col_chat:
    st.subheader("💬 智能客服")
    
    # 主题切换 (只保留一处定义)
    theme = st.radio("🌙 选择主题", ["默认", "夜间", "护眼"], index=0, key="theme")
    
    # 动态应用主题样式 (添加完整CSS)
    if theme == "夜间":
        st.markdown("""
        <style>
            :root {
                --primary-color: #1A237E;
                --bg-color: #121212;
                --text-color: #E0E0E0;
                --human-bg: #2d2d2d;
                --ai-bg: #1f1f1f;
            }
            .chat-container {
                background: var(--bg-color);
                color: var(--text-color);
            }
            .human {
                background: var(--human-bg);
                border-left: 4px solid var(--primary-color);
            }
            .ai {
                background: var(--ai-bg);
                border-left: 4px solid var(--primary-color);
            }
        </style>
        """, unsafe_allow_html=True)
    elif theme == "护眼":
        st.markdown("""
        <style>
            :root {
                --primary-color: #2E7D32;
                --bg-color: #F1F8E9;
                --text-color: #2D3436;
                --human-bg: #ffffff;
                --ai-bg: #e8f5e9;
            }
            .chat-container {
                background: var(--bg-color);
                color: var(--text-color);
            }
            .human {
                background: var(--human-bg);
                border-left: 4px solid var(--primary-color);
            }
            .ai {
                background: var(--ai-bg);
                border-left: 4px solid var(--primary-color);
            }
        </style>
        """, unsafe_allow_html=True)
    else:  # 默认主题
        st.markdown("""
        <style>
            :root {
                --primary-color: #2A5CAA;
                --bg-color: #F8F9FF;
                --text-color: #2D3436;
                --human-bg: #ffffff;
                --ai-bg: #F3F4F6;
            }
            .chat-container {
                background: var(--bg-color);
                color: var(--text-color);
            }
            .human {
                background: var(--human-bg);
                border-left: 4px solid var(--primary-color);
            }
            .ai {
                background: var(--ai-bg);
                border-left: 4px solid var(--primary-color);
            }
        </style>
        """, unsafe_allow_html=True)
    
    # 聊天容器 (消息气泡和头像在这里显示)
    chat_container = st.container(height=500)
    with chat_container:
        # 初始化消息显示区域
        if "messages" not in st.session_state:
            st.session_state.messages = []
            # 添加欢迎消息
            st.session_state.messages.append({"role": "assistant", "content": "您好！我是医疗助手，有什么可以帮您？"})
        
        # 显示所有消息 (带头像和气泡样式)
        for message in st.session_state.messages:
            role = message["role"]
            content = message["content"]
    
            # 头像独立显示
            avatar_img = "🤖" if role == "assistant" else "👩⚕️"  # 使用医疗相关符号
            is_avatar = role == "assistant"  # 仅在AI消息显示头像
            
            # 消息气泡样式
            st.markdown(f"""
            <div style="
                display: flex;
                align-items: flex-start;
                margin: 10px 0;
                gap: 15px;
            ">
                {f'<span style="font-size:24px">{avatar_img}</span>' if is_avatar else ''}
                <div style="
                    background: {'#F3F4F6' if role == 'assistant' else 'white'};
                    border-radius: 18px;
                    padding: 12px 16px;
                    max-width: 70%;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                ">
                    {content}
                </div>
            </div>
            """, unsafe_allow_html=True)
    
    # 输入表单 (简化版，无文件上传)
    with st.form(key="chat_form", clear_on_submit=True):
        user_input = st.text_area(
            "输入消息...", 
            placeholder="问我关于医院的问题...", 
            label_visibility="collapsed",
            height=100
        )
        submit_button = st.form_submit_button("发送")
    
    # 处理消息发送
    if submit_button and user_input.strip():
        # 添加用户消息
        st.session_state.messages.append({"role": "user", "content": user_input})
        
        # 获取AI回复
        if api_key and endpoint_id:
            try:
                client = OpenAI(api_key=api_key, base_url="https://ark.cn-beijing.volces.com/api/v3")
                system_prompt = f"你是一个专业的湾区医疗助手。请基于以下数据回答：\n{context_data}"
                
                response = client.chat.completions.create(
                    model=endpoint_id,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_input},
                    ],
                    stream=False
                )
                ai_reply = response.choices[0].message.content
                st.session_state.messages.append({"role": "assistant", "content": ai_reply})
                
            except Exception as e:
                error_msg = f"AI出错：{str(e)}"
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
        else:
            error_msg = "请先在侧边栏设置API Key和Endpoint ID"
            st.session_state.messages.append({"role": "assistant", "content": error_msg})
        
        # 刷新页面显示新消息
        st.rerun()















