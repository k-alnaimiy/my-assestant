
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

def get_setting(name: str, default: str = "") -> str:
    """Read credentials locally from .env or from Streamlit Cloud secrets."""
    try:
        value = st.secrets.get(name, default)
        if value not in (None, ""):
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
    layout="wide"
)

if not OPENAI_API_KEY:
    st.error("OpenAI API key is missing. Add OPENAI_API_KEY in Streamlit Secrets or local .env.")
    st.stop()

# Canvas is optional: general chat, study, trading and projects can work
# without a Canvas connection. Canvas features become available when both
# Canvas settings are configured in Streamlit Secrets or the local .env.
CANVAS_CONNECTED = bool(CANVAS_URL and CANVAS_TOKEN)

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
# 3. LANGUAGE
# =====================================

LANGUAGES = {
    "English": {
        "welcome": "Welcome to My Assistant",
        "subtitle": "Your Personal AI Workspace",
        "chat": "Chat with My Assistant",
        "study": "Study",
        "canvas": "Canvas",
        "trading": "Trading",
        "projects": "Projects",
        "course": "Select a Canvas course",
        "placeholder": "Ask me anything...",
        "upload": "Upload Files & Images",
        "voice": "Voice Message",
        "connections": "Connections",
        "thinking": "Thinking...",
        "clear": "Clear Conversation"
    },
    "العربية": {
        "welcome": "مرحباً بك في مساعدك الشخصي",
        "subtitle": "مساحة العمل الذكية الخاصة بك",
        "chat": "المحادثة",
        "study": "الدراسة",
        "canvas": "كانفس",
        "trading": "التداول",
        "projects": "المشاريع",
        "course": "اختر المقرر",
        "placeholder": "اكتب سؤالك هنا...",
        "upload": "رفع الملفات والصور",
        "voice": "رسالة صوتية",
        "connections": "الاتصالات",
        "thinking": "جاري التفكير...",
        "clear": "مسح المحادثة"
    }
}

T = LANGUAGES[st.session_state.language]

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
    if not CANVAS_CONNECTED:
        return []
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
# 5. CANVAS TOOLS
# =====================================

TOOLS = [
    {
        "type": "function",
        "name": "get_course_modules",
        "description": "Get modules from the selected Canvas course.",
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
        "description": "Get pages from the selected Canvas course.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False
        },
        "strict": True
    }
]

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
# 10. AI ENGINE
# =====================================

def run_assistant(prompt, course, files):

    course_id = course["id"] if course else None
    course_name = course.get("name", "Selected course") if course else "No Canvas course selected"
    available_tools = TOOLS if course else []

    instructions = f"""
You are My Assistant, a professional personal AI assistant.

You are bilingual in Arabic and English.
Respond in the language used by the user.

Your responsibilities include:

- Academic studies and PhD research.
- Digital Transformation.
- Canvas course assistance.
- Trading education and market analysis.
- Project management.
- Document and image analysis.
- Writing and translation.

Selected Canvas course:
{course_name}

Course ID:
{course_id if course_id is not None else "Not selected"}

When a Canvas course is selected, you can retrieve its modules and pages.
When no course is selected, answer general questions normally and do not claim to access Canvas.

Never claim an action succeeded unless it did.
Never edit, delete, or publish Canvas content
without explicit user approval.
"""

    document_context = ""
    images = []

    for file in files or []:

        if file.type.startswith("image/"):
            images.extend(prepare_images([file]))

        elif file.type.startswith("audio/"):
            continue

        else:
            content = read_document(file)

            document_context += (
                f"\n\nFILE: {file.name}\n"
                f"{content}\n"
            )

    user_content = [{
        "type": "input_text",
        "text": (
            f"{prompt}\n\n"
            f"Attached document contents:\n"
            f"{document_context}"
        )
    }]

    user_content.extend(images)

    history = [
        {
            "role": message["role"],
            "content": message["content"]
        }
        for message in st.session_state.messages
    ]

    history.append({
        "role": "user",
        "content": user_content
    })

    response = client.responses.create(
        model="gpt-5.5",
        instructions=instructions,
        input=history,
        tools=available_tools
    )

    for _ in range(5):

        calls = [
            item for item in response.output
            if item.type == "function_call"
        ]

        if not calls:
            break

        outputs = []

        for call in calls:

            try:

                if call.name == "get_course_modules":

                    result = get_modules(course_id) if course_id is not None else []

                    output = [
                        {
                            "id": item.get("id"),
                            "name": item.get("name")
                        }
                        for item in result
                    ]

                elif call.name == "get_course_pages":

                    result = get_pages(course_id) if course_id is not None else []

                    output = [
                        {
                            "title": item.get("title"),
                            "url": item.get("url")
                        }
                        for item in result
                    ]

                else:
                    output = {"error": "Unknown tool"}

            except Exception as error:
                output = {"error": str(error)}

            outputs.append({
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": json.dumps(
                    output,
                    ensure_ascii=False
                )
            })

        response = client.responses.create(
            model="gpt-5.5",
            instructions=instructions,
            input=(
                history
                + list(response.output)
                + outputs
            ),
            tools=available_tools
        )

    return response.output_text or "No response generated."

# =====================================
# =====================================
# 11. MY ASSISTANT — REDESIGNED INTERFACE
# =====================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Cairo:wght@400;600;700;800&display=swap');
.stApp{background:#f5f7ff;color:#17264b;font-family:Inter,'Cairo',sans-serif}
[data-testid="stHeader"]{background:transparent}
.block-container{max-width:1500px;padding:1.1rem 2.2rem 6rem}
section[data-testid="stSidebar"]{background:linear-gradient(180deg,#10172f,#17254b);border:0}
section[data-testid="stSidebar"] *{color:#eef2ff}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p{color:#b9c5e7}
section[data-testid="stSidebar"] [data-testid="stSelectbox"]>div>div{background:#202e55;border:1px solid #34436b;border-radius:12px}
section[data-testid="stSidebar"] .stButton>button{background:#27365f;color:white;border:1px solid #3b4c78;border-radius:12px}
.brand{display:flex;align-items:center;gap:12px;padding:8px 0 20px}
.brand-mark{width:43px;height:43px;border-radius:15px;display:grid;place-items:center;background:linear-gradient(135deg,#7167ff,#20d5ca);color:white;font-size:20px;font-weight:800;box-shadow:0 8px 25px #5148d966}
.brand-name{font-size:19px;font-weight:800;color:white}.brand-sub{font-size:10px;color:#9cadd8;margin-top:3px}
.side-label,.section-eyebrow{font-size:10px;letter-spacing:1.5px;text-transform:uppercase;font-weight:800;margin:22px 0 10px;color:#8493b4}
section[data-testid="stSidebar"] .side-label{color:#8498c9}
.hero{position:relative;overflow:hidden;border-radius:26px;padding:34px 38px;min-height:235px;background:radial-gradient(circle at 84% 20%,#697df5,transparent 25%),radial-gradient(circle at 72% 100%,#3a5ab2,transparent 36%),linear-gradient(115deg,#111c40,#253d83 58%,#607bd8);color:white;box-shadow:0 18px 45px #263b7624;margin:5px 0 24px}
.hero:before{content:"";position:absolute;width:260px;height:260px;border:1px solid #ffffff25;border-radius:50%;right:9%;top:-110px;box-shadow:0 0 0 24px #ffffff0b,0 0 0 50px #ffffff08}
.hero h1{color:white!important;font-size:clamp(27px,3vw,40px)!important;margin:8px 0 10px;font-weight:800!important}
.hero p{color:#dbe5ff;font-size:14px;max-width:560px;margin:0}
.hero-kicker{font-size:11px;letter-spacing:2px;color:#a8f5ed;font-weight:700}
.hero-orb{position:absolute;right:13%;top:45px;width:112px;height:112px;border-radius:50%;border:2px solid #9af6ef88;background:radial-gradient(circle at 35% 30%,#c7ffff,#5c89ed 30%,#1a2a62 70%);box-shadow:0 0 0 12px #b4d7ff12,0 0 45px #6ce8f1aa;display:grid;place-items:center;font-size:45px;color:white}
div[data-testid="stHorizontalBlock"]{gap:14px}
div[data-testid="stHorizontalBlock"]>div [data-testid="stVerticalBlockBorderWrapper"]{border:1px solid #e4e9f7;border-radius:19px;background:white;box-shadow:0 8px 24px #273b7010}
.module-icon{width:43px;height:43px;border-radius:14px;display:grid;place-items:center;font-size:22px;margin-bottom:11px}
.module-title{font-size:15px;font-weight:800;color:#1b2b53;margin-bottom:4px}
.module-desc{font-size:11px;color:#7d89a5;line-height:1.5}
.stButton>button{border-radius:13px;border:1px solid #dfe6f6;background:#f2f5ff;color:#314b85;font-weight:700;min-height:42px}
.stButton>button:hover{border-color:#8d9cff;background:#e9edff}
[data-testid="stChatMessage"]{background:white;border:1px solid #e8edf7;border-radius:18px;padding:15px 18px;margin:10px 0}
[data-testid="stChatInput"]{background:white;border:1px solid #dfe6f4;border-radius:18px;box-shadow:0 8px 24px #20345d16;padding:5px}
[data-testid="stFileUploader"]{background:#f8faff;border:1px dashed #bdc9e6;border-radius:15px;padding:10px}
[data-testid="stAudioInput"]{background:#f8faff;border-radius:14px;padding:8px}
hr{border-color:#e5eaf5!important}
@media(max-width:800px){.block-container{padding:1rem .8rem 5rem}.hero{padding:25px 22px;min-height:210px}.hero-orb{right:6%;top:25px;width:75px;height:75px;font-size:30px}.hero p{max-width:75%}}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("""
    <div class="brand"><div class="brand-mark">AI</div><div>
    <div class="brand-name">My Assistant</div>
    <div class="brand-sub">YOUR PERSONAL AI WORKSPACE</div></div></div>
    """, unsafe_allow_html=True)
    language = st.selectbox("🌐 Language", ["English", "العربية"],
        index=0 if st.session_state.language == "English" else 1)
    if language != st.session_state.language:
        st.session_state.language = language
        st.rerun()
    st.markdown('<div class="side-label">Workspace</div>', unsafe_allow_html=True)
    section = st.radio("Navigation", ["Chat","Study","Canvas","Trading","Projects"], label_visibility="collapsed")
    st.session_state.section = section
    st.markdown('<div class="side-label">Canvas courses</div>', unsafe_allow_html=True)
    if st.button("↻  Refresh courses", use_container_width=True):
        try:
            st.cache_data.clear()
            st.session_state.courses = get_courses()
            st.success("Courses refreshed")
        except Exception as error:
            st.error(str(error))
    if not CANVAS_CONNECTED:
        st.caption("Canvas is not connected yet. Add Canvas settings in Streamlit Secrets to enable it.")
    elif not st.session_state.courses:
        try:
            st.session_state.courses = get_courses()
        except Exception as error:
            st.warning(f"Canvas connection: {error}")
    courses = st.session_state.courses
    selected_course = None
    if courses:
        course_map = {f"{c.get('name','Unnamed')} (ID: {c['id']})":c for c in courses}
        selected_name = st.selectbox(T["course"], list(course_map.keys()))
        selected_course = course_map[selected_name]
    else:
        st.caption("No active courses found.")
    st.markdown('<div class="side-label">Connections</div>', unsafe_allow_html=True)
    canvas_status = "🟢 Canvas API" if CANVAS_CONNECTED else "⚪ Canvas not configured"
    st.markdown(f"🟢 OpenAI API<br>{canvas_status}", unsafe_allow_html=True)
    if st.button(T["clear"], use_container_width=True):
        st.session_state.messages = []
        st.rerun()

welcome_line = "مرحباً بك في مساعدك الذكي" if st.session_state.language == "العربية" else "Your ideas. One intelligent workspace."
subtitle_line = "مساعدك في الدراسة وCanvas والتداول والمشاريع" if st.session_state.language == "العربية" else "Your companion for study, Canvas, trading and projects."
st.markdown(f"""<div class="hero"><div class="hero-kicker">MY ASSISTANT · AI WORKSPACE</div>
<h1>{welcome_line}</h1><p>{subtitle_line}</p><div class="hero-orb">✧</div></div>""", unsafe_allow_html=True)

st.markdown('<div class="section-eyebrow">Explore your workspace</div>', unsafe_allow_html=True)
cards = [
 ("🎓",T["study"],"Courses, research and learning","#e9e7ff","Study"),
 ("📚",T["canvas"],"Courses, assignments and grades","#e3f8f4","Canvas"),
 ("📈",T["trading"],"Markets, insights and strategy","#fff0e6","Trading"),
 ("📁",T["projects"],"Files, ideas and active projects","#e8efff","Projects")
]
cols=st.columns(4)
for col,(emoji,title,desc,tint,key) in zip(cols,cards):
    with col:
        with st.container(border=True):
            st.markdown(f'<div class="module-icon" style="background:{tint}">{emoji}</div><div class="module-title">{title}</div><div class="module-desc">{desc}</div>',unsafe_allow_html=True)
            if st.button("Open workspace →",key=f"open_{key}",use_container_width=True):
                st.session_state.section=key
                st.rerun()

st.markdown('<div class="section-eyebrow">Your assistant</div>',unsafe_allow_html=True)
st.markdown(f"## 💬 {T['chat']}")
uploaded_files=[]
audio_input=None
with st.expander("＋  Add files or a voice message"):
    uploaded_files=st.file_uploader("Attach documents, images or audio",
        type=["pdf","docx","xlsx","pptx","txt","csv","png","jpg","jpeg","webp","mp3","wav","m4a"],
        accept_multiple_files=True)
    if uploaded_files: st.caption(" · ".join(file.name for file in uploaded_files))
    audio_input=st.audio_input("Record a voice message")

voice_prompt=None
if audio_input:
    try:
        voice_prompt=transcribe_audio(audio_input)
        st.info(f"Recognized: {voice_prompt}")
    except Exception as error: st.error(f"Voice error: {error}")

for message in st.session_state.messages:
    with st.chat_message(message["role"]): st.markdown(message["content"])

prompt=st.chat_input(T["placeholder"])
if not prompt and voice_prompt: prompt=voice_prompt
if prompt:
    st.session_state.messages.append({"role":"user","content":prompt})
    with st.chat_message("user"): st.markdown(prompt)
    with st.chat_message("assistant"):
        try:
            with st.spinner(T["thinking"]):
                answer=run_assistant(prompt,selected_course,uploaded_files)
            st.markdown(answer)
            if st.session_state.voice_enabled:
                try:
                    speech=generate_speech(answer)
                    st.audio(speech,format="audio/mp3")
                except Exception as audio_error: st.warning(f"Voice response unavailable: {audio_error}")
        except Exception as error:
            answer=f"Assistant error: {error}"
            st.error(answer)
    st.session_state.messages.append({"role":"assistant","content":answer})

with st.expander("Voice settings"):
    st.session_state.voice_enabled=st.toggle("Enable spoken responses",value=st.session_state.voice_enabled)
    st.caption("Recorded voice input and spoken replies are supported. Real-time continuous voice is a separate development stage.")
