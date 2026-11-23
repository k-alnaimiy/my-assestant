
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
# 3. LANGUAGE
# =====================================

LANGUAGES = {
    "English": {
        "welcome": "Welcome to Canvas Assistant",
        "subtitle": "Your Personal AI Workspace",
        "chat": "Chat with Canvas Assistant",
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
        "clear": "Clear Conversation",
        "no_course": "Please select an active Canvas course first."
    },
    "العربية": {
        "welcome": "مرحباً بك في مساعد كانفس",
        "subtitle": "مساحة العمل الذكية الخاصة بك",
        "chat": "المحادثة مع مساعد كانفس",
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
        "clear": "مسح المحادثة",
        "no_course": "يرجى اختيار مقرر نشط من Canvas أولاً."
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

def run_assistant(prompt, course=None, files=None):

    course_id = course.get("id") if course else None
    course_name = course.get("name", "No course selected") if course else "No course selected"

    instructions = f"""
You are Canvas Assistant, a professional Canvas support assistant for an authorized university staff member.

You are bilingual in Arabic and English.
Respond in the language used by the user.

Your responsibilities are limited to Canvas support, administration guidance, course information, modules, pages, assignments, quizzes, grades, students, instructors, and Canvas-related documents. Do not claim access to data or actions unless an available Canvas API tool actually provides it.

Selected Canvas course:
{course_name}

Course ID:
{course_id}

You can retrieve Canvas modules and pages
using the available tools.

Never claim an action succeeded unless it did.
Never edit, delete, grade, or publish Canvas content without explicit user approval. Never claim that the user is a student or administrator based only on a course list.
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

    # Replace the current plain-text prompt with its enriched version.
    if history and history[-1]["role"] == "user" and history[-1]["content"] == prompt:
        history.pop()

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

                    if not course_id:
                        output = {"error": "Select a Canvas course to retrieve its modules."}
                    else:
                        result = get_modules(course_id)

                        output = [
                            {
                                "id": item.get("id"),
                                "name": item.get("name")
                            }
                            for item in result
                        ]

                elif call.name == "get_course_pages":

                    if not course_id:
                        output = {"error": "Select a Canvas course to retrieve its pages."}
                    else:
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
# 11. CANVAS ASSISTANT INTERFACE
# =====================================

st.markdown("""
<style>
.stApp {
    background: radial-gradient(circle at 85% 0%, rgba(24,182,164,.10), transparent 28%),
                linear-gradient(135deg, #0B1425 0%, #101D35 55%, #13243D 100%);
    color: #EAF1FA;
}
.block-container { max-width: 1480px; padding-top: 1.8rem; padding-bottom: 3rem; }
section[data-testid="stSidebar"] { background: #0A1527; border-right: 1px solid rgba(159,176,199,.16); }
h1, h2, h3, h4, p, label, .stMarkdown, [data-testid="stCaptionContainer"] { color: #EAF1FA; }
[data-testid="stChatMessage"], [data-testid="stFileUploader"], [data-testid="stExpander"] {
    background: rgba(23,41,68,.88); border: 1px solid rgba(159,176,199,.16); border-radius: 18px;
}
[data-testid="stChatMessage"] { padding: 1rem 1.15rem; margin-bottom: .8rem; }
.stButton > button, .stDownloadButton > button {
    background: linear-gradient(135deg, #18B6A4, #138D91); color: #061B2A;
    border: 0; border-radius: 12px; min-height: 2.65rem; font-weight: 750;
}
.stChatInput textarea, .stTextInput input, .stSelectbox div[data-baseweb="select"] {
    background: #172944 !important; color: #F3F7FC !important;
    border-color: rgba(159,176,199,.24) !important; border-radius: 12px !important;
}
hr { border-color: rgba(159,176,199,.18); }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("# 🎓 Canvas Assistant")
    st.caption("Canvas support for authorized university staff")
    st.divider()

    language = st.selectbox(
        "Language",
        ["English", "العربية"],
        index=0 if st.session_state.language == "English" else 1
    )
    if language != st.session_state.language:
        st.session_state.language = language
        st.rerun()

    st.divider()
    st.markdown("### Canvas Courses")

    if st.button("↻ Refresh courses", use_container_width=True):
        try:
            st.cache_data.clear()
            st.session_state.courses = get_courses()
            st.success("Courses refreshed")
        except Exception as error:
            st.error(f"Canvas error: {error}")

    if not st.session_state.courses:
        try:
            st.session_state.courses = get_courses()
        except Exception as error:
            st.error(f"Canvas connection: {error}")

    courses = st.session_state.courses
    selected_course = None
    course_options = ["General Canvas support — no course selected"]
    course_map = {}
    for c in courses:
        if c.get("id") is not None:
            label = f"{c.get('name', 'Unnamed')} (ID: {c['id']})"
            course_options.append(label)
            course_map[label] = c

    selected_name = st.selectbox(
        "Optional course context",
        course_options,
        help="A course is only needed for course-specific information. You can chat without selecting one."
    )
    selected_course = course_map.get(selected_name)

    st.divider()
    st.markdown("### Connections")
    st.success("OpenAI API configured")
    st.success("Canvas API configured")
    st.caption("The current Canvas API connection uses the token configured in the deployment secrets.")

    if st.button(T["clear"], use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# Main Canvas-focused workspace
page_title = "مساعد كانفس" if st.session_state.language == "العربية" else "Canvas Assistant"
page_subtitle = (
    "مساعدك الذكي لدعم وإدارة Canvas"
    if st.session_state.language == "العربية"
    else "Your AI workspace for Canvas support and administration"
)
st.title(f"🎓 {page_title}")
st.caption(page_subtitle)
st.divider()

if selected_course:
    st.info(
        f"Selected course: {selected_course.get('name', 'Unnamed course')} "
        f"(ID: {selected_course.get('id')})"
    )
else:
    st.caption("General Canvas support mode — no course selected.")

uploaded_files = st.file_uploader(
    T["upload"],
    type=["pdf", "docx", "xlsx", "pptx", "txt", "csv",
          "png", "jpg", "jpeg", "webp", "mp3", "wav", "m4a"],
    accept_multiple_files=True
)
if uploaded_files:
    st.caption(" · ".join(file.name for file in uploaded_files))

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

with st.expander("Voice settings"):
    st.session_state.voice_enabled = st.toggle(
        "Enable spoken responses",
        value=st.session_state.voice_enabled
    )
    st.caption("Recorded voice input and spoken replies are supported.")

