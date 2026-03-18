import streamlit as st
import ollama
import json
import re
import os

# ==========================================
# 1. 檢索核心：精準權重與負向懲罰
# ==========================================
KNOWLEDGE_FILE = "sop_kb.md"

def load_knowledge():
    if not os.path.exists(KNOWLEDGE_FILE): return ""
    with open(KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()

MY_KNOWLEDGE_BASE = load_knowledge()

def retrieve_best_chunks(query, full_text, top_n=5):
    if not full_text: return ""
    clean_query = re.sub(r'[我想查問的流程玩看打去做的是在\s]', '', query)
    chunks = [c.strip() for c in full_text.split('##') if c.strip()]
    scored_chunks = []
    
    # 核心實體：對這些詞給予最高加成
    core_entities = ["請假", "核銷", "報銷", "會議", "訪客", "報修", "租借", "資安", "設備", "申請", "大會議室"]
    
    for chunk in chunks:
        lines = chunk.split('\n')
        header = lines[0].lower() if lines else ""
        full_content = chunk.lower()
        score = 0
        
        # A. 標題全詞命中 (解決「會議室」問題)
        if clean_query in header and len(clean_query) >= 2:
            score += 1500
            
        # B. 核心詞命中標題
        for entity in core_entities:
            if entity in query and entity in header:
                score += 800
        
        # C. 內容命中比對
        if clean_query in full_content:
            score += 100
            
        # D. 負向懲罰 (解決「玩/睡」誤觸問題)
        if any(act in query for act in ["玩", "打", "看", "睡", "睡覺"]) and \
           not any(act in full_content for act in ["玩", "打", "看", "睡", "睡覺"]):
            score -= 2000

        # 動態門檻：確保長句與短詞都能過關
        threshold = 80 if len(query) > 5 else 30
        
        if score > threshold:
            fingerprint = chunk.replace(" ", "")[:30]
            scored_chunks.append((score, "## " + chunk, fingerprint))

    unique_chunks = []
    seen = set()
    for s, c, f in sorted(scored_chunks, key=lambda x: x[0], reverse=True):
        if f not in seen:
            unique_chunks.append(c)
            seen.add(f)
            
    return "\n\n".join(unique_chunks[:top_n])

# ==========================================
# 2. UI 佈局優化 (解決切掉與遮擋問題)
# ==========================================
st.set_page_config(page_title="SOP 檢索系統", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: white; }
    
    /* 核心修正：增加底部間距防止被按鈕遮擋 */
    .main .block-container {
        padding-bottom: 250px !important;
    }

    /* 快捷按鈕容器：優化圖層與透明度 */
    div.stButtonGroup {
        position: fixed;
        bottom: 100px;
        left: 50%;
        transform: translateX(-50%);
        width: 90%;
        z-index: 1000;
        background-color: rgba(14, 17, 23, 0.9);
        padding: 12px;
        border-radius: 12px;
        backdrop-filter: blur(8px);
        border: 1px solid #333;
    }

    .sop-card-box {
        background-color: #1e1e26; border-top: 4px solid #4a90e2;
        border-radius: 12px; padding: 22px; margin-bottom: 24px;
        min-height: 280px; display: flex; flex-direction: column; justify-content: space-between;
    }
    .sop-label { color: #4a90e2; font-weight: 700; margin-bottom: 12px; border-left: 4px solid #4a90e2; padding-left: 10px; font-size: 1.1rem; }
    .sop-content { background-color: #26262e; border-radius: 8px; padding: 16px; flex-grow: 1; color: white !important; line-height: 1.6; }
    .sop-footer { font-size: 0.85rem; color: #b0b0b0; border-top: 1px solid #3d3d4d; padding-top: 10px; margin-top: 10px; }
    .footer-tag { color: #4a90e2; font-weight: bold; margin-right: 4px; }
    </style>
""", unsafe_allow_html=True)

if "messages" not in st.session_state:
    st.session_state.messages = []

# ==========================================
# 3. 側邊欄與紀錄
# ==========================================
with st.sidebar:
    st.header("🧪 測試控制台")
    tester = st.text_input("人員：", "測試員")
    if st.button("🗑️ 清除對話紀錄"):
        st.session_state.messages = []
        st.rerun()
    st.divider()
    task_id = st.radio("當前任務：", ["任務 1", "任務 2", "任務 3", "任務 4", "任務 5", "任務 6"])
    tasks = {
        "任務 1": "為了開會順利你要先預約會議室。請查出預約「大會議室」必須在使用日前幾天提出申請？",
        "任務 2": "今天因業務有外部貴賓要來拜訪你。請問訪客到達櫃台後，除了領取證件，還必須簽署什麼文件？",
        "任務 3": "你發現辦公設備故障需要報修。請查出「技術員初步檢測」步驟的時限要求為何？",
        "任務 4": "工作累了你想出國15天需要請長假。請查出「關鍵層級審核」是由哪個職位負責審批？",
        "任務 5": "今天會議流程較長且討論熱烈，預計會比原定時間多出 40 分鐘。根據規範，你這時必須執行哪項動作？",
        "任務 6": "當你陪同訪客要離開到達櫃台時，保全人員必須執行哪兩項資安檢查重點？"
    }
    st.info(f"題目：\n{tasks[task_id]}")
    execute_task = st.button("🚀 執行任務題目")

st.title("🛡️ 知識檢索輔助系統")

# ==========================================
# 4. 主畫面渲染與解析防錯 (修正 None 問題)
# ==========================================
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.write(f"💬 **問題：{msg['content']}**")
        else:
            steps = msg["content"]
            if isinstance(steps, list) and len(steps) > 0:
                cols = st.columns(3)
                for idx, item in enumerate(steps):
                    # --- 終極修正：強制容錯映射 ---
                    t = item.get("title") or item.get("標題") or "詳細步驟"
                    c = item.get("content") or item.get("step") or item.get("描述") or item.get("內容") or "無詳細內容"
                    o = item.get("owner") or item.get("負責人") or "相關人員"
                    tm = item.get("time") or item.get("deadline") or item.get("時限") or "依規定"
                    
                    with cols[idx % 3]:
                        st.markdown(f"""<div class="sop-card-box">
                            <div>
                                <div class="sop-label">步驟 {idx+1}：{t}</div>
                                <div class="sop-content">{c}</div>
                            </div>
                            <div class="sop-footer">
                                <span class="footer-tag">👤 負責：</span>{o}<br>
                                <span class="footer-tag">⏳ 時限：</span>{tm}
                            </div>
                        </div>""", unsafe_allow_html=True)
            else:
                st.warning("⚠️ 檢索不到相關內容。建議嘗試簡化關鍵字（如：大會議室）。")

# 底部按鈕
st.markdown('<div class="stButtonGroup">', unsafe_allow_html=True)
b1, b2, b3, _ = st.columns([1.2, 1.2, 1.4, 6])
shortcut = None
if b1.button("📝 請假流程"): shortcut = "請假流程"
if b2.button("🔧 設備報修"): shortcut = "設備報修"
if b3.button("📅 租借會議室"): shortcut = "租借會議室"
st.markdown('</div>', unsafe_allow_html=True)

# 輸入處理
query = None
if execute_task: query = tasks[task_id]
elif shortcut: query = shortcut
elif p := st.chat_input("輸入關鍵字 (如：報修、大會議室)..."): query = p

if query:
    st.session_state.messages.append({"role": "user", "content": query})
    with st.spinner("AI 正在解析繁體 SOP..."):
        context = retrieve_best_chunks(query, MY_KNOWLEDGE_BASE)
        if context:
            prompt = f"""你是一個 SOP 專家。根據提供內容提取具體步驟。
            若內容無關，請回傳空陣列 []。
            必須回傳 JSON 陣列，欄位名稱固定為: "title", "content", "owner", "time"。
            
            參考內容：
            {context}

            問題："{query}"
            """
            try:
                res = ollama.generate(model='qwen2.5:7b', prompt=prompt, options={'temperature': 0})
                raw = res['response']
                match = re.search(r'\[.*\]', raw, re.DOTALL)
                data = json.loads(match.group()) if match else []
                st.session_state.messages.append({"role": "assistant", "content": data})
            except:
                st.session_state.messages.append({"role": "assistant", "content": []})
        else:
            st.session_state.messages.append({"role": "assistant", "content": []})
    st.rerun()