import os
import json
import base64
import requests
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
load_dotenv()
import streamlit as st
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont


# ============================================================
# CONFIG
# ============================================================
st.set_page_config(page_title="Storybook Generator", layout="wide")

OUTPUT_DIR = Path("generated_books")
OUTPUT_DIR.mkdir(exist_ok=True)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "stepfun/step-3.5-flash:free")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GROK_API_KEY = os.getenv("GROK_API_KEY", "")


# ============================================================
# SESSION STATE
# ============================================================
def init_state() -> None:
    defaults = {
        "messages": [
            {
                "role": "assistant",
                "content": (
                    "Hi! Tell me the kind of children's book you want to create. "
                    "For example: 'Write a storybook for my 5-year-old daughter teaching her the importance of brushing her teeth.'"
                ),
            }
        ],
        "story_idea": "",
        "page_count": 10,
        "summary_data": None,
        "pages_data": None,
        "image_prompts_data": None,
        "image_paths": [],
        "selected_page": 1,
        "current_stage": "idea",
        "edit_mode": False,
        "show_page_breakdown": False,
        "show_summary_editor": False,
        "is_generating_book": False,
        "style_preferences": {
            "warm_colors_only": False,
            "cool_colors_only": False,
            "less_distraction": False,
            "colorful": True,
            "gentle_expressions": True,
            "simple_backgrounds": False,
            "high_contrast": False,
            "soft_pastels": False,
        },
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_state()


# ============================================================
# HELPERS
# ============================================================
def extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()

    if text.startswith("```"):
        parts = text.split("```")
        for part in parts:
            candidate = part.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            if candidate.startswith("{") and candidate.endswith("}"):
                return json.loads(candidate)

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start:end + 1])

    raise ValueError("Could not find valid JSON in model response.")


def slugify(text: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in text)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "storybook"


def openrouter_chat(system_prompt: str, user_prompt: str) -> str:
    if not OPENROUTER_API_KEY:
        raise ValueError("Missing OPENROUTER_API_KEY environment variable.")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
    }

    response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def build_visual_preferences_text(preferences: Dict[str, bool]) -> str:
    selected = []

    if preferences.get("warm_colors_only"):
        selected.append("use warm colors only")
    if preferences.get("cool_colors_only"):
        selected.append("use cool colors only")
    if preferences.get("less_distraction"):
        selected.append("keep visuals low-distraction and uncluttered")
    if preferences.get("colorful"):
        selected.append("use colorful illustrations")
    if preferences.get("gentle_expressions"):
        selected.append("use gentle, friendly facial expressions")
    if preferences.get("simple_backgrounds"):
        selected.append("use simple backgrounds")
    if preferences.get("high_contrast"):
        selected.append("use higher-contrast visuals")
    if preferences.get("soft_pastels"):
        selected.append("use soft pastel tones")

    return ", ".join(selected) if selected else "use a balanced children's picture-book style"


def generate_story_summary(story_idea: str, page_count: int, preferences: Dict[str, bool]) -> Dict[str, Any]:
    system_prompt = (
        "You create children's picture book plans for ages 4 to 7. "
        "Always respond with valid JSON only and no extra text."
    )

    user_prompt = f"""
Create a children's story concept from this request:
{story_idea}

Visual and sensory preferences for the book:
{build_visual_preferences_text(preferences)}

Return JSON with exactly these keys:
- title: string
- lesson: string
- target_age: string
- main_character: string
- supporting_characters: array of strings
- setting: string
- art_style: string
- summary: string
- plot_points: array of strings
- character_bible: string
- style_bible: string

Requirements:
- Make it emotionally warm, simple, and very clear.
- The story should be appropriate for a young child.
- The lesson should be concrete and positive.
- The story must be easy to expand into about {page_count} picture-book pages.
- Make the visual style match the preferences.
- character_bible must include stable visual details: age, hairstyle, hair color, skin tone if relevant, signature outfit, recurring accessories, facial expression style.
- style_bible must include stable visual details: medium, palette, line quality, background complexity, lighting, rendering style.
- Output valid JSON only.
"""
    raw = openrouter_chat(system_prompt, user_prompt)
    return extract_json(raw)


def generate_page_texts(summary_data: Dict[str, Any], page_count: int) -> Dict[str, Any]:
    system_prompt = (
        "You turn a children's story summary into page-by-page storybook text. "
        "Always respond with valid JSON only and no extra text."
    )

    user_prompt = f"""
Expand this story plan into exactly {page_count} pages.

Story plan:
{json.dumps(summary_data, indent=2)}

Return JSON with this structure:
{{
  "pages": [
    {{"page_number": 1, "text": "..."}}
  ]
}}

Requirements:
- Create exactly {page_count} pages.
- Each page should have 1 to 3 short sentences.
- Keep the language simple and easy to read aloud to a 5-year-old.
- Include a clear beginning, middle, and end.
- End positively.
- Output valid JSON only.
"""
    raw = openrouter_chat(system_prompt, user_prompt)
    return extract_json(raw)
def create_storybook_pdf() -> bytes:
    summary = st.session_state.summary_data or {}
    pages = st.session_state.pages_data.get("pages", []) if st.session_state.pages_data else []
    image_paths = st.session_state.image_paths if st.session_state.image_paths else []

    if not pages:
        raise ValueError("No story pages available for PDF export.")

    page_width = 1240
    page_height = 1754
    margin = 70
    gap = 40
    image_height = 900

    pdf_images = []

    try:
        body_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 36)
    except:
        body_font = ImageFont.load_default()

    def wrap_text(draw, text, font, max_width):
        words = text.split()
        lines = []
        current = ""

        for word in words:
            test = word if not current else f"{current} {word}"
            if draw.textbbox((0,0), test, font=font)[2] <= max_width:
                current = test
            else:
                lines.append(current)
                current = word

        if current:
            lines.append(current)

        return lines

    for idx, page in enumerate(pages, start=1):

        canvas = Image.new("RGB", (page_width, page_height), "white")
        draw = ImageDraw.Draw(canvas)

        image_path = image_paths[idx-1] if idx-1 < len(image_paths) else ""

        image_area = (margin, margin, page_width-margin, margin+image_height)

        if image_path and Path(image_path).exists():

            page_image = Image.open(image_path).convert("RGB")
            page_image.thumbnail((image_area[2]-image_area[0], image_area[3]-image_area[1]))

            x = image_area[0] + ((image_area[2]-image_area[0]) - page_image.width)//2
            y = image_area[1] + ((image_area[3]-image_area[1]) - page_image.height)//2

            canvas.paste(page_image, (x,y))

        text_y = margin + image_height + gap

        # wrap text to slightly smaller width for nicer centering
        body_lines = wrap_text(draw, page.get("text",""), body_font, page_width * 0.7)

        for line in body_lines:

            line_width = draw.textbbox((0,0), line, font=body_font)[2]

            x_position = (page_width - line_width) // 2

            draw.text((x_position, text_y), line, fill="black", font=body_font)

            text_y += 50

        pdf_images.append(canvas)

    buffer = BytesIO()

    pdf_images[0].save(
        buffer,
        format="PDF",
        save_all=True,
        append_images=pdf_images[1:]
    )

    buffer.seek(0)

    return buffer.getvalue()

def generate_image_prompts(
    summary_data: Dict[str, Any],
    pages_data: Dict[str, Any],
    preferences: Dict[str, bool],
) -> Dict[str, Any]:
    system_prompt = (
        "You write children's picture-book illustration prompts. "
        "Always respond with valid JSON only and no extra text."
    )

    character_bible = summary_data.get("character_bible", "")
    style_bible = summary_data.get("style_bible", "")
    setting = summary_data.get("setting", "")

    user_prompt = f"""
Create one illustration prompt for each story page.

Story plan:
{json.dumps(summary_data, indent=2)}

Pages:
{json.dumps(pages_data, indent=2)}

Visual and sensory preferences:
{build_visual_preferences_text(preferences)}

Return JSON with this structure:
{{
  "pages": [
    {{
      "page_number": 1,
      "image_prompt": "...",
      "continuity_prompt": "..."
    }}
  ]
}}

Requirements:
- Return one prompt per page.
- Keep the main character exactly the same across every page.
- Keep the illustration style exactly the same across every page.
- Base setting context: {setting}
- Character bible: {character_bible}
- Style bible: {style_bible}
- image_prompt should describe the actual page scene.
- continuity_prompt should be a reusable instruction saying to preserve the same character identity, outfit logic, palette, rendering style, and storybook look.
- Do not include printed words in the image.
- Output valid JSON only.
"""
    raw = openrouter_chat(system_prompt, user_prompt)
    return extract_json(raw)


def generate_grok_image(prompt: str, output_path: Path) -> Optional[str]:
    if not GROK_API_KEY:
        print("Missing GROK_API_KEY")
        return None

    url = "https://api.x.ai/v1/images/generations"
    headers = {
        "Authorization": f"Bearer {GROK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "grok-imagine-image",
        "prompt": prompt,
        "aspect_ratio": "1:1",
        "resolution": "1k",
        "response_format": "b64_json",
    }

    response = requests.post(url, headers=headers, json=payload, timeout=180)

    if response.status_code != 200:
        print("xAI image error:", response.status_code, response.text)
        return None

    data = response.json()
    print("xAI image response:", data)

    if "data" in data and data["data"] and "b64_json" in data["data"][0]:
        image_bytes = base64.b64decode(data["data"][0]["b64_json"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(image_bytes)
        return str(output_path)

    return None


def generate_full_book() -> None:
    if not st.session_state.summary_data:
        raise ValueError("No summary available.")

    summary_data = st.session_state.summary_data
    page_count = st.session_state.page_count
    preferences = st.session_state.style_preferences

    pages_data = generate_page_texts(summary_data, page_count)
    image_prompts_data = generate_image_prompts(summary_data, pages_data, preferences)

    title = summary_data.get("title", "storybook")
    book_slug = slugify(title)
    book_dir = OUTPUT_DIR / book_slug
    image_paths: List[str] = []

    character_bible = summary_data.get("character_bible", "")
    style_bible = summary_data.get("style_bible", "")

    total = len(image_prompts_data.get("pages", []))
    progress = st.progress(0)

    anchor_image_path: Optional[Path] = None
    previous_image_path: Optional[Path] = None

    for idx, page in enumerate(image_prompts_data.get("pages", []), start=1):
        page_num = page["page_number"]
        base_prompt = page["image_prompt"]
        continuity_prompt = page.get("continuity_prompt", "")

        output_path = book_dir / f"page_{page_num:02d}.png"

        full_prompt = (
            f"{continuity_prompt}\n\n"
            f"Character continuity: {character_bible}\n"
            f"Style continuity: {style_bible}\n"
            f"Scene for page {page_num}: {base_prompt}\n"
            f"Keep this as a consistent children's storybook illustration. "
            f"Do not change the main character's identity or switch rendering styles."
        )

        if idx == 1:
            image_path = generate_grok_image_from_text(full_prompt, output_path)
            if image_path:
                anchor_image_path = Path(image_path)
                previous_image_path = Path(image_path)
        else:
            reference_path = previous_image_path or anchor_image_path
            if reference_path and reference_path.exists():
                edit_prompt = (
                    f"{full_prompt}\n\n"
                    f"Preserve the same exact character design, same visual universe, "
                    f"same palette family, same linework, same storybook style. "
                    f"Change only the pose, scene action, and page-specific setting needed for this page."
                )
                image_path = generate_grok_image_edit(edit_prompt, reference_path, output_path)
                if not image_path:
                    image_path = generate_grok_image_from_text(full_prompt, output_path)
            else:
                image_path = generate_grok_image_from_text(full_prompt, output_path)

            if image_path:
                previous_image_path = Path(image_path)

        image_paths.append(image_path or "")
        progress.progress(idx / max(total, 1))

    st.session_state.pages_data = pages_data
    st.session_state.image_prompts_data = image_prompts_data
    st.session_state.image_paths = image_paths
    st.session_state.current_stage = "storybook"


def regenerate_page_image(page_number: int) -> None:
    summary_data = st.session_state.summary_data
    image_prompts_data = st.session_state.image_prompts_data
    if not summary_data or not image_prompts_data:
        raise ValueError("Missing summary or image prompts.")

    title = summary_data.get("title", "storybook")
    book_slug = slugify(title)
    book_dir = OUTPUT_DIR / book_slug

    page_prompt = next(
        (p for p in image_prompts_data.get("pages", []) if p["page_number"] == page_number),
        None,
    )
    if not page_prompt:
        raise ValueError("Page prompt not found.")

    character_bible = summary_data.get("character_bible", "")
    style_bible = summary_data.get("style_bible", "")
    continuity_prompt = page_prompt.get("continuity_prompt", "")

    full_prompt = (
        f"{continuity_prompt}\n\n"
        f"Character continuity: {character_bible}\n"
        f"Style continuity: {style_bible}\n"
        f"Scene for page {page_number}: {page_prompt['image_prompt']}\n"
        f"Keep this as a consistent children's storybook illustration."
    )

    output_path = book_dir / f"page_{page_number:02d}.png"

    ref_candidates = []
    if page_number > 1 and len(st.session_state.image_paths) >= page_number - 1:
        prev_path = st.session_state.image_paths[page_number - 2]
        if prev_path:
            ref_candidates.append(Path(prev_path))
    if st.session_state.image_paths:
        first_path = st.session_state.image_paths[0]
        if first_path:
            ref_candidates.append(Path(first_path))

    image_path = None
    for ref in ref_candidates:
        if ref.exists():
            image_path = generate_grok_image_edit(full_prompt, ref, output_path)
            if image_path:
                break

    if not image_path:
        image_path = generate_grok_image_from_text(full_prompt, output_path)

    while len(st.session_state.image_paths) < page_number:
        st.session_state.image_paths.append("")
    st.session_state.image_paths[page_number - 1] = image_path or ""


def generate_grok_image_from_text(prompt: str, output_path: Path) -> Optional[str]:
    if not GROK_API_KEY:
        print("Missing GROK_API_KEY")
        return None

    url = "https://api.x.ai/v1/images/generations"
    headers = {
        "Authorization": f"Bearer {GROK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "grok-imagine-image",
        "prompt": prompt,
        "aspect_ratio": "1:1",
        "resolution": "1k",
        "response_format": "b64_json",
    }

    response = requests.post(url, headers=headers, json=payload, timeout=180)

    if response.status_code != 200:
        print("xAI image generation error:", response.status_code, response.text)
        return None

    data = response.json()
    if "data" in data and data["data"] and "b64_json" in data["data"][0]:
        image_bytes = base64.b64decode(data["data"][0]["b64_json"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(image_bytes)
        return str(output_path)

    return None

def generate_grok_image_edit(prompt: str, input_image_path: Path, output_path: Path) -> Optional[str]:
    if not GROK_API_KEY:
        print("Missing GROK_API_KEY")
        return None

    url = "https://api.x.ai/v1/images/edits"
    headers = {
        "Authorization": f"Bearer {GROK_API_KEY}",
        "Content-Type": "application/json",
    }

    suffix = input_image_path.suffix.lower()
    mime_type = "image/png"
    if suffix in [".jpg", ".jpeg"]:
        mime_type = "image/jpeg"
    elif suffix == ".webp":
        mime_type = "image/webp"

    image_b64 = base64.b64encode(input_image_path.read_bytes()).decode("utf-8")
    data_uri = f"data:{mime_type};base64,{image_b64}"

    payload = {
        "model": "grok-imagine-image",
        "prompt": prompt,
        "image": {
            "url": data_uri,
            "type": "image_url"
        },
        "response_format": "b64_json",
        "aspect_ratio": "1:1",
        "resolution": "1k",
    }

    response = requests.post(url, headers=headers, json=payload, timeout=180)

    if response.status_code != 200:
        print("xAI image edit error:", response.status_code, response.text)
        return None

    data = response.json()

    if "data" in data and data["data"] and "b64_json" in data["data"][0]:
        image_bytes = base64.b64decode(data["data"][0]["b64_json"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(image_bytes)
        return str(output_path)

    return None


def reset_project() -> None:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "Hi! Tell me the kind of children's book you want to create. "
                "For example: 'Write a storybook for my 5-year-old daughter teaching her the importance of brushing her teeth.'"
            ),
        }
    ]
    st.session_state.story_idea = ""
    st.session_state.summary_data = None
    st.session_state.pages_data = None
    st.session_state.image_prompts_data = None
    st.session_state.edit_mode = False
    st.session_state.image_paths = []
    st.session_state.current_stage = "idea"
    st.session_state.show_page_breakdown = False
    st.session_state.show_summary_editor = False
    st.session_state.is_generating_book = False
    st.session_state.selected_page = 1


# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.header("Settings")
    st.session_state.page_count = st.slider(
        "Number of pages",
        min_value=1,
        max_value=20,
        value=st.session_state.page_count,
    )

    st.subheader("Visual preferences")
    prefs = st.session_state.style_preferences
    prefs["warm_colors_only"] = st.checkbox("Warm colors only", value=prefs["warm_colors_only"])
    prefs["cool_colors_only"] = st.checkbox("Cool colors only", value=prefs["cool_colors_only"])
    prefs["less_distraction"] = st.checkbox("Less distraction", value=prefs["less_distraction"])
    prefs["colorful"] = st.checkbox("Colorful", value=prefs["colorful"])
    prefs["gentle_expressions"] = st.checkbox("Gentle expressions", value=prefs["gentle_expressions"])
    prefs["simple_backgrounds"] = st.checkbox("Simple backgrounds", value=prefs["simple_backgrounds"])
    prefs["high_contrast"] = st.checkbox("High contrast", value=prefs["high_contrast"])
    prefs["soft_pastels"] = st.checkbox("Soft pastels", value=prefs["soft_pastels"])


    if st.button("Clear Project", use_container_width=True):
        reset_project()
        st.rerun()


# ============================================================
# TITLE
# ============================================================
st.title("Storybook Generator")


# ============================================================
# CHAT HISTORY
# ============================================================
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])


# ============================================================
# CHAT INPUT
# ============================================================
user_prompt = st.chat_input("Describe the storybook you want to create")
if user_prompt:
    st.session_state.story_idea = user_prompt
    st.session_state.messages.append({"role": "user", "content": user_prompt})

    with st.chat_message("user"):
        st.write(user_prompt)

    with st.chat_message("assistant"):
        with st.status("Creating story summary..."):
            try:
                summary = generate_story_summary(
                    user_prompt,
                    st.session_state.page_count,
                    st.session_state.style_preferences,
                )
                st.session_state.summary_data = summary
                st.session_state.pages_data = None
                st.session_state.image_prompts_data = None
                st.session_state.image_paths = []
                st.session_state.current_stage = "summary"
                st.session_state.show_page_breakdown = False
                st.session_state.show_summary_editor = False

                summary_text = (
                    f"**Title:** {summary['title']}\n\n"
                    f"**Lesson:** {summary['lesson']}\n\n"
                    f"**Plotline:** {summary['summary']}\n\n"
                    "Review the summary below, then click Generate Full Storybook to build out each page."
                )
                st.write(summary_text)
                st.session_state.messages.append({"role": "assistant", "content": summary_text})
            except Exception as exc:
                error_text = f"I couldn't generate the summary: {exc}"
                st.error(error_text)
                st.session_state.messages.append({"role": "assistant", "content": error_text})


# ============================================================
# SUMMARY SECTION
# ============================================================
if st.session_state.summary_data:
    st.subheader("1. Story Summary")

    summary = st.session_state.summary_data
    st.markdown(f"### {summary.get('title', 'Untitled Story')}")
    st.write(summary.get("summary", ""))

    with st.expander("Story details"):
        st.write(f"**Lesson:** {summary.get('lesson', '')}")
        st.write(f"**Main character:** {summary.get('main_character', '')}")
        supporting = summary.get("supporting_characters", [])
        if supporting:
            st.write(f"**Supporting characters:** {', '.join(supporting)}")
        st.write(f"**Setting:** {summary.get('setting', '')}")
        st.write(f"**Art style:** {summary.get('art_style', '')}")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Show page-by-page plot breakdown", use_container_width=True):
            st.session_state.show_page_breakdown = not st.session_state.show_page_breakdown

    with col2:
        if st.button("Edit summary details", use_container_width=True):
            st.session_state.show_summary_editor = not st.session_state.show_summary_editor

    if st.session_state.show_page_breakdown:
        for idx, beat in enumerate(summary.get("plot_points", []), start=1):
            st.markdown(f"**Page idea {idx}:** {beat}")

    if st.session_state.show_summary_editor:
        edited_title = st.text_input("Title", value=summary.get("title", ""))
        edited_lesson = st.text_input("Lesson", value=summary.get("lesson", ""))
        edited_summary = st.text_area("Plotline summary", value=summary.get("summary", ""), height=140)
        edited_setting = st.text_input("Setting", value=summary.get("setting", ""))
        edited_style = st.text_input("Art style", value=summary.get("art_style", ""))

        if st.button("Save Summary Changes", use_container_width=True):
            st.session_state.summary_data["title"] = edited_title
            st.session_state.summary_data["lesson"] = edited_lesson
            st.session_state.summary_data["summary"] = edited_summary
            st.session_state.summary_data["setting"] = edited_setting
            st.session_state.summary_data["art_style"] = edited_style
            st.success("Summary updated.")

    if st.button("Generate Full Storybook", use_container_width=True):
        try:
            st.session_state.is_generating_book = True
            st.session_state.edit_mode = False
            with st.status("Building full storybook: pages, prompts, and images..."):
                generate_full_book()
            st.success("Full storybook generated.")
        except Exception as exc:
            st.error(f"Could not generate storybook: {exc}")
        finally:
            st.session_state.is_generating_book = False

# ============================================================
# STORYBOOK PREVIEW
# ============================================================
if st.session_state.pages_data:
    st.subheader("2. Storybook Preview")

    summary = st.session_state.summary_data or {}
    pages = st.session_state.pages_data.get("pages", [])
    total_pages = len(pages)

    if total_pages > 0:
        st.markdown(f"## {summary.get('title', 'Untitled Story')}")
        st.markdown(f"**Lesson:** {summary.get('lesson', '')}")

        current_page = next(
            (p for p in pages if p["page_number"] == st.session_state.selected_page),
            pages[0],
        )
        current_index = current_page["page_number"] - 1
        current_image_path = st.session_state.image_paths[current_index] if current_index < len(st.session_state.image_paths) else ""

        prompt_lookup: Dict[int, str] = {}
        if st.session_state.image_prompts_data:
            for item in st.session_state.image_prompts_data.get("pages", []):
                prompt_lookup[item["page_number"]] = item["image_prompt"]

        if not st.session_state.edit_mode:
            top1, top2, top3 = st.columns([1, 2, 1])
            with top2:
                st.markdown(
                    f"<div style='text-align:center; font-size:1.1rem; margin-bottom:0.75rem;'><strong>Page {st.session_state.selected_page} of {total_pages}</strong></div>",
                    unsafe_allow_html=True,
                )

            left_arrow, book_col, right_arrow = st.columns([0.08, 0.84, 0.08])

            with left_arrow:
                st.markdown("<div style='height:260px;'></div>", unsafe_allow_html=True)
                if st.button("←", use_container_width=True, disabled=st.session_state.selected_page <= 1):
                    st.session_state.selected_page = max(1, st.session_state.selected_page - 1)
                    st.rerun()

            with book_col:
                book_left, book_right = st.columns([1.15, 0.85])

                with book_left:
                    if current_image_path and Path(current_image_path).exists():
                        st.image(current_image_path, use_container_width=True)
                    else:
                        st.warning("No image generated for this page.")

                with book_right:
                    st.write(current_page.get("text", ""))

            with right_arrow:
                st.markdown("<div style='height:260px;'></div>", unsafe_allow_html=True)
                if st.button("→", use_container_width=True, disabled=st.session_state.selected_page >= total_pages):
                    st.session_state.selected_page = min(total_pages, st.session_state.selected_page + 1)
                    st.rerun()

            st.divider()

            action1, action2, action3 = st.columns([1, 1, 1])

            with action1:
                if st.button("Edit Page", use_container_width=True):
                    st.session_state.edit_mode = True
                    st.rerun()

            with action2:
                with st.expander("Go to a specific page"):
                    chosen_page = st.selectbox(
                        "Select page",
                        [page["page_number"] for page in pages],
                        index=max(0, st.session_state.selected_page - 1),
                    )
                    if chosen_page != st.session_state.selected_page:
                        st.session_state.selected_page = chosen_page
                        st.rerun()

            with action3:
                try:
                    pdf_bytes = create_storybook_pdf()
                    pdf_name = f"{slugify(summary.get('title', 'storybook'))}.pdf"
                    st.download_button(
                        "Download Storybook PDF",
                        data=pdf_bytes,
                        file_name=pdf_name,
                        mime="application/pdf",
                        use_container_width=True,
                    )
                except Exception as exc:
                    st.warning(f"PDF unavailable: {exc}")

        else:
            st.subheader(f"Edit Page {st.session_state.selected_page}")

            current_prompt = prompt_lookup.get(st.session_state.selected_page, "")

            edited_page_text = st.text_area(
                "Page text",
                value=current_page.get("text", ""),
                height=140,
                key=f"page_text_{st.session_state.selected_page}",
            )

            edited_image_prompt = st.text_area(
                "Image prompt",
                value=current_prompt,
                height=220,
                key=f"image_prompt_{st.session_state.selected_page}",
            )

            edit_col1, edit_col2, edit_col3 = st.columns(3)

            with edit_col1:
                if st.button("Save Page Text", use_container_width=True):
                    current_page["text"] = edited_page_text
                    st.success("Page text updated.")

            with edit_col2:
                if st.button("Save Image Prompt + Regenerate Image", use_container_width=True):
                    for item in st.session_state.image_prompts_data.get("pages", []):
                        if item["page_number"] == st.session_state.selected_page:
                            item["image_prompt"] = edited_image_prompt
                            break
                    try:
                        with st.status("Regenerating page image..."):
                            regenerate_page_image(st.session_state.selected_page)
                        st.success("Page image regenerated.")
                    except Exception as exc:
                        st.error(f"Could not regenerate page image: {exc}")

            with edit_col3:
                if st.button("Back to Storybook", use_container_width=True):
                    st.session_state.edit_mode = False
                    st.rerun()

            if st.session_state.image_prompts_data:
                with st.expander("Character and style continuity settings"):
                    st.write("**Character bible:**")
                    st.write(st.session_state.image_prompts_data.get("character_bible", ""))
                    st.write("**Style bible:**")
                    st.write(st.session_state.image_prompts_data.get("style_bible", ""))
       