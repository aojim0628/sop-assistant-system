import streamlit as st
import google.generativeai as genai
import json
import re
import os
import pandas as pd
from datetime import datetime

# ==========================================
# 1. 核心功能與 安全設定
# ==========================================

# 密碼檢查功能 (防路人甲)
def check_password():
    if "password_correct" not in st.session_state:
        st.markdown("<br><br>", unsafe_allow_html=True)
        _, col_pw, _ = st.columns([1, 1, 1])
        with col_pw:
            st.subheader("🔐 系統存取控制")
            password = st.text_input("請輸入訪問密碼", type="password")
            if st.button("確認"):
                # 優先從 Secrets 讀取密碼，如果沒設定就預設為 "ntue123"
                correct_pw = st.secrets.get("ACCESS_PASSWORD", "ntue123")
                if password == correct_pw:
                    st.session_state["password_correct"] = True
                    st.rerun()
                else:
                    st.error("密碼錯誤！")
        return False
    return True

# 讀取 API KEY
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=GEMINI_API_KEY)

# 修正模型名稱：改用最穩定的 1.5-flash 或最新的 2.0-flash-exp
# 建議先用 'gemini-1.5-flash'，這是目前最通用的
# 加上最新的小版本號，這通常能解決 404 問題
model = genai.GenerativeModel('gemini-1.5-flash-latest')

KNOWLEDGE_FILE = "sop_kb.md"

@st.cache_data
def load_knowledge(file_path):
    if not os.path.exists(file_path): return ""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read().strip()

MY_KNOWLEDGE_BASE = load_knowledge(KNOWLEDGE_FILE)

# (其餘 retrieve_category_context 與 is_query_relevant 邏輯保持不變)
def retrieve_category_context(query, full_text):
    if not full_text: return ""
    clean_query = query.strip().lower()
    chunks = [c.strip() for c in re.split(r'\n#+\s', full_text) if c.strip()]
    category_map = {
        "總務行政/空間租借": ["會議", "空間", "租借", "總務"],
        "資訊安全/訪客管理": ["訪客", "nda", "換證", "資安", "保全", "簽署"],
        "IT資源/設備報修": ["報修", "故障", "it", "維修"],
        "人事/請假申請": ["請假", "人事", "hr", "休假", "portal"],
        "財務/採購報銷": ["報銷", "核銷", "費用", "財務", "會計", "單據"]
    }
    target_category = None
    for cat, kws in category_map.items():
        if any(kw in clean_query for kw in kws):
            target_category = cat
            break
    if target_category:
        relevant_chunks = [c for c in chunks if target_category in c]
        if relevant_chunks: return "\n\n".join(["## " + c for c in relevant_chunks])
    scored_chunks = [c for c in chunks if any(part in c.lower() for part in clean_query)]
    return "\n\n".join(["## " + c for c in scored_chunks[:5]])

def is_query_relevant(query):
    sop_keywords = ["會議", "會議室", "空間", "租借", "訪客", "nda", "換證", "資安", "保全", "報修", "故障", "it", "維修", "請假", "人事", "hr", "報銷", "核銷", "sop", "流程", "休假", "簽署", "單據"]
    return any(kw in query.strip().lower() for kw in sop_keywords)

# ==========================================
# 2. 啟動密碼鎖與 UI
# ==========================================
st.set_page_config(page_title="SOP 知識檢索輔助系統", layout="wide")

if check_password():
    # --- 原本的 UI 程式碼開始 ---
    st.markdown("""
        <style>
        .stApp { background-color: #0e1117; color: white; }
        .main .block-container { padding-bottom: 220px !important; }
        .sop-card-box { 
            background-color: #1e1e26; border-top: 4px solid #4a90e2; border-radius: 12px; 
            padding: 16px; margin-bottom: 24px; height: 260px; 
            display: flex; flex-direction: column;
        }
        .sop-step-header { color: #4a90e2; font-weight: 800; border-left: 4px solid #4a90e2; padding-left: 10px; margin-bottom: 8px; }
        .sop-content { background-color: #26262e; border-radius: 8px; padding: 10px; color: #eeeeee; height: 7rem; overflow-y: auto; margin-bottom: 12px; }
        .sop-info-line { color: #4a90e2; font-size: 0.9rem; margin-bottom: 3px; }
        #custom-bottom-bar { position: fixed; bottom: 80px; left: 50%; transform: translateX(-50%); width: 100%; max-width: 1100px; display: flex; z-index: 99; }
        .stButton > button { width: auto !important; min-width: 100px; background-color: #26262e; color: white; }
        footer, header {visibility: hidden;}
        </style>
    """, unsafe_allow_html=True)

    # 狀態初始化
    if "is_started" not in st.session_state: st.session_state.is_started = False
    if "user_name" not in st.session_state: st.session_state.user_name = ""
    if "messages" not in st.session_state: st.session_state.messages = []
    if "answers" not in st.session_state: st.session_state.answers = {}
    if "current_step_idx" not in st.session_state: st.session_state.current_step_idx = 0
    if "is_finished" not in st.session_state: st.session_state.is_finished = False

    tasks = {
        "任務 1": "預約「會議室」必須在使用日前幾天提出申請？",
        "任務 2": "訪客到達櫃台後，除了領取證件，還必須簽署什麼文件？",
        "任務 3": "「技術員初步檢測」步驟的時限要求為何？",
        "任務 4": "請假的「關鍵層級審核」是由哪個職位負責？",
        "任務 5": "會議預計比原定時間多出 15 分鐘，必須執行哪項動作？",
        "任務 6": "陪同訪客離開時，保全人員必須執行哪兩項資安檢查重點？"
    }
    task_list = list(tasks.keys())

    # 路由與主邏輯
    if not st.session_state.is_started:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        _, col_center, _ = st.columns([1, 1.5, 1])
        with col_center:
            st.title("🔍 SOP 知識檢索輔助系統")
            name = st.text_input("您的姓名", key="name_input")
            if st.button("進入系統", use_container_width=True):
                if name.strip():
                    st.session_state.user_name = name
                    st.session_state.is_started = True
                    st.session_state.enter_time = datetime.now() 
                    st.rerun()
    else:
        with st.sidebar:
            st.header(f"👤 使用者：{st.session_state.user_name}")
            if not st.session_state.is_finished:
                curr_idx = st.session_state.current_step_idx
                curr_key = task_list[curr_idx]
                st.divider()
                st.write(f"📊 任務進度：{curr_idx + 1} / {len(task_list)}")
                st.progress((curr_idx + 1) / len(task_list))
                st.info(f"目前任務：\n{tasks[curr_key]}")
                
                user_ans = st.text_area("您的回答：", key=f"ans_{curr_idx}", height=120)
                if st.button("✅ 儲存並進入下一題"):
                    if user_ans.strip():
                        st.session_state.answers[curr_key] = user_ans
                        if curr_idx < len(task_list) - 1:
                            st.session_state.current_step_idx += 1
                        else:
                            st.session_state.is_finished = True
                            duration = datetime.now() - st.session_state.enter_time
                            duration_str = f"{int(duration.total_seconds() // 60):02d}:{int(duration.total_seconds() % 60):02d}"
                            final_results = [{"使用者": st.session_state.user_name, "任務": k, "回答": v, "總耗時": duration_str} for k, v in st.session_state.answers.items()]
                            pd.DataFrame(final_results).to_csv("test_results.csv", mode='a', index=False, header=not os.path.exists("test_results.csv"), encoding="utf-8-sig")
                        st.rerun()
            else:
                st.success("🎉 任務完成！")
                if st.button("🔄 重新測驗"):
                    st.session_state.clear()
                    st.rerun()

        st.title("🔍 SOP 知識檢索輔助系統")
        
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                if isinstance(msg["content"], list):
                    cols_msg = st.columns(3)
                    for i, item in enumerate(msg["content"]):
                        with cols_msg[i % 3]:
                            st.markdown(f"""
                                <div class="sop-card-box">
                                    <div class="sop-step-header">步驟 {i+1}：{item.get('title', '項目')}</div>
                                    <div class="sop-content">{item.get('content', '暫無描述')}</div>
                                    <div class="sop-info-line">👤 負責：{item.get('owner', '未註明')}</div>
                                    <div class="sop-info-line">⏳ 時限：{item.get('time', '未註明')}</div>
                                </div>
                            """, unsafe_allow_html=True)
                else:
                    st.write(msg["content"])

        shortcut_query = None
        st.markdown('<div id="custom-bottom-bar">', unsafe_allow_html=True)
        btn_cols = st.columns(5)
        if btn_cols[0].button("💰 報銷流程"): shortcut_query = "報銷流程"
        if btn_cols[1].button("📝 請假申請"): shortcut_query = "請假申請"
        if btn_cols[2].button("🔧 設備報修"): shortcut_query = "設備報修"
        if btn_cols[3].button("🛂 訪客相關"): shortcut_query = "訪客相關"
        if btn_cols[4].button("📅 租借會議室"): shortcut_query = "租借會議室"
        st.markdown('</div>', unsafe_allow_html=True)
        
        chat_input = st.chat_input("輸入 SOP 關鍵字搜尋...")
        final_query = shortcut_query if shortcut_query else chat_input

        if final_query:
            st.session_state.messages.append({"role": "user", "content": final_query})
            with st.spinner("Gemini 正在檢索..."):
                if not is_query_relevant(final_query):
                    st.session_state.messages.append({"role": "assistant", "content": "查無相關 SOP 資訊。"})
                else:
                    context = retrieve_category_context(final_query, MY_KNOWLEDGE_BASE)
                    prompt = (
                        "你是一位台灣資深行政顧問。請根據提供內容回答。\n"
                        f"參考內容：\n{context}\n"
                        f"問題：{final_query}\n"
                        "【輸出規範】：\n"
                        "1. 必須使用『繁體中文』(台灣術語)。\n"
                        "2. 嚴禁簡體字。\n"
                        "3. 僅回傳 JSON 陣列，格式：[{\"title\":\"動作名稱\",\"content\":\"繁體說明\",\"owner\":\"對象\",\"time\":\"時限\"}]"
                    )
                    try:
                        response = model.generate_content(
                            prompt,
                            generation_config=genai.types.GenerationConfig(
                                temperature=0,
                                response_mime_type="application/json"
                            )
                        )
                        raw_data = json.loads(response.text)
                        st.session_state.messages.append({"role": "assistant", "content": raw_data})
                    except Exception as e:
                        st.session_state.messages.append({"role": "assistant", "content": f"系統解析錯誤: {str(e)}"})
            st.rerun()