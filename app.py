import os
import json
import base64
import io
import uuid
import requests
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

# =====================================
# 1. CONFIGURATION
# =====================================
load_dotenv()

def get_setting(name, default=""):
    try:
        value = st.secrets.get(name, None)
        if value is not None:
            return str(value)
    except Exception:
        pass
    return os.getenv(name, default)

CANVAS_URL = get_setting("CANVAS_API_URL").rstrip("/")
CANVAS_TOKEN = get_setting("CANVAS_API_TOKEN")
OPENAI_API_KEY = get_setting("OPENAI_API_KEY")

st.set_page_config(
    page_title="My Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

if not OPENAI_API_KEY:
    st.error("OpenAI API key is missing. Add OPENAI_API_KEY in Streamlit Secrets or your local .env file.")
    st.stop()

client = OpenAI(api_key=OPENAI_API_KEY)

# =====================================
# 2. SESSION STATE
# =====================================
def new_conversation():
    return {
        "id": str(uuid.uuid4()),
        "title": "New chat",
        "messages": [],
    }

defaults = {
    "language": "English",
    "section": "Home",
    "conversations": [],
    "active_conversation_id": None,
    "courses": [],
    "voice_enabled": True,
    "projects": [],
    "active_project_id": None,
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

if not st.session_state.conversations:
    first_chat = new_conversation()
    st.session_state.conversations = [first_chat]
    st.session_state.active_conversation_id = first_chat["id"]

def get_active_conversation():
    for conversation in st.session_state.conversations:
        if conversation["id"] == st.session_state.active_conversation_id:
            return conversation
    conversation = new_conversation()
    st.session_state.conversations.insert(0, conversation)
    st.session_state.active_conversation_id = conversation["id"]
    return conversation

def start_new_chat():
    conversation = new_conversation()
    st.session_state.conversations.insert(0, conversation)
    st.session_state.active_conversation_id = conversation["id"]
    st.session_state.section = "Home"

# =====================================
# 3. LANGUAGE
# =====================================
LANGUAGES = {
    "English": {
        "welcome": "Welcome to My Assistant",
        "subtitle": "Your Personal AI Workspace",
        "study": "Study",
        "canvas": "Canvas",
        "trading": "Trading",
        "projects": "Projects",
        "study_desc": "Courses and research",
        "canvas_desc": "Courses and assignments",
        "trading_desc": "Market analysis",
        "projects_desc": "Your files and projects",
        "placeholder": "Ask me anything...",
        "send": "Send",
        "upload": "Upload files and images",
        "thinking": "Thinking...",
        "new_chat": "＋ New chat",
        "history": "Your conversations",
        "home": "Home",
        "back": "← Home",
        "choose_course": "Select a Canvas course",
        "refresh_courses": "Refresh courses",
        "no_courses": "No active Canvas courses were found.",
        "canvas_setup": "Canvas connection is not configured. Add CANVAS_API_URL and CANVAS_API_TOKEN in Streamlit Secrets.",
        "projects_title": "Your Projects",
        "project_name": "New project name",
        "add_project": "Add project",
        "open_project": "Open",
        "project_empty": "You have not created any projects yet.",
        "voice_error": "Voice transcription error",
        "voice_recognized": "Voice message transcribed",
        "voice_settings": "Voice settings",
        "spoken_replies": "Enable spoken responses",
        "clear_chat": "Delete this conversation",
        "language": "Language",
        "connections_missing": "Canvas is not connected.",
    },
    "العربية": {
        "welcome": "مرحباً بك في مساعدك الشخصي",
        "subtitle": "مساحة العمل الذكية الخاصة بك",
        "study": "الدراسة",
        "canvas": "كانفس",
        "trading": "التداول",
        "projects": "المشاريع",
        "study_desc": "المقررات والأبحاث",
        "canvas_desc": "المقررات والواجبات",
        "trading_desc": "تحليل الأسواق",
        "projects_desc": "ملفاتك ومشاريعك",
        "placeholder": "اكتب سؤالك هنا...",
        "send": "إرسال",
        "upload": "رفع الملفات والصور",
        "thinking": "جاري التفكير...",
        "new_chat": "＋ محادثة جديدة",
        "history": "المحادثات السابقة",
        "home": "الرئيسية",
        "back": "← الرئيسية",
        "choose_course": "اختر مقرراً من Canvas",
        "refresh_courses": "تحديث المقررات",
        "no_courses": "لم يتم العثور على مقررات نشطة في Canvas.",
        "canvas_setup": "إعدادات Canvas غير مكتملة. أضف CANVAS_API_URL و CANVAS_API_TOKEN إلى Streamlit Secrets.",
        "projects_title": "مشاريعك",
        "project_name": "اسم المشروع الجديد",
        "add_project": "إضافة مشروع",
        "open_project": "فتح",
        "project_empty": "لم تقم بإنشاء مشاريع بعد.",
        "voice_error": "حدث خطأ في تحويل الصوت إلى نص",
        "voice_recognized": "تم تحويل الرسالة الصوتية إلى نص",
        "voice_settings": "إعدادات الصوت",
        "spoken_replies": "تفعيل الردود الصوتية",
        "clear_chat": "حذف هذه المحادثة",
        "language": "اللغة",
        "connections_missing": "اتصال Canvas غير متوفر.",
    },
}
T = LANGUAGES[st.session_state.language]

# =====================================
# 4. CANVAS CONNECTION AND TOOLS
# =====================================
CANVAS_HEADERS = {"Authorization": f"Bearer {CANVAS_TOKEN}"} if CANVAS_TOKEN else {}

def canvas_get(endpoint, params=None):
    if not CANVAS_URL or not CANVAS_TOKEN:
        raise RuntimeError(T["canvas_setup"])
    response = requests.get(
        f"{CANVAS_URL}/api/v1/{endpoint}",
        headers=CANVAS_HEADERS,
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()

@st.cache_data(ttl=60)
def get_courses():
    return canvas_get("courses", {"enrollment_state": "active", "per_page": 100})

def get_modules(course_id):
    return canvas_get(f"courses/{course_id}/modules", {"per_page": 100})

def get_pages(course_id):
    return canvas_get(f"courses/{course_id}/pages", {"per_page": 100})

CANVAS_TOOLS = [
    {
        "type": "function",
        "name": "get_course_modules",
        "description": "Get modules from the selected Canvas course.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_course_pages",
        "description": "Get pages from the selected Canvas course.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    },
]

# =====================================
# 5. FILE AND VOICE HELPERS
# =====================================
def read_document(file):
    name = file.name.lower()
    data = file.getvalue()
    try:
        if name.endswith((".txt", ".csv")):
            return data.decode("utf-8", errors="replace")
        if name.endswith(".pdf"):
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        if name.endswith(".docx"):
            from docx import Document
            doc = Document(io.BytesIO(data))
            return "\n".join(p.text for p in doc.paragraphs)
        if name.endswith(".xlsx"):
            from openpyxl import load_workbook
            workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            output = []
            for sheet in workbook.worksheets:
                output.append(f"Sheet: {sheet.title}")
                for row in sheet.iter_rows(values_only=True):
                    output.append(" | ".join(str(v) if v is not None else "" for v in row))
            return "\n".join(output)
        if name.endswith(".pptx"):
            from pptx import Presentation
            presentation = Presentation(io.BytesIO(data))
            output = []
            for number, slide in enumerate(presentation.slides, 1):
                output.append(f"Slide {number}")
                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        output.append(shape.text)
            return "\n".join(output)
        return "This file format needs conversion or a dedicated reader."
    except Exception as error:
        return f"File reading error: {error}"

def prepare_images(files):
    images = []
    for file in files or []:
        if file.type not in ["image/png", "image/jpeg", "image/webp"]:
            continue
        encoded = base64.b64encode(file.getvalue()).decode("utf-8")
        images.append({
            "type": "input_image",
            "image_url": f"data:{file.type};base64,{encoded}",
            "detail": "auto",
        })
    return images

def transcribe_audio(audio):
    audio.seek(0)
    result = client.audio.transcriptions.create(
        model="gpt-4o-mini-transcribe",
        file=audio,
    )
    return result.text

def generate_speech(text):
    result = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice="marin",
        input=text,
    )
    return result.content

# =====================================
# 6. AI ENGINE
# =====================================
def run_assistant(prompt, course, files, messages):
    course_name = course.get("name", "No Canvas course selected") if course else "No Canvas course selected"
    course_id = course.get("id") if course else None

    instructions = f"""
You are My Assistant, a professional personal AI assistant.
You are bilingual in Arabic and English. Respond in the language used by the user.

Your responsibilities include:
- Academic studies and PhD research.
- Digital Transformation.
- Canvas course assistance.
- Trading education and market analysis.
- Project management.
- Document and image analysis.
- Writing and translation.

Selected Canvas course: {course_name}
Course ID: {course_id if course_id else "None"}

Canvas modules and pages tools are available only when a Canvas course is selected.
Never claim an action succeeded unless it did.
Never edit, delete, grade, or publish Canvas content without explicit user approval.
"""

    document_context = ""
    images = []
    for file in files or []:
        if file.type.startswith("image/"):
            images.extend(prepare_images([file]))
        elif file.type.startswith("audio/"):
            continue
        else:
            document_context += f"\n\nFILE: {file.name}\n{read_document(file)}\n"

    user_content = [{
        "type": "input_text",
        "text": f"{prompt}\n\nAttached document contents:\n{document_context}",
    }]
    user_content.extend(images)

    history = [{"role": m["role"], "content": m["content"]} for m in messages]
    history.append({"role": "user", "content": user_content})

    tools = CANVAS_TOOLS if course_id else []
    response = client.responses.create(
        model="gpt-5.5",
        instructions=instructions,
        input=history,
        tools=tools,
    )

    for _ in range(5):
        calls = [item for item in response.output if item.type == "function_call"]
        if not calls:
            break
        outputs = []
        for call in calls:
            try:
                if not course_id:
                    output = {"error": "No Canvas course selected."}
                elif call.name == "get_course_modules":
                    result = get_modules(course_id)
                    output = [{"id": item.get("id"), "name": item.get("name")} for item in result]
                elif call.name == "get_course_pages":
                    result = get_pages(course_id)
                    output = [{"title": item.get("title"), "url": item.get("url")} for item in result]
                else:
                    output = {"error": "Unknown tool"}
            except Exception as error:
                output = {"error": str(error)}
            outputs.append({
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": json.dumps(output, ensure_ascii=False),
            })
        response = client.responses.create(
            model="gpt-5.5",
            instructions=instructions,
            input=history + list(response.output) + outputs,
            tools=tools,
        )
    return response.output_text or "No response generated."

# =====================================
# 7. INTERFACE STYLE
# =====================================
st.markdown("""
<style>
.stApp { background: #F7F9FD; color: #26344D; }
.block-container { max-width: 1450px; padding-top: 1.5rem; }
section[data-testid="stSidebar"] {
    background: #FFFFFF;
    border-right: 1px solid #E7ECF5;
}
h1, h2, h3 { color: #263F68 !important; font-weight: 700 !important; }
.stButton > button {
    background: #EEF4FF; color: #315A9D;
    border: 1px solid #DCE6F7; border-radius: 12px;
    min-height: 44px; font-weight: 600;
}
.stButton > button:hover { background: #DDEAFF; border-color: #B8CDEE; }
.stTextInput input { border-radius: 12px; }
.stChatMessage {
    background: white; border: 1px solid #E7ECF5;
    border-radius: 16px; padding: 14px;
}
[data-testid="stFileUploader"] {
    background: white; border: 1px dashed #B9CBE9;
    border-radius: 14px; padding: 10px;
}
</style>
""", unsafe_allow_html=True)

# =====================================
# 8. SIDEBAR: LANGUAGE + CHAT HISTORY
# =====================================
with st.sidebar:
    st.markdown("# 🤖 My Assistant")
    st.caption("Your Personal AI Workspace")
    st.divider()

    language = st.selectbox(
        T["language"],
        ["English", "العربية"],
        index=0 if st.session_state.language == "English" else 1,
        key="language_selector",
    )
    if language != st.session_state.language:
        st.session_state.language = language
        st.rerun()

    st.divider()

    if st.button(T["new_chat"], use_container_width=True, type="primary"):
        start_new_chat()
        st.rerun()

    st.markdown(f"### {T['history']}")
    for conversation in st.session_state.conversations:
        title = conversation["title"] or "New chat"
        is_active = conversation["id"] == st.session_state.active_conversation_id
        label = ("● " if is_active else "") + title[:34]
        if st.button(label, key=f"conversation_{conversation['id']}", use_container_width=True):
            st.session_state.active_conversation_id = conversation["id"]
            st.session_state.section = "Home"
            st.rerun()

# Refresh language dictionary after any language selection rerun.
T = LANGUAGES[st.session_state.language]
active_conversation = get_active_conversation()

# =====================================
# 9. HOME DASHBOARD / SECTION NAVIGATION
# =====================================
if st.session_state.section == "Home":
    st.title("🤖 My Assistant")
    st.markdown(f"### {T['welcome']}")
    st.caption(T["subtitle"])
    st.divider()

    columns = st.columns(4)
    cards = [
        ("Study", "🎓", T["study"], T["study_desc"]),
        ("Canvas", "📚", T["canvas"], T["canvas_desc"]),
        ("Trading", "📈", T["trading"], T["trading_desc"]),
        ("Projects", "📁", T["projects"], T["projects_desc"]),
    ]
    for column, (section_key, icon, label, description) in zip(columns, cards):
        with column:
            st.markdown(
                f"""<div style="background:white;border:1px solid #E2EAF5;
                border-radius:16px;padding:22px 14px;text-align:center;
                min-height:130px;">
                <div style="font-size:34px">{icon}</div>
                <div style="font-size:18px;font-weight:700;color:#263F68">{label}</div>
                <div style="font-size:13px;color:#718096">{description}</div>
                </div>""",
                unsafe_allow_html=True,
            )
            if st.button(label, key=f"open_{section_key}", use_container_width=True):
                st.session_state.section = section_key
                st.rerun()
    st.divider()

else:
    if st.button(T["back"]):
        st.session_state.section = "Home"
        st.rerun()
    section_titles = {
        "Study": T["study"],
        "Canvas": T["canvas"],
        "Trading": T["trading"],
        "Projects": T["projects"],
    }
    st.title(section_titles.get(st.session_state.section, "My Assistant"))

# =====================================
# 10. PROJECTS SECTION
# =====================================
selected_course = None
if st.session_state.section == "Projects":
    st.subheader(T["projects_title"])
    with st.form("add_project_form", clear_on_submit=True):
        project_name = st.text_input(T["project_name"])
        add_project = st.form_submit_button(T["add_project"], use_container_width=True)
    if add_project and project_name.strip():
        st.session_state.projects.append({
            "id": str(uuid.uuid4()),
            "name": project_name.strip(),
        })
        st.rerun()

    if not st.session_state.projects:
        st.info(T["project_empty"])
    else:
        project_columns = st.columns(3)
        for index, project in enumerate(st.session_state.projects):
            with project_columns[index % 3]:
                st.markdown(f"**📁 {project['name']}**")
                if st.button(T["open_project"], key=f"project_{project['id']}"):
                    st.session_state.active_project_id = project["id"]
                    st.session_state.section = "Project Chat"
                    st.rerun()

if st.session_state.section == "Project Chat":
    project = next(
        (p for p in st.session_state.projects if p["id"] == st.session_state.active_project_id),
        None,
    )
    if project:
        st.subheader(f"📁 {project['name']}")
        st.info("This project workspace is ready. Project-specific files and conversations can be added in a later step.")

# =====================================
# 11. CANVAS SECTION: COURSE SELECTION
# =====================================
if st.session_state.section == "Canvas":
    if not CANVAS_URL or not CANVAS_TOKEN:
        st.warning(T["canvas_setup"])
    else:
        course_col, refresh_col = st.columns([5, 1])
        with refresh_col:
            if st.button(T["refresh_courses"], use_container_width=True):
                get_courses.clear()
                st.session_state.courses = get_courses()
        if not st.session_state.courses:
            try:
                st.session_state.courses = get_courses()
            except Exception as error:
                st.error(f"Canvas error: {error}")
        if st.session_state.courses:
            course_map = {
                f"{course.get('name', 'Unnamed')} (ID: {course['id']})": course
                for course in st.session_state.courses
            }
            with course_col:
                selected_name = st.selectbox(T["choose_course"], list(course_map.keys()))
            selected_course = course_map[selected_name]
        else:
            st.info(T["no_courses"])

# =====================================
# 12. CHAT, FILES AND VOICE
# =====================================
show_chat = st.session_state.section in ["Home", "Study", "Canvas", "Trading", "Project Chat"]

if show_chat:
    st.divider()
    st.subheader("💬 " + ("Chat with My Assistant" if st.session_state.language == "English" else "المحادثة مع مساعدك"))

    for message in active_conversation["messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    uploaded_files = st.file_uploader(
        T["upload"],
        type=["pdf", "docx", "xlsx", "pptx", "txt", "csv", "png", "jpg", "jpeg", "webp", "mp3", "wav", "m4a"],
        accept_multiple_files=True,
        key=f"upload_{active_conversation['id']}",
    )
    if uploaded_files:
        for file in uploaded_files:
            st.caption(f"📎 {file.name}")

    input_col, mic_col, send_col = st.columns([7, 1, 1], vertical_alignment="bottom")
    with input_col:
        typed_prompt = st.text_input(
            T["placeholder"],
            key=f"prompt_{active_conversation['id']}",
            label_visibility="collapsed",
        )
    with mic_col:
        audio_input = st.audio_input("🎙️", label_visibility="collapsed")
    with send_col:
        send_clicked = st.button(T["send"], use_container_width=True)

    if send_clicked:
        prompt = typed_prompt.strip()
        if audio_input:
            try:
                spoken_text = transcribe_audio(audio_input)
                if prompt:
                    prompt = f"{prompt}\n\n{spoken_text}"
                else:
                    prompt = spoken_text
            except Exception as error:
                st.error(f"{T['voice_error']}: {error}")
                prompt = ""

        if prompt:
            active_conversation["messages"].append({"role": "user", "content": prompt})
            if active_conversation["title"] == "New chat":
                active_conversation["title"] = prompt[:36] + ("…" if len(prompt) > 36 else "")

            with st.spinner(T["thinking"]):
                try:
                    answer = run_assistant(
                        prompt,
                        selected_course,
                        uploaded_files,
                        active_conversation["messages"][:-1],
                    )
                except Exception as error:
                    answer = f"Assistant error: {error}"

            active_conversation["messages"].append({"role": "assistant", "content": answer})
            st.rerun()

    with st.expander(T["voice_settings"]):
        st.session_state.voice_enabled = st.toggle(
            T["spoken_replies"],
            value=st.session_state.voice_enabled,
        )
        if active_conversation["messages"] and st.session_state.voice_enabled:
            last_answer = next(
                (m["content"] for m in reversed(active_conversation["messages"]) if m["role"] == "assistant"),
                None,
            )
            if last_answer and st.button("🔊 Play latest reply", key=f"play_{active_conversation['id']}"):
                try:
                    st.audio(generate_speech(last_answer), format="audio/mp3")
                except Exception as error:
                    st.warning(f"Voice response unavailable: {error}")

