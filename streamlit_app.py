import streamlit as st
from groq import Groq
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import re
import os
from datetime import datetime

# ==========================================
# 1. 核心初始化
# ==========================================
client = Groq(api_key=st.secrets["GROQ_API_KEY"])
conn = st.connection("gsheets", type=GSheetsConnection)

def check_password():
    if "password_correct" not in st.session_state:
        st.markdown("<br><br>", unsafe_allow_html=True)
        _, col_pw, _ = st.columns([1, 1, 1])
        with col_pw:
            st.subheader("🔐 系統存取控制")
            password = st.text_input("請輸入訪問密碼", type="password")
            if st.button("確認"):
                correct_pw = st.secrets.get("ACCESS_PASSWORD", "ntue123")
                if password == correct_pw:
                    st.session_state["password_correct"] = True
                    st.rerun()
                else:
                    st.error("密碼錯誤！")
        return False
    return True

# (保留 retrieve_category_context 與 is_query_relevant 邏輯，此處省略以縮短長度)

# ==========================================
# 2. 啟動 UI
# ==========================================
st.set_page_config(page_title="SOP 知識檢索輔助系統", layout="wide")

if check_password():
    # 初始化狀態 (與原程式碼相同)
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

    # 側邊欄與進度控制
    with st.sidebar:
        if st.session_state.is_started and not st.session_state.is_finished:
            curr_idx = st.session_state.current_step_idx
            curr_key = task_list[curr_idx]
            st.info(f"目前任務：\n{tasks[curr_key]}")
            user_ans = st.text_area("您的回答：", key=f"ans_{curr_idx}", height=120)
            
            if st.button("✅ 儲存並進入下一題"):
                if user_ans.strip():
                    st.session_state.answers[curr_key] = user_ans
                    if curr_idx < len(task_list) - 1:
                        st.session_state.current_step_idx += 1
                        st.rerun()
                    else:
                        # --- 核心修改：傳送到 Google Sheets ---
                        try:
                            duration = datetime.now() - st.session_state.enter_time
                            duration_str = f"{int(duration.total_seconds() // 60):02d}:{int(duration.total_seconds() % 60):02d}"
                            
                            # 準備數據
                            new_data = []
                            for k, v in st.session_state.answers.items():
                                new_data.append({
                                    "使用者": st.session_state.user_name,
                                    "任務": k,
                                    "回答": v,
                                    "總耗時": duration_str,
                                    "時間戳記": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                })
                            
                            # 讀取現有 Sheets 資料並附加新資料
                            existing_data = conn.read(spreadsheet=st.secrets["GSHEETS_URL"])
                            updated_df = pd.concat([existing_data, pd.DataFrame(new_data)], ignore_index=True)
                            conn.update(spreadsheet=st.secrets["GSHEETS_URL"], data=updated_df)
                            
                            st.session_state.is_finished = True
                            st.rerun()
                        except Exception as e:
                            st.error(f"資料上傳 Sheets 失敗: {e}")

    # (保留主畫面的 Chat 介面與按鈕邏輯)