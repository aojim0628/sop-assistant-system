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
def load_knowledge():
    if not os.path.exists(KNOWLEDGE_FILE): return ""
    with open(KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()

MY_KNOWLEDGE_BASE = load_knowledge()

def retrieve_category_context(query, full_text):
    if not full_text: return ""
    clean_query = query.strip().lower()
    chunks = [c.strip() for c in re.split(r'\n#+\s', full_text) if c.strip()]
    
    category_map = {
        "總務行政/空間租借": ["會議", "空間", "租借", "總務"],
        "資訊安全/訪客管理": ["訪客", "nda", "換證", "資安", "保全"],
        "IT資源/設備報修": ["報修", "故障", "it", "維修"],
        "人事/請假申請": ["請假", "人事", "hr", "休假", "portal"],
        "財務/採購報銷": ["報銷", "核銷", "費用", "財務", "會計"]
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
    sop_keywords = ["會議", "會議室", "空間", "租借", "訪客", "nda", "換證", "資安", "保全", "報修", "故障", "it", "維修", "請假", "人事", "hr", "報銷", "核銷", "sop", "流程", "休假"]
    return any(kw in query.strip().lower() for kw in sop_keywords)

# ==========================================
# 2. UI 樣式設定
# ==========================================
st.set_page_config(page_title="SOP 知識檢索輔助系統", layout="wide")
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: white; }
    
    /* 卡片容器：固定高度 260px，並增加底部內距 */
    .sop-card-box { 
        background-color: #1e1e26; border-top: 4px solid #4a90e2; border-radius: 12px; 
        padding: 16px 16px 24px 16px; 
        margin-bottom: 24px; 
        height: 260px; 
        display: flex; flex-direction: column; justify-content: flex-start; 
        box-sizing: border-box;
    }
    
    .sop-step-header { 
        color: #4a90e2; font-weight: 800; border-left: 4px solid #4a90e2; 
        padding-left: 10px; font-size: 1.05rem; margin-bottom: 8px; flex-shrink: 0; 
    }
    
    /* 描述欄位：固定約四行高度，超出則捲動 */
    .sop-content { 
        background-color: #26262e; border-radius: 8px; padding: 10px; 
        color: #eeeeee !important; 
        line-height: 1.5;
        font-size: 0.92rem;
        height: 6.5rem; 
        overflow-y: auto;
        margin-bottom: 12px; 
        flex-shrink: 0;
    }
    
    /* 捲軸美化 */
    .sop-content::-webkit-scrollbar { width: 4px; }
    .sop-content::-webkit-scrollbar-thumb { background: #4a90e2; border-radius: 10px; }

    /* 亮黃色資訊行與 ICON */
    .sop-info-line {
        color: #ffffcd; /* 亮金色 */
        font-weight: 600;
        margin-bottom: 3px;
        display: flex;
        align-items: center;
        gap: 6px;
    }

    .sop-footer { 
        font-size: 0.8rem; 
        margin-top: auto; 
        border-top: 1px solid #3d3d3d; 
        padding-top: 8px; 
        padding-bottom: 2px; 
    }
    
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
        st.title("🛡️ SOP 知識檢索輔助系統")
        name = st.text_input("您的姓名", key="name_input")
        if st.button("🚀 進入系統 (開始計時)", use_container_width=True):
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

    st.title("🔍 SOP 智能檢索站")
    
    # --- 快捷按鈕區 ---
    st.markdown('<div class="stButtonGroup">', unsafe_allow_html=True)
    b1, b2, b3, _ = st.columns([1.2, 1.2, 1.4, 6])
    shortcut_query = None
    if b1.button("📝 請假流程"): shortcut_query = "請假流程"
    if b2.button("🔧 設備報修"): shortcut_query = "設備報修"
    if b3.button("📅 租借會議室"): shortcut_query = "租借會議室"
    st.markdown('</div>', unsafe_allow_html=True)
    
    # --- 對話歷史展示 (渲染亮黃色資訊與 ICON) ---
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if isinstance(msg["content"], list):
                cols = st.columns(3)
                for i, item in enumerate(msg["content"]):
                    with cols[i % 3]:
                        # 標題清洗邏輯：避免重複出現「步驟」
                        display_title = str(item.get('title', '執行項目')).replace("步驟", "").replace(":", "").replace("：", "").strip()
                        st.markdown(f"""
                            <div class="sop-card-box">
                                <div class="sop-step-header">步驟 {i+1}：{display_title}</div>
                                <div class="sop-content">{item.get('content', '暫無描述')}</div>
                                <div class="sop-footer">
                                    <div class="sop-info-line">👤 <b>負責：</b>{item.get('owner', '未註明')}</div>
                                    <div class="sop-info-line">⏱️ <b>時限：</b>{item.get('time', '未註明')}</div>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
            else:
                st.write(msg["content"])

    # --- 搜尋與 AI 處理邏輯 (優化 Prompt) ---
    chat_input = st.chat_input("輸入 SOP 關鍵字搜尋...")
    final_query = shortcut_query if shortcut_query else chat_input

    if final_query:
        st.session_state.messages.append({"role": "user", "content": final_query})
        with st.spinner("檢索中..."):
            if not is_query_relevant(final_query):
                st.session_state.messages.append({"role": "assistant", "content": "查無相關 SOP。"})
            else:
                context = retrieve_category_context(final_query, MY_KNOWLEDGE_BASE)
                prompt = (
                    "你是一個專業助手。請根據提供內容回答。\n"
                    f"內容：\n{context}\n"
                    f"問題：{final_query}\n"
                    "請嚴格回傳 JSON 陣列格式，規則如下：\n"
                    "1. title: 僅限動作名稱（例如：填寫申請）。禁止包含'步驟'字樣。\n"
                    "2. content: 詳細的執行說明（約 2-4 行）。\n"
                    "3. owner: 負責對象。\n"
                    "4. time: 時間限制。\n"
                    "範例：[{\"title\":\"提交申請\",\"content\":\"於系統填寫休假單並送出\",\"owner\":\"員工\",\"time\":\"3天前\"}]"
                )
                
                try:
                    res = ollama.generate(model='qwen2.5:7b', prompt=prompt, options={'temperature': 0})
                    match = re.search(r'\[\s*\{.*\}\s*\]', res['response'], re.DOTALL)
                    if match:
                        st.session_state.messages.append({"role": "assistant", "content": json.loads(match.group())})
                    else:
                        st.session_state.messages.append({"role": "assistant", "content": res['response']})
                except Exception as e:
                    st.session_state.messages.append({"role": "assistant", "content": f"系統解析錯誤: {str(e)}"})
        st.rerun()