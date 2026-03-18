import streamlit as st
import ollama
import json
import re
import os
import pandas as pd
from datetime import datetime

# ==========================================
# 1. 核心功能
# ==========================================
KNOWLEDGE_FILE = "sop_kb.md"

@st.cache_data
def load_knowledge(file_path):
    if not os.path.exists(file_path): return ""
    # 加入檔案修改時間偵測，確保修改知識庫後能立即反應
    mtime = os.path.getmtime(file_path)
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
        if any(kw in clean_query for kw in kws) or any(clean_query in kw for kw in kws):
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
# 2. UI 樣式設定 (按鈕緊密排列優化)
# ==========================================
st.set_page_config(page_title="SOP 知識檢索輔助系統", layout="wide")
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: white; }
    
    .main .block-container { padding-bottom: 220px !important; }

    .sop-card-box { 
        background-color: #1e1e26; border-top: 4px solid #4a90e2; border-radius: 12px; 
        padding: 16px 16px 24px 16px; margin-bottom: 24px; height: 260px; 
        display: flex; flex-direction: column; justify-content: flex-start; box-sizing: border-box;
    }
    .sop-step-header { 
        color: #4a90e2; font-weight: 800; border-left: 4px solid #4a90e2; 
        padding-left: 10px; font-size: 1.05rem; margin-bottom: 8px; flex-shrink: 0; 
    }
    .sop-content { 
        background-color: #26262e; border-radius: 8px; padding: 10px; 
        color: #eeeeee !important; line-height: 1.5; font-size: 0.95rem;
        height: 7rem; overflow-y: auto; margin-bottom: 12px; flex-shrink: 0;
    }
    .sop-content::-webkit-scrollbar { width: 4px; }
    .sop-content::-webkit-scrollbar-thumb { background: #4a90e2; border-radius: 10px; }

    .sop-info-line { color: #4a90e2; font-size: 0.9rem; font-weight: 500; margin-bottom: 3px; display: flex; align-items: center; gap: 6px; }
    .sop-footer { font-size: 0.8rem; margin-top: auto; border-top: 1px solid #3d3d3d; padding-top: 8px; padding-bottom: 2px; }

    /* --- 核心修正：強制固定底部按鈕區並緊密排列 --- */
    #custom-bottom-bar {
        position: fixed;
        bottom: 80px;
        left: 50%;
        transform: translateX(-50%);
        width: 100%;
        max-width: 1100px;
        background-color: #0e1117;
        z-index: 99;
        padding: 10px 0;
        /* 使用 Flex 讓按鈕靠左緊貼 */
        display: flex;
        justify-content: flex-start;
    }

    /* 快捷按鈕樣式：寬度不再強制 100% */
    .stButton > button {
        width: auto !important; /* 寬度自動 */
        min-width: 100px;
        border-radius: 6px;
        padding: 0.3rem 0.8rem !important;
        font-size: 0.85rem !important;
        white-space: nowrap !important;
        background-color: #26262e;
        color: white;
        border: 1px solid #3d3d3d;
    }
    
    .stButton > button:hover { border-color: #4a90e2; color: #4a90e2; }

    /* 縮小按鈕之間的欄位間距 */
    [data-testid="column"] {
        flex: 0 1 auto !important; /* 讓欄位寬度根據內容伸縮 */
        padding-right: 8px !important;
        min-width: fit-content !important;
    }

    [data-testid="stBottom"] { background-color: transparent !important; }
    [data-testid="stBottom"] > div { background-color: #0e1117 !important; }

    footer, header {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 3. 狀態初始化
# ==========================================
if "is_started" not in st.session_state: st.session_state.is_started = False
if "user_name" not in st.session_state: st.session_state.user_name = ""
if "enter_time" not in st.session_state: st.session_state.enter_time = None
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

# ==========================================
# 4. 路由與主邏輯
# ==========================================

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
                st.warning("請先輸入姓名！")
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
                        submit_time_obj = datetime.now()
                        st.session_state.is_finished = True
                        duration = submit_time_obj - st.session_state.enter_time
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
    
    # --- 對話歷史展示 ---
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if isinstance(msg["content"], list):
                cols_msg = st.columns(3)
                for i, item in enumerate(msg["content"]):
                    with cols_msg[i % 3]:
                        display_title = str(item.get('title', '項目')).replace("步驟", "").replace(":", "").replace("：", "").strip()
                        st.markdown(f"""
                            <div class="sop-card-box">
                                <div class="sop-step-header">步驟 {i+1}：{display_title}</div>
                                <div class="sop-content">{item.get('content', '暫無描述')}</div>
                                <div class="sop-footer">
                                    <div class="sop-info-line">👤 <b>負責：</b>{item.get('owner', '未註明')}</div>
                                    <div class="sop-info-line">⏳ <b>時限：</b>{item.get('time', '未註明')}</div>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
            else:
                st.write(msg["content"])

    # --- 工具欄：釘死在底部 ---
    shortcut_query = None
    
    st.markdown('<div id="custom-bottom-bar">', unsafe_allow_html=True)
    # 使用 columns 但 CSS 會強制欄位寬度根據內容收縮
    btn_cols = st.columns(5)
    if btn_cols[0].button("💰 報銷流程"): shortcut_query = "報銷流程"
    if btn_cols[1].button("📝 請假申請"): shortcut_query = "請假申請"
    if btn_cols[2].button("🔧 設備報修"): shortcut_query = "設備報修"
    if btn_cols[3].button("🛂 訪客相關"): shortcut_query = "訪客相關"
    if btn_cols[4].button("📅 租借會議室"): shortcut_query = "租借會議室"
    st.markdown('</div>', unsafe_allow_html=True)
    
    chat_input = st.chat_input("輸入 SOP 關鍵字搜尋...")

    # --- 搜尋邏輯處理 (繁體後處理 + 糾錯) ---
    final_query = shortcut_query if shortcut_query else chat_input

    if final_query:
        st.session_state.messages.append({"role": "user", "content": final_query})
        with st.spinner("檢索中..."):
            if not is_query_relevant(final_query):
                st.session_state.messages.append({"role": "assistant", "content": "查無相關 SOP。"})
            else:
                context = retrieve_category_context(final_query, MY_KNOWLEDGE_BASE)
                prompt = (
                    "你是一位台灣資深行政顧問。請根據提供內容回答。\n"
                    f"參考內容：\n{context}\n"
                    f"問題：{final_query}\n"
                    "【輸出規範】請嚴格執行：\n"
                    "1. 必須使用『繁體中文』(台灣術語)。例如：核銷、憑證、主管。\n"
                    "2. 嚴禁出現簡體字（如：报、销、凭、证）。\n"
                    "3. 回傳 JSON 陣列格式：[{\"title\":\"動作名稱\",\"content\":\"繁體說明\",\"owner\":\"對象\",\"time\":\"時限\"}]"
                )
                
                try:
                    res = ollama.generate(model='qwen2.5:7b', prompt=prompt, options={'temperature': 0})
                    match = re.search(r'\[\s*\{.*\}\s*\]', res['response'], re.DOTALL)
                    if match:
                        raw_data = json.loads(match.group())
                        
                        corrections = {
                            "报销": "報銷", "核准": "核准", "凭证": "憑證", "经办人": "經辦人", 
                            "部门": "部門", "经理": "主管", "审批": "審核", "拨付": "撥付"
                        }
                        for item in raw_data:
                            for key in ['title', 'content', 'owner', 'time']:
                                text = str(item.get(key, ""))
                                for cn, tw in corrections.items():
                                    text = text.replace(cn, tw)
                                item[key] = text
                                
                        st.session_state.messages.append({"role": "assistant", "content": raw_data})
                    else:
                        st.session_state.messages.append({"role": "assistant", "content": res['response']})
                except Exception as e:
                    st.session_state.messages.append({"role": "assistant", "content": f"系統解析錯誤: {str(e)}"})
        st.rerun()