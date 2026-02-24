import streamlit as st
import data_loader
import google.generativeai as genai
import os
import json
from dotenv import load_dotenv

# --- Config ---
st.set_page_config(
    page_title="社科 AI 助教",
    page_icon="🎓",
    layout="centered",
    initial_sidebar_state="auto",
)
load_dotenv()

# --- PWA & Mobile Meta Tags ---
st.markdown("""
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<meta name="theme-color" content="#1a1a2e">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="社科AI助教">
<meta name="description" content="您的個人化社會學 AI 助教 - 隨時練習，即時批改">
<style>
    /* Mobile-friendly improvements */
    .stButton > button {
        width: 100%;
        padding: 0.75rem 1rem;
        font-size: 1.05rem;
        border-radius: 12px;
        font-weight: 600;
    }
    .stRadio > div {
        gap: 0.5rem;
    }
    .stTextArea textarea {
        font-size: 1rem;
        min-height: 120px;
    }
    @media (max-width: 768px) {
        .stSidebar { font-size: 1rem; }
        h1 { font-size: 1.6rem !important; }
    }
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

# --- Helper Functions ---
def generate_quiz(topic_text):
    """Generates a quiz using Gemini in JSON format."""
    prompt = f"""
    You are a professional Sociology Tutor. 
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
    Focus on sociology concepts.
    """
    response = model.generate_content(prompt)
    return response.text

# --- UI Layout ---
st.title("🎓 Exam_Tutor AI (中文版)")
st.caption("您的個人化社會學 AI 助教")

# 1. Sidebar: Select Topic
materials = data_loader.load_materials()
if not materials:
    st.error("在 'materials/' 資料夾中找不到講義檔案")
    st.stop()

topic_list = list(materials.keys())
selected_topic = st.sidebar.selectbox("📚 選擇單元/週次", topic_list)

# --- Mobile Install Tip ---
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


# Reset state if topic changes
if selected_topic != st.session_state.current_topic:
    st.session_state.current_topic = selected_topic
    st.session_state.quiz_data = None
    st.session_state.user_answers = {}
    st.session_state.graded = False

# 2. Main Area: Generate Button
if st.session_state.quiz_data is None:
    st.info(f"準備練習單元: **{selected_topic}**")
    if st.button("🚀 開始測驗 (Start Quiz)", type="primary"):
        with st.spinner("🤖 AI 正在閱讀講義並出題中..."):
            text_content = materials[selected_topic]
            quiz = generate_quiz(text_content)
            if quiz:
                st.session_state.quiz_data = quiz
                st.rerun()

# 3. Quiz Area
if st.session_state.quiz_data:
    quiz = st.session_state.quiz_data
    
    with st.form("quiz_form"):
        st.subheader("第一部分: 選擇題 (MCQ)")
        
        # MCQs
        mcq_answers = {}
        for i, q in enumerate(quiz["mcq"]):
            st.markdown(f"**{i+1}. {q['q']}**")
            # Streamlit radio returns the string value of the option
            mcq_answers[i] = st.radio(f"請選擇第 {i+1} 題答案", q['options'], key=f"mcq_{i}", label_visibility="collapsed")
            st.markdown("---")
            
        st.subheader("第二部分: 簡答題 (Short Answer)")
        
        # SAs
        sa_answers = {}
        for i, q in enumerate(quiz["sa"]):
            st.markdown(f"**{i+1}. {q['q']}**")
            sa_answers[i] = st.text_area("您的回答:", key=f"sa_{i}")

        submitted = st.form_submit_button("📝 提交並評分 (Submit)")
        
        if submitted:
            st.session_state.graded = True
            st.session_state.user_answers = {"mcq": mcq_answers, "sa": sa_answers}

# 4. Grading Results
if st.session_state.graded and st.session_state.quiz_data:
    st.divider()
    st.header("📊 成績與回饋")
    
    quiz = st.session_state.quiz_data
    u_ans = st.session_state.user_answers
    
    # Grade MCQs
    score = 0
    total = len(quiz["mcq"])
    
    for i, q in enumerate(quiz["mcq"]):
        user_choice = u_ans["mcq"][i] # String "A) ..."
        correct_choice = q['options'][q['correct_index']]
        
        if user_choice == correct_choice:
            score += 1
            st.success(f"第 {i+1} 題: 答對了！ ✅")
        else:
            st.error(f"第 {i+1} 題: 錯誤 ❌")
            st.markdown(f"- **您的答案**: {user_choice}")
            st.markdown(f"- **正確答案**: {correct_choice}")
            
    st.metric("選擇題得分", f"{score}/{total}")
    
    # Grade SA
    st.subheader("簡答題 AI 回饋")
    for i, q in enumerate(quiz["sa"]):
        user_text = u_ans["sa"][i]
        if not user_text.strip():
            st.warning("未填寫答案")
            continue
            
        with st.spinner("AI 正在批改您的簡答題..."):
            feedback = grade_sa(q['q'], user_text, q['reference_answer'])
            
        st.info(f"**題目**: {q['q']}")
        st.markdown(f"**AI 評語**: \n{feedback}")
        with st.expander("查看講義參考重點"):
            st.markdown(q['reference_answer'])
            
    if st.button("🔄 練習其他單元"):
        st.session_state.quiz_data = None
        st.session_state.graded = False
        st.rerun()
