
import os
import json
import base64
import io
import requests
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

# =====================================
# 1. CONFIGURATION
# =====================================

load_dotenv()

CANVAS_URL = os.getenv("CANVAS_API_URL", "").rstrip("/")
CANVAS_TOKEN = os.getenv("CANVAS_API_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

st.set_page_config(
    page_title="Canvas Assistant",
    page_icon="🤖",
    layout="wide"
)

if not OPENAI_API_KEY:
    st.error("OpenAI API key is missing from .env")
    st.stop()

if not CANVAS_URL or not CANVAS_TOKEN:
    st.error("Canvas settings are missing from .env")
    st.stop()

client = OpenAI(api_key=OPENAI_API_KEY)

# =====================================
# 2. SESSION STATE
# =====================================

defaults = {
    "messages": [],
    "courses": [],
    "language": "English",
    "section": "Chat",
    "voice_enabled": True
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# =====================================
# 4. CANVAS CONNECTION
# =====================================

CANVAS_HEADERS = {
    "Authorization": f"Bearer {CANVAS_TOKEN}"
}

def canvas_get(endpoint, params=None):
    response = requests.get(
        f"{CANVAS_URL}/api/v1/{endpoint}",
        headers=CANVAS_HEADERS,
        params=params,
        timeout=30
    )
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=60)
def get_courses():
    return canvas_get(
        "courses",
        {
            "enrollment_state": "active",
            "per_page": 100
        }
    )


def get_modules(course_id):
    return canvas_get(
        f"courses/{course_id}/modules",
        {"per_page": 100}
    )


def get_pages(course_id):
    return canvas_get(
        f"courses/{course_id}/pages",
        {"per_page": 100}
    )

# =====================================
# 6. DOCUMENT READER
# =====================================

def read_document(file):

    name = file.name.lower()
    data = file.getvalue()

    try:

        if name.endswith((".txt", ".csv")):
            return data.decode(
                "utf-8",
                errors="replace"
            )

        if name.endswith(".pdf"):
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))

            return "\n".join(
                page.extract_text() or ""
                for page in reader.pages
            )

        if name.endswith(".docx"):
            from docx import Document

            doc = Document(io.BytesIO(data))

            return "\n".join(
                p.text for p in doc.paragraphs
            )

        if name.endswith(".xlsx"):
            from openpyxl import load_workbook

            workbook = load_workbook(
                io.BytesIO(data),
                read_only=True,
                data_only=True
            )

            output = []

            for sheet in workbook.worksheets:
                output.append(f"Sheet: {sheet.title}")

                for row in sheet.iter_rows(values_only=True):
                    output.append(
                        " | ".join(
                            str(v) if v is not None else ""
                            for v in row
                        )
                    )

            return "\n".join(output)

        if name.endswith(".pptx"):
            from pptx import Presentation

            presentation = Presentation(io.BytesIO(data))

            output = []

            for number, slide in enumerate(
                presentation.slides, 1
            ):
                output.append(f"Slide {number}")

                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        output.append(shape.text)

            return "\n".join(output)

        return (
            "This file format needs conversion "
            "or a dedicated reader."
        )

    except Exception as error:
        return f"File reading error: {error}"

# =====================================
# 7. IMAGE SUPPORT
# =====================================

def prepare_images(files):

    images = []

    for file in files or []:

        if file.type not in [
            "image/png",
            "image/jpeg",
            "image/webp"
        ]:
            continue

        encoded = base64.b64encode(
            file.getvalue()
        ).decode("utf-8")

        images.append({
            "type": "input_image",
            "image_url": (
                f"data:{file.type};base64,{encoded}"
            ),
            "detail": "auto"
        })

    return images

# =====================================
# 8. VOICE TRANSCRIPTION
# =====================================

def transcribe_audio(audio):

    audio.seek(0)

    result = client.audio.transcriptions.create(
        model="gpt-4o-mini-transcribe",
        file=audio
    )

    return result.text

# =====================================
# 9. VOICE RESPONSE
# =====================================

def generate_speech(text):

    result = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice="marin",
        input=text
    )

    return result.content

# =====================================
# 10. CANVAS ASSISTANT ENGINE
# =====================================

CANVAS_TOOLS = [
    {
        "type": "function",
        "name": "get_course_modules",
        "description": "Get modules from the Canvas course currently selected by the user.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False
        },
        "strict": True
    },
    {
        "type": "function",
        "name": "get_course_pages",
        "description": "Get pages from the Canvas course currently selected by the user.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False
        },
        "strict": True
    }
]


def run_assistant(prompt, course=None, files=None):
    course_id = course.get("id") if course else None
    course_name = course.get("name", "Selected course") if course else None

    instructions = """
You are Canvas Assistant, a professional bilingual assistant for Canvas LMS support.
Respond in the same language used by the user (Arabic or English).
Your scope is Canvas LMS, course administration guidance, learning management workflows,
Canvas troubleshooting, and analysis of documents, images, and files supplied by the user.
Do not offer trading or unrelated personal-workspace features.

If a Canvas course is selected, you may use the available tools to read that course's
modules and pages. If no course is selected, answer general questions normally and do not
attempt course-specific tool calls. Explain when a request needs a course selection.

Important safety rules:
- Never claim that a Canvas action succeeded unless the API actually confirmed it.
- The current app has read-only tools for course modules and pages only.
- Do not claim to change grades, edit, delete, publish, message users, or modify Canvas data.
- Never request or reveal API tokens, passwords, or secrets.
- Ask for explicit confirmation before any future action that changes Canvas data.
- Be transparent about missing permissions or unavailable data.
"""

    if course:
        instructions += f"\nCurrently selected Canvas course: {course_name} (ID: {course_id})."
        tools = CANVAS_TOOLS
    else:
        instructions += "\nNo Canvas course is currently selected."
        tools = []

    document_context = ""
    images = []
    for file in files or []:
        if file.type.startswith("image/"):
            images.extend(prepare_images([file]))
        elif file.type.startswith("audio/"):
            continue
        else:
            content = read_document(file)
            document_context += f"\n\nFILE: {file.name}\n{content}\n"

    user_content = [{
        "type": "input_text",
        "text": f"{prompt}\n\nAttached document contents:\n{document_context}"
    }]
    user_content.extend(images)

    history = [
        {"role": message["role"], "content": message["content"]}
        for message in st.session_state.messages
    ]
    # The current prompt is already in session history as plain text.
    # Replace it with the enriched content containing uploaded files/images.
    if history and history[-1]["role"] == "user" and history[-1]["content"] == prompt:
        history.pop()
    history.append({"role": "user", "content": user_content})

    response = client.responses.create(
        model="gpt-5.5",
        instructions=instructions,
        input=history,
        tools=tools
    )

    for _ in range(5):
        calls = [item for item in response.output if item.type == "function_call"]
        if not calls:
            break

        outputs = []
        for call in calls:
            try:
                if not course_id:
                    output = {"error": "Select a Canvas course first."}
                elif call.name == "get_course_modules":
                    result = get_modules(course_id)
                    output = [
                        {"id": item.get("id"), "name": item.get("name")}
                        for item in result
                    ]
                elif call.name == "get_course_pages":
                    result = get_pages(course_id)
                    output = [
                        {"title": item.get("title"), "url": item.get("url")}
                        for item in result
                    ]
                else:
                    output = {"error": "Unknown tool"}
            except Exception as error:
                output = {"error": str(error)}

            outputs.append({
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": json.dumps(output, ensure_ascii=False)
            })

        response = client.responses.create(
            model="gpt-5.5",
            instructions=instructions,
            input=history + list(response.output) + outputs,
            tools=tools
        )

    return response.output_text or "No response generated."


# =====================================
# 11. CANVAS ASSISTANT INTERFACE
# =====================================

LANGUAGES = {
    "English": {
        "title": "Canvas Assistant",
        "welcome": "Your intelligent assistant for Canvas LMS",
        "subtitle": "Courses, modules, pages, learning workflows and Canvas support.",
        "course": "Optional: select a Canvas course",
        "no_course": "No course selected — general Canvas help is available.",
        "placeholder": "Ask about Canvas...",
        "upload": "Upload files and images",
        "voice": "Record a voice message",
        "thinking": "Thinking...",
        "clear": "Clear conversation",
        "refresh": "Refresh courses",
        "connections": "Connections",
        "voice_settings": "Voice settings",
        "voice_toggle": "Enable spoken responses",
        "attached": "Attached",
        "course_hint": "Course selection is optional. Select one only for course-specific questions."
    },
    "العربية": {
        "title": "مساعد كانفس",
        "welcome": "مساعدك الذكي لنظام Canvas",
        "subtitle": "المقررات والوحدات والصفحات وسير العمل والدعم الفني لكانفس.",
        "course": "اختياري: اختر مقرراً من Canvas",
        "no_course": "لم يتم اختيار مقرر — يمكنك طرح أسئلة عامة عن Canvas.",
        "placeholder": "اسأل عن Canvas...",
        "upload": "رفع الملفات والصور",
        "voice": "سجّل رسالة صوتية",
        "thinking": "جاري التفكير...",
        "clear": "مسح المحادثة",
        "refresh": "تحديث المقررات",
        "connections": "الاتصالات",
        "voice_settings": "إعدادات الصوت",
        "voice_toggle": "تفعيل الردود الصوتية",
        "attached": "مرفق",
        "course_hint": "اختيار المقرر اختياري. اختر مقرراً فقط عندما يكون سؤالك متعلقاً بمقرر محدد."
    }
}

if "language" not in st.session_state:
    st.session_state.language = "English"
if "messages" not in st.session_state:
    st.session_state.messages = []
if "courses" not in st.session_state:
    st.session_state.courses = []
if "voice_enabled" not in st.session_state:
    st.session_state.voice_enabled = True

T = LANGUAGES[st.session_state.language]

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Cairo:wght@400;600;700;800&display=swap');
.stApp { background: radial-gradient(circle at 85% 0%, rgba(24,182,164,.10), transparent 28%), linear-gradient(135deg,#0B1425 0%,#101D35 55%,#13243D 100%); color:#EAF1FA; font-family:Inter,'Cairo',sans-serif; }
.block-container { max-width:1480px; padding-top:1.8rem; padding-bottom:3rem; }
section[data-testid="stSidebar"] { background:#0A1527; border-right:1px solid rgba(159,176,199,.16); }
h1,h2,h3,h4,p,label,.stMarkdown,[data-testid="stCaptionContainer"] { color:#EAF1FA; }
h1 { letter-spacing:-.035em; font-weight:800 !important; }
[data-testid="stChatMessage"],[data-testid="stFileUploader"],[data-testid="stExpander"] { background:rgba(23,41,68,.88); border:1px solid rgba(159,176,199,.16); border-radius:18px; }
[data-testid="stChatMessage"] { padding:1rem 1.15rem; margin-bottom:.8rem; }
.stButton>button,.stDownloadButton>button { background:linear-gradient(135deg,#18B6A4,#138D91); color:#061B2A; border:0; border-radius:12px; min-height:2.65rem; font-weight:750; }
.stButton>button:hover,.stDownloadButton>button:hover { background:#39D0BD; color:#061B2A; border:0; }
.stChatInput textarea,.stTextInput input,.stSelectbox div[data-baseweb="select"] { background:#172944 !important; color:#F3F7FC !important; border-color:rgba(159,176,199,.24) !important; border-radius:12px !important; }
.stChatInput textarea::placeholder,.stTextInput input::placeholder { color:#9FB0C7 !important; }
[data-testid="stFileUploader"] section { background:transparent; }
hr { border-color:rgba(159,176,199,.18); }
[data-testid="stAlert"] { border-radius:12px; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("# 🎓 Canvas Assistant")
    st.caption("Canvas LMS support workspace")
    language = st.selectbox(
        "Language / اللغة",
        ["English", "العربية"],
        index=0 if st.session_state.language == "English" else 1
    )
    if language != st.session_state.language:
        st.session_state.language = language
        st.rerun()

    st.divider()
    if st.button(T["refresh"], use_container_width=True):
        try:
            st.cache_data.clear()
            st.session_state.courses = get_courses()
            st.success("Courses refreshed" if language == "English" else "تم تحديث المقررات")
        except Exception as error:
            st.error(f"Canvas API: {error}")

    if not st.session_state.courses:
        try:
            st.session_state.courses = get_courses()
        except Exception as error:
            st.warning(f"Canvas connection: {error}")

    courses = st.session_state.courses
    course_options = {"— No course selected —": None}
    for item in courses:
        if item.get("id") is not None:
            label = f"{item.get('name', 'Unnamed course')} (ID: {item['id']})"
            course_options[label] = item
    selected_label = st.selectbox(T["course"], list(course_options.keys()))
    selected_course = course_options[selected_label]
    st.caption(T["course_hint"])

    st.divider()
    st.markdown(f"### {T['connections']}")
    st.success("OpenAI API")
    st.success("Canvas API")
    if st.button(T["clear"], use_container_width=True):
        st.session_state.messages = []
        st.rerun()

st.title("🎓 Canvas Assistant")
st.markdown(f"### {T['welcome']}")
st.caption(T["subtitle"])
if selected_course:
    st.info(f"Selected course: {selected_course.get('name', 'Unnamed course')} · ID: {selected_course.get('id')}")
else:
    st.caption(T["no_course"])

uploaded_files = st.file_uploader(
    T["upload"],
    type=["pdf","docx","xlsx","pptx","txt","csv","png","jpg","jpeg","webp","mp3","wav","m4a"],
    accept_multiple_files=True
)
if uploaded_files:
    st.caption(" · ".join(f"{T['attached']}: {file.name}" for file in uploaded_files))

audio_input = st.audio_input(T["voice"])
voice_prompt = None
if audio_input:
    try:
        voice_prompt = transcribe_audio(audio_input)
        st.info(f"Recognized: {voice_prompt}")
    except Exception as error:
        st.error(f"Voice error: {error}")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.chat_input(T["placeholder"])
if not prompt and voice_prompt:
    prompt = voice_prompt

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        try:
            with st.spinner(T["thinking"]):
                answer = run_assistant(prompt, selected_course, uploaded_files)
            st.markdown(answer)
            if st.session_state.voice_enabled:
                try:
                    speech = generate_speech(answer)
                    st.audio(speech, format="audio/mp3")
                except Exception as audio_error:
                    st.warning(f"Voice response unavailable: {audio_error}")
        except Exception as error:
            answer = f"Assistant error: {error}"
            st.error(answer)
    st.session_state.messages.append({"role": "assistant", "content": answer})

with st.expander(T["voice_settings"]):
    st.session_state.voice_enabled = st.toggle(
        T["voice_toggle"], value=st.session_state.voice_enabled
    )
    st.caption(
        "Recorded voice input and spoken replies are supported. Continuous real-time voice is a separate development stage."
        if st.session_state.language == "English"
        else "يدعم التطبيق تسجيل الرسائل الصوتية وإنشاء ردود منطوقة. المحادثة الصوتية الفورية المستمرة مرحلة تطوير منفصلة."
    )
