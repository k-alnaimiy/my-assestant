
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
    page_title="My Assistant",
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

    course_id = course["id"]
    course_name = course.get("name", "Selected course")

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
{course_id}

You can retrieve Canvas modules and pages
using the available tools.

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
        tools=TOOLS
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

                    result = get_modules(course_id)

                    output = [
                        {
                            "id": item.get("id"),
                            "name": item.get("name")
                        }
                        for item in result
                    ]

                elif call.name == "get_course_pages":

                    result = get_pages(course_id)

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
            tools=TOOLS
        )

    return response.output_text or "No response generated."

# =====================================
# 11. NEW INTERFACE
# =====================================

st.markdown("""
<style>

.stApp {
    background: #F7F9FD;
    color: #26344D;
}

.block-container {
    max-width: 1450px;
    padding-top: 2rem;
}

section[data-testid="stSidebar"] {
    background: #FFFFFF;
    border-right: 1px solid #E7ECF5;
}

h1, h2, h3 {
    color: #263F68 !important;
    font-weight: 700 !important;
}

.stButton > button {
    background: #EEF4FF;
    color: #315A9D;
    border: 1px solid #DCE6F7;
    border-radius: 12px;
    min-height: 42px;
    font-weight: 600;
}

.stButton > button:hover {
    background: #DDEAFF;
}

.stChatInput textarea {
    background: white;
    border-radius: 14px;
}

[data-testid="stChatMessage"] {
    background: white;
    border: 1px solid #E7ECF5;
    border-radius: 16px;
    padding: 16px;
    margin-bottom: 12px;
}

[data-testid="stFileUploader"] {
    background: white;
    border: 1px dashed #B9CBE9;
    border-radius: 14px;
    padding: 12px;
}

</style>
""", unsafe_allow_html=True)

# =====================================
# 12. SIDEBAR
# =====================================

with st.sidebar:

    st.markdown("# 🤖 My Assistant")

    st.caption("Your Personal AI Workspace")

    st.divider()

    language = st.selectbox(
        "Language",
        ["English", "العربية"],
        index=(
            0 if st.session_state.language == "English"
            else 1
        )
    )

    if language != st.session_state.language:
        st.session_state.language = language
        st.rerun()

    st.divider()

    st.markdown("### Workspace")

    section = st.radio(
        "Navigation",
        [
            "Chat",
            "Study",
            "Canvas",
            "Trading",
            "Projects"
        ],
        label_visibility="collapsed"
    )

    st.session_state.section = section

    st.divider()

    st.markdown("### Canvas Courses")

    if st.button(
        "Refresh Courses",
        use_container_width=True
    ):
        try:
            st.cache_data.clear()
            st.session_state.courses = get_courses()
            st.success("Courses refreshed")
        except Exception as error:
            st.error(str(error))

    if not st.session_state.courses:
        try:
            st.session_state.courses = get_courses()
        except Exception as error:
            st.error(f"Canvas error: {error}")

    courses = st.session_state.courses
    selected_course = None

    if courses:

        course_map = {
            f"{c.get('name', 'Unnamed')} (ID: {c['id']})": c
            for c in courses
        }

        selected_name = st.selectbox(
            T["course"],
            list(course_map.keys())
        )

        selected_course = course_map[selected_name]

    st.divider()

    st.markdown("### Connections")

    st.success("OpenAI API")
    st.success("Canvas API")

    st.divider()

    if st.button(
        T["clear"],
        use_container_width=True
    ):
        st.session_state.messages = []
        st.rerun()

# =====================================
# 13. MAIN DASHBOARD
# =====================================

st.title("🤖 My Assistant")

st.markdown(f"### {T['welcome']}")

st.caption(T["subtitle"])

st.divider()

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.markdown("### 🎓")
    st.markdown(f"**{T['study']}**")
    st.caption("Courses and Research")

with c2:
    st.markdown("### 📚")
    st.markdown(f"**{T['canvas']}**")
    st.caption("Assignments and Courses")

with c3:
    st.markdown("### 📈")
    st.markdown(f"**{T['trading']}**")
    st.caption("Market Analysis")

with c4:
    st.markdown("### 📁")
    st.markdown(f"**{T['projects']}**")
    st.caption("Files and Projects")

st.divider()

# =====================================
# 14. FILE UPLOAD
# =====================================

st.markdown(f"### 📎 {T['upload']}")

uploaded_files = st.file_uploader(
    "Upload your files and images",
    type=[
        "pdf", "docx",
        "xlsx", "pptx",
        "txt", "csv",
        "png", "jpg", "jpeg", "webp",
        "mp3", "wav", "m4a"
    ],
    accept_multiple_files=True
)

if uploaded_files:
    for file in uploaded_files:
        st.caption(f"Attached: {file.name}")

# =====================================
# 15. VOICE INPUT
# =====================================

st.markdown(f"### 🎙️ {T['voice']}")

audio_input = st.audio_input(
    "Record your voice message"
)

voice_prompt = None

if audio_input:
    try:
        voice_prompt = transcribe_audio(audio_input)
        st.info(f"Recognized: {voice_prompt}")
    except Exception as error:
        st.error(f"Voice error: {error}")

# =====================================
# 16. CHAT
# =====================================

st.divider()

st.markdown(f"## 💬 {T['chat']}")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.chat_input(T["placeholder"])

if not prompt and voice_prompt:
    prompt = voice_prompt

if prompt:

    if not selected_course:
        st.error(T["no_course"])
        st.stop()

    st.session_state.messages.append({
        "role": "user",
        "content": prompt
    })

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):

        try:

            with st.spinner(T["thinking"]):

                answer = run_assistant(
                    prompt,
                    selected_course,
                    uploaded_files
                )

            st.markdown(answer)

            if st.session_state.voice_enabled:
                try:
                    speech = generate_speech(answer)
                    st.audio(speech, format="audio/mp3")
                except Exception as audio_error:
                    st.warning(
                        f"Voice response unavailable: {audio_error}"
                    )

        except Exception as error:

            answer = f"Assistant error: {error}"
            st.error(answer)

    st.session_state.messages.append({
        "role": "assistant",
        "content": answer
    })

# =====================================
# 17. VOICE SETTINGS
# =====================================

with st.expander("Voice Settings"):

    st.session_state.voice_enabled = st.toggle(
        "Enable spoken responses",
        value=st.session_state.voice_enabled
    )

    st.caption(
        "This version supports recorded voice input "
        "and generated spoken replies. Continuous "
        "real-time voice conversation is a separate "
        "development stage."
    )

# =====================================
# END
# =====================================
