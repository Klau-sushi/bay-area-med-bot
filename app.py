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
        
st.markdown("### 🗺️ 图例说明")

# 使用列 (columns) 将三个说明横向排开，更节省空间也更美观
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("🔴 **红色**：港澳药械通指定医院")

with col2:
    st.markdown("🔵 **蓝色**：公立三甲医院")

with col3:
    st.markdown("🟢 **绿色**：非三甲/私立医院")

st.markdown("---") # 分割线


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
col1, col2 = st.columns([3, 2])

# === 左侧：地图 (三色标记) ===
with col1:
    st.subheader("📍 医疗资源分布")

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

# === 右侧：对话 (逻辑不变) ===
with col2:
    st.subheader("💬 智能咨询")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    chat_container = st.container(height=480)
    for message in st.session_state.messages:
        with chat_container.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("问我关于医院的问题..."):
        if not api_key or not endpoint_id:
            st.toast("请先填入 Key 和 ID！", icon="⚠️")
        else:
            chat_container.chat_message("user").markdown(prompt)
            st.session_state.messages.append({"role": "user", "content": prompt})

            try:
                client = OpenAI(api_key=api_key, base_url="https://ark.cn-beijing.volces.com/api/v3")
                system_prompt = f"你是一个专业的湾区医疗助手。请基于以下数据回答：\n{context_data}"

                response = client.chat.completions.create(
                    model=endpoint_id,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    stream=False
                )
                ai_reply = response.choices[0].message.content
                chat_container.chat_message("assistant").markdown(ai_reply)
                st.session_state.messages.append({"role": "assistant", "content": ai_reply})

            except Exception as e:

                st.error(f"AI 出错：{e}")




