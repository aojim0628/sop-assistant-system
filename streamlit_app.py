import streamlit as st
from groq import Groq
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import re
import os
from datetime import datetime

# ==========================================
# 1. 系統初始化與錯誤檢查
# ==========================================
st.set_page_config(page_title="SOP 知識檢索輔助系統", layout="wide")

# 安全檢查：確保 Secrets 都有填寫
required_secrets = ["GROQ_API_KEY", "GSHEETS_URL", "ACCESS_PASSWORD"]
for s in required_secrets:
    if s not in st.secrets:
        st.error(f"❌ 遺失 Secrets 設定：{s}。請至 Streamlit Cloud 設定。")
        st.stop()

# 初始化 Groq 與 Google Sheets 連線
try:
    client = Groq(api_key=st.secrets["GROQ_API_KEY"])
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"❌ 連線初始化失敗: {e}")
    st.stop()

# ==========================================
# 2. 核心邏輯功能
# ==========================================

KNOWLEDGE_FILE = "sop_kb.md"

@st.cache_data
def load_knowledge(file_path):
    if not os.path.exists(file_path): return ""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read().strip()

MY_KNOWLEDGE_BASE = load_knowledge(KNOWLEDGE_FILE)

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

# 密碼檢查
def check_password():
    if "password_correct" not in st.session_state:
        st.markdown("<br><br>", unsafe_allow_html=True)
        _, col_pw, _ = st.columns([1, 1, 1])
        with col_pw:
            st.subheader("🔐 系統存取控制")
            password = st.text_input("請輸入訪問密碼", type="password")
            if st.button("確認"):
                if password == st.secrets["ACCESS_PASSWORD"]:
                    st.session_state["password_correct"] = True
                    st.rerun()
                else:
                    st.error("密碼錯誤！")
        return False
    return True

# ==========================================
# 3. UI 介面與流程
# ==========================================
if check_password():
    # 注入 CSS 樣式
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
        footer, header {visibility: hidden;}
        </style>
    """, unsafe_allow_html=True)

    # 初始化會話狀態
    if "messages" not in st.session_state: st.session_state.messages = []
    if "is_started" not in st.session_state: st.session_state.is_started = False
    if "current_step_idx" not in st.session_state: st.session_state.current_step_idx = 0
    if "answers" not in st.session_state: st.session_state.answers = {}
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
        # 側邊欄：進度與答題
        with st.sidebar:
            st.header(f"👤：{st.session_state.user_name}")
            if not st.session_state.is_finished:
                curr_idx = st.session_state.current_step_idx
                curr_key = task_list[curr_idx]
                st.divider()
                st.write(f"📊 任務進度：{curr_idx + 1} / {len(task_list)}")
                st.progress((curr_idx + 1) / len(task_list))
                st.info(f"任務：{tasks[curr_key]}")
                
                user_ans = st.text_area("您的回答：", key=f"ans_{curr_idx}", height=120)
                if st.button("✅ 儲存並下一題"):
                    if user_ans.strip():
                        st.session_state.answers[curr_key] = user_ans
                        if curr_idx < len(task_list) - 1:
                            st.session_state.current_step_idx += 1
                            st.rerun()
                        else:
                            # 完成後傳送到 Google Sheets
                            try:
                                with st.spinner("正在上傳數據至雲端..."):
                                    duration = datetime.now() - st.session_state.enter_time
                                    duration_str = f"{int(duration.total_seconds() // 60):02d}:{int(duration.total_seconds() % 60):02d}"
                                    
                                    new_rows = []
                                    for k, v in st.session_state.answers.items():
                                        new_rows.append({
                                            "使用者": st.session_state.user_name,
                                            "任務": k,
                                            "回答": v,
                                            "總耗時": duration_str,
                                            "時間戳記": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                        })
                                    
                                    # 讀取並更新
                                    df = conn.read(spreadsheet=st.secrets["GSHEETS_URL"])
                                    updated_df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
                                    conn.update(spreadsheet=st.secrets["GSHEETS_URL"], data=updated_df)
                                    
                                    st.session_state.is_finished = True
                                    st.rerun()
                            except Exception as e:
                                st.error(f"上傳失敗：{e}")
            else:
                st.success("🎉 測驗已完成，數據已同步至 Google Sheets！")
                if st.button("🔄 重新開始"):
                    st.session_state.clear()
                    st.rerun()

        # 主畫面：聊天檢索介面
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

        # 快捷鍵區
        shortcut_query = None
        st.markdown('<div id="custom-bottom-bar">', unsafe_allow_html=True)
        btn_cols = st.columns(5)
        if btn_cols[0].button("💰 報銷流程"): shortcut_query = "報銷流程"
        if btn_cols[1].button("📝 請假申請"): shortcut_query = "請假申請"
        if btn_cols[2].button("🔧 設備報修"): shortcut_query = "設備報修"
        if btn_cols[3].button("🛂 訪客相關"): shortcut_query = "訪客相關"
        if btn_cols[4].button("📅 租借會議室"): shortcut_query = "租借會議室"
        st.markdown('</div>', unsafe_allow_html=True)
        
        chat_input = st.chat_input("輸入關鍵字...")
        final_query = shortcut_query if shortcut_query else chat_input

        if final_query:
            st.session_state.messages.append({"role": "user", "content": final_query})
            with st.spinner("AI 正在極速檢索..."):
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
                        "2. 僅回傳純 JSON 物件，格式：{\"steps\": [{\"title\":\"名稱\",\"content\":\"說明\",\"owner\":\"對象\",\"time\":\"時限\"}]}"
                        "3. 不要輸出任何解釋文字。"
                    )
                    try:
                        chat_completion = client.chat.completions.create(
                            messages=[{"role": "user", "content": prompt}],
                            model="llama-3.3-70b-versatile",
                            temperature=0,
                            response_format={"type": "json_object"}
                        )
                        res_data = json.loads(chat_completion.choices[0].message.content)
                        steps = res_data.get("steps", [])
                        st.session_state.messages.append({"role": "assistant", "content": steps})
                    except Exception as e:
                        st.session_state.messages.append({"role": "assistant", "content": f"錯誤: {e}"})
            st.rerun()