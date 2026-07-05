import streamlit as st
import data_loader
import google.generativeai as genai
import os
import json
from dotenv import load_dotenv

# --- Load Config ---
config = data_loader.load_config()
subject_name = config.get("subject_name", "社會學")
assistant_role = config.get("assistant_role", "專業社會學助教")
focus_instruction = config.get("focus_instruction", "請著重於社會學理論、學派（如結構功能論、衝突論、符號互動論）及學者觀點之應用。")

# --- Config ---
st.set_page_config(
    page_title=f"{subject_name} AI 助教",
    page_icon="🎓",
    layout="centered",
    initial_sidebar_state="auto",
)
load_dotenv()

# --- PWA & Mobile Meta Tags ---
st.markdown(f"""
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<meta name="theme-color" content="#1a1a2e">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="{subject_name}AI助教">
<meta name="description" content="您的個人化{subject_name} AI 助教 - 隨時練習，即時批改">
<style>
    /* Mobile-friendly improvements */
    .stButton > button {{
        width: 100%;
        padding: 0.75rem 1rem;
        font-size: 1.05rem;
        border-radius: 12px;
        font-weight: 600;
    }}
    .stRadio > div {{
        gap: 0.5rem;
    }}
    .stTextArea textarea {{
        font-size: 1rem;
        min-height: 120px;
    }}
    @media (max-width: 768px) {{
        .stSidebar {{ font-size: 1rem; }}
        h1 {{ font-size: 1.6rem !important; }}
    }}
</style>
""", unsafe_allow_html=True)

# --- API Setup ---
# Priority 1: Streamlit Secrets (Cloud deployment)
try:
    api_key = st.secrets.get("GEMINI_API_KEY", None)
except Exception:
    api_key = None

# Priority 2: Environment Variable (.env for local dev)
if not api_key:
    api_key = os.getenv("GEMINI_API_KEY")

# Priority 3: User input in sidebar
if not api_key:
    with st.sidebar:
        st.markdown("### ⚙️ 設定")
        api_key = st.text_input("Gemini API Key", type="password", help="請輸入您的 Google Gemini API Key")
        if not api_key:
            st.warning("請輸入您的 Gemini API Key 以繼續")
            st.stop()

# --- Model Setup ---
def get_available_model():
    """Finds the best available model from the API."""
    try:
        # List all models that support generation
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
        
        # Priority list
        priorities = ['models/gemini-1.5-flash', 'models/gemini-1.5-pro', 'models/gemini-pro']
        
        for p in priorities:
            if p in available_models:
                return p
        
        # Fallback to the first available if none of the above match
        if available_models:
            return available_models[0]
            
        return "models/gemini-pro" # Ultimate fallback
    except Exception as e:
        # If list_models fails (e.g. old lib), fallback to simple string
        return "gemini-pro"

# Configure Model
genai.configure(api_key=api_key)

# Select Model
model_name = get_available_model()
# st.toast(f"Using AI Model: {model_name}") # Optional: Notify user
model = genai.GenerativeModel(model_name)


# --- Session State Management ---
if "current_topic" not in st.session_state:
    st.session_state.current_topic = None
if "quiz_data" not in st.session_state:
    st.session_state.quiz_data = None
if "user_answers" not in st.session_state:
    st.session_state.user_answers = {}
if "graded" not in st.session_state:
    st.session_state.graded = False
# 模擬考模式 session state
if "mock_questions" not in st.session_state:
    st.session_state.mock_questions = None
if "mock_answers" not in st.session_state:
    st.session_state.mock_answers = {}
if "mock_graded" not in st.session_state:
    st.session_state.mock_graded = False

# --- Helper Functions ---
def generate_quiz(topic_text):
    """Generates a quiz using Gemini in JSON format."""
    prompt = f"""
    You are a professional {assistant_role} for the course '{subject_name}'. 
    Based on the following course material, generate a quiz in **Traditional Chinese (繁體中文)**.
    
    Content:
    {topic_text[:20000]}  # Limit char count to safe range
    
    Requirements:
    1. 3 Multiple Choice Questions (MCQ) with 4 options.
    2. 1 Short Answer Question (SA).
    3. **ALL Content must be in Traditional Chinese (TW).**
    
    Output STRICT JSON format:
    {{
        "mcq": [
            {{
                "q": "題目內容...",
                "options": ["A) 選項 1", "B) 選項 2", "C) ...", "D) ..."],
                "correct_index": 0  (0 for A, 1 for B, etc.)
            }}
        ],
        "sa": [
            {{
                "q": "題目內容...",
                "reference_answer": "參考答案重點..."
            }}
        ]
    }}
    """
    try:
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        return json.loads(response.text)
    except Exception as e:
        st.error(f"生成測驗時發生錯誤: {e}")
        return None

def grade_sa(question, student_answer, reference):
    """Uses AI to grade the short answer."""
    prompt = f"""
    You are a Teacher grading a student's answer.
    
    Question: {question}
    Reference Answer (from material): {reference}
    Student Answer: {student_answer}
    
    Task:
    Provide a concise evaluation (Pass/Fail) and constructive feedback/correction. 
    **Reply in Traditional Chinese (繁體中文).**
    Focus on {subject_name} concepts. {focus_instruction}
    """
    response = model.generate_content(prompt)
    return response.text


@st.cache_data(ttl=300)
def load_question_bank():
    """載入考古題題庫（快取 5 分鐘）"""
    bank_path = "question_bank.json"
    if not os.path.exists(bank_path):
        return None
    try:
        with open(bank_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"讀取題庫失敗：{e}")
        return None

# --- UI Layout ---
st.title(f"🎓 {subject_name} AI 助教")
st.caption(f"您的個人化{subject_name} AI 學習助理")

# ── 側邊欄：單元選擇（供 Tab 1 使用）──
materials = data_loader.load_materials()
if not materials:
    st.error("在 'materials/' 資料夾中找不到講義檔案")
    st.stop()

topic_list = list(materials.keys())
selected_topic = st.sidebar.selectbox("📚 選擇單元/週次", topic_list)

with st.sidebar.expander("📲 加到手機主畫面"):
    st.markdown("""
**iPhone (iOS Safari)**
1. 點下方 **分享** 按鈕 `⬆`
2. 選擇「**加入主畫面**」
3. 按「新增」完成 ✅

**Android (Chrome)**
1. 點右上角 **⋮** 選單
2. 選擇「**新增至主畫面**」
3. 按「新增」完成 ✅

加完後可像 App 一樣從主畫面直接開啟！
    """)

# 切換單元時重置狀態
if selected_topic != st.session_state.current_topic:
    st.session_state.current_topic = selected_topic
    st.session_state.quiz_data = None
    st.session_state.user_answers = {}
    st.session_state.graded = False

# ── 主分頁 ──
tab1, tab2 = st.tabs(["📖 單元練習", "🏆 模擬考模式（考選部考古題）"])

# ══════════════════════════════════════════════
# TAB 1：單元練習（原有功能）
# ══════════════════════════════════════════════
with tab1:
    if st.session_state.quiz_data is None:
        st.info(f"準備練習單元：**{selected_topic}**")
        if st.button("🚀 開始測驗 (Start Quiz)", type="primary"):
            with st.spinner("🤖 AI 正在閱讀講義並出題中..."):
                text_content = materials[selected_topic]
                quiz = generate_quiz(text_content)
                if quiz:
                    st.session_state.quiz_data = quiz
                    st.rerun()

    if st.session_state.quiz_data:
        quiz = st.session_state.quiz_data

        with st.form("quiz_form"):
            st.subheader("第一部分: 選擇題 (MCQ)")

            mcq_answers = {}
            for i, q in enumerate(quiz["mcq"]):
                st.markdown(f"**{i+1}. {q['q']}**")
                mcq_answers[i] = st.radio(
                    f"請選擇第 {i+1} 題答案",
                    q["options"],
                    key=f"mcq_{i}",
                    label_visibility="collapsed",
                )
                st.markdown("---")

            st.subheader("第二部分: 簡答題 (Short Answer)")

            sa_answers = {}
            for i, q in enumerate(quiz["sa"]):
                st.markdown(f"**{i+1}. {q['q']}**")
                sa_answers[i] = st.text_area("您的回答:", key=f"sa_{i}")

            submitted = st.form_submit_button("📝 提交並評分 (Submit)")
            if submitted:
                st.session_state.graded = True
                st.session_state.user_answers = {"mcq": mcq_answers, "sa": sa_answers}

    if st.session_state.graded and st.session_state.quiz_data:
        st.divider()
        st.header("📊 成績與回饋")

        quiz  = st.session_state.quiz_data
        u_ans = st.session_state.user_answers

        score = 0
        total = len(quiz["mcq"])

        for i, q in enumerate(quiz["mcq"]):
            user_choice    = u_ans["mcq"][i]
            correct_choice = q["options"][q["correct_index"]]
            if user_choice == correct_choice:
                score += 1
                st.success(f"第 {i+1} 題: 答對了！ ✅")
            else:
                st.error(f"第 {i+1} 題: 錯誤 ❌")
                st.markdown(f"- **您的答案**: {user_choice}")
                st.markdown(f"- **正確答案**: {correct_choice}")

        st.metric("選擇題得分", f"{score}/{total}")

        st.subheader("簡答題 AI 回饋")
        for i, q in enumerate(quiz["sa"]):
            user_text = u_ans["sa"][i]
            if not user_text.strip():
                st.warning("未填寫答案")
                continue
            with st.spinner("AI 正在批改您的簡答題..."):
                feedback = grade_sa(q["q"], user_text, q["reference_answer"])
            st.info(f"**題目**: {q['q']}")
            st.markdown(f"**AI 評語**: \n{feedback}")
            with st.expander("查看講義參考重點"):
                st.markdown(q["reference_answer"])

        if st.button("🔄 練習其他單元"):
            st.session_state.quiz_data = None
            st.session_state.graded    = False
            st.rerun()


# ══════════════════════════════════════════════
# TAB 2：模擬考模式（歷屆考古題）
# ══════════════════════════════════════════════
with tab2:
    st.subheader("🏆 模擬考模式")
    st.caption(f"題目來源：歷屆{subject_name}考古題（依題庫來源而定）")

    bank = load_question_bank()

    # ── 未建立題庫 → 顯示建立說明 ──
    if not bank or bank["metadata"]["total"] == 0:
        st.warning("📭 題庫尚未建立，請依下列步驟操作：")
        st.markdown(f"""
### 📋 建立題庫（一次性設定）

**Step 1｜安裝新套件**
```bash
pip install pdfplumber requests beautifulsoup4
```

**Step 2｜下載歷屆試題 PDF**
```bash
python moex_scraper.py
```
> 預計下載該專業領域的 {subject_name} 試題

**Step 3｜AI 解析 PDF → 建立題庫**
```bash
python pdf_to_questions.py
```

完成後重新整理此頁即可使用 🎯
        """)

    else:
        # ── 題庫統計 ──
        questions    = bank["questions"]
        total_q      = bank["metadata"]["total"]
        sources_cnt  = len(bank["metadata"].get("sources", []))
        last_updated = bank["metadata"].get("last_updated", "未知")
        if last_updated and "T" in str(last_updated):
            last_updated = last_updated[:10]

        col_a, col_b, col_c = st.columns(3)
        col_a.metric("📚 題庫總題數", f"{total_q} 題")
        col_b.metric("📄 考試份數",   f"{sources_cnt} 份")
        col_c.metric("🔄 最後更新",   last_updated)

        st.divider()

        # ── 出題設定 ──
        st.markdown("### ⚙️ 出題設定")
        ctrl1, ctrl2, ctrl3 = st.columns(3)

        with ctrl1:
            n_questions = st.selectbox(
                "📝 出題數",
                [4, 8, 12, "全部"],
                index=0,
                key="mock_n",
            )

        with ctrl2:
            all_years = sorted({q["year"] for q in questions if q.get("year")})
            if len(all_years) >= 2:
                year_range = st.select_slider(
                    "📅 年度範圍（民國年）",
                    options=all_years,
                    value=(min(all_years), max(all_years)),
                    key="mock_year",
                )
            elif all_years:
                year_range = (all_years[0], all_years[0])
                st.info(f"年度：{all_years[0]} 年")
            else:
                year_range = (0, 999)

        with ctrl3:
            all_categories = ["全部"] + sorted({
                q.get("exam_category", "") for q in questions if q.get("exam_category")
            })
            selected_cat = st.selectbox(
                "🏛️ 考試類型",
                all_categories,
                key="mock_cat",
            )

        # ── 篩選題目 ──
        filtered_qs = [
            q for q in questions
            if (year_range[0] <= q.get("year", 0) <= year_range[1])
            and (selected_cat == "全部" or q.get("exam_category") == selected_cat)
        ]

        if not filtered_qs:
            st.warning("⚠️ 無符合條件的題目，請調整篩選條件")
        else:
            n = len(filtered_qs) if n_questions == "全部" else min(int(n_questions), len(filtered_qs))
            st.info(f"符合條件：{len(filtered_qs)} 題，本次將隨機抽取 **{n}** 題")

            # 尚未開考 → 顯示開始按鈕
            if not st.session_state.mock_questions:
                if st.button("🎯 抽題開始模擬考", type="primary", key="start_mock"):
                    import random
                    st.session_state.mock_questions = random.sample(filtered_qs, n)
                    st.session_state.mock_answers   = {}
                    st.session_state.mock_graded    = False
                    st.rerun()

        # ── 作答區 ──
        if st.session_state.mock_questions and not st.session_state.mock_graded:
            mock_qs = st.session_state.mock_questions
            st.divider()
            st.subheader(f"📋 模擬考卷（共 {len(mock_qs)} 題）")

            with st.form("mock_form"):
                temp_ans = {}
                for i, q in enumerate(mock_qs):
                    yr  = f"{q.get('year', '?')} 年" if q.get("year") else ""
                    cat = q.get("exam_category", "")
                    st.markdown(f"**第 {i+1} 題** `{yr} · {cat}`")
                    st.markdown(f"**{q['q']}**")
                    opts = q.get("options", [])
                    if opts and q.get("type") != "essay":
                        temp_ans[i] = st.radio(
                            f"答案 {i+1}",
                            opts,
                            key=f"mock_q_{i}",
                            label_visibility="collapsed",
                        )
                    else:
                        temp_ans[i] = st.text_area(
                            "請輸入您的申論作答",
                            key=f"mock_q_{i}",
                            height=150,
                        )
                    st.markdown("---")

                if st.form_submit_button("📤 交卷評分", type="primary"):
                    st.session_state.mock_answers = temp_ans
                    st.session_state.mock_graded  = True
                    st.rerun()

        # ── 成績與解析 ──
        if st.session_state.mock_graded and st.session_state.mock_questions:
            mock_qs  = st.session_state.mock_questions
            mock_ans = st.session_state.mock_answers

            st.divider()
            st.header("📊 模擬考成績單")

            # 計算選擇題得分
            mcq_qs = [q for q in mock_qs if q.get("type") != "essay"]
            score = sum(
                1 for i, q in enumerate(mock_qs)
                if q.get("type") != "essay" and mock_ans.get(i, "") == q.get("options", [""])[q.get("correct_index", 0)]
            )
            
            if mcq_qs:
                pct = score / len(mcq_qs) * 100
                m1, m2, m3 = st.columns(3)
                m1.metric("🎯 選擇題得分",   f"{score} / {len(mcq_qs)}")
                m2.metric("📈 選擇題正確率",  f"{pct:.1f}%")
                m3.metric("📅 涵蓋年份", f"{len({q.get('year') for q in mock_qs if q.get('year')})} 年")

                if pct >= 80:
                    st.success("🎉 選擇題表現優秀！")
                elif pct >= 60:
                    st.info("👍 選擇題及格！繼續加油！")
                else:
                    st.error("📖 選擇題未達 60%，建議多加複習。")
            else:
                st.info("本次測驗全為申論題，請參考下方 AI 評分與解析。")
                st.metric("📅 涵蓋年份", f"{len({q.get('year') for q in mock_qs if q.get('year')})} 年")

            # 逐題解析與評分
            st.subheader("📝 逐題解析與 AI 評分")
            for i, q in enumerate(mock_qs):
                user_ans    = mock_ans.get(i, "")
                is_essay    = q.get("type") == "essay"
                yr   = f"{q.get('year', '?')} 年" if q.get("year") else ""
                cat  = q.get("exam_category", "")

                with st.expander(f"第 {i+1} 題 — {yr} {cat}", expanded=is_essay):
                    st.markdown(f"**題目：** {q['q']}")
                    
                    if is_essay:
                        st.info(f"**您的作答：**\n{user_ans if user_ans.strip() else '（未作答）'}")
                        if q.get("explanation"):
                            st.success(f"**考點解析：**\n{q['explanation']}")
                        if user_ans.strip():
                            with st.spinner("AI 批改中..."):
                                ai_feedback = grade_sa(q['q'], user_ans, q.get("explanation", ""))
                                st.warning(f"**🤖 AI 評分與建議：**\n{ai_feedback}")
                    else:
                        correct_ans = q.get("options", [""])[q.get("correct_index", 0)]
                        is_correct  = user_ans == correct_ans
                        if is_correct:
                            st.success(f"**您的答案：** {user_ans} ✅")
                        else:
                            st.error(f"**您的答案：** {user_ans} ❌")
                            st.success(f"**正確答案：** {correct_ans}")
                        if q.get("explanation"):
                            st.info(f"**解析：** {q['explanation']}")

            # 操作按鈕
            btn1, btn2 = st.columns(2)
            with btn1:
                if st.button("🔄 重新抽題再考", key="retry_mock"):
                    st.session_state.mock_questions = None
                    st.session_state.mock_graded    = False
                    st.session_state.mock_answers   = {}
                    st.rerun()
            with btn2:
                if st.button("⚙️ 重設篩選條件", key="reset_mock"):
                    st.session_state.mock_questions = None
                    st.session_state.mock_graded    = False
                    st.session_state.mock_answers   = {}
                    st.rerun()
