from __future__ import annotations

import re
import shutil
import subprocess
import textwrap
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory, url_for
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
UPLOAD_DIR = OUTPUT_DIR / "uploaded-photos"
NORMALIZED_DIR = OUTPUT_DIR / "normalized-photos"

OUTPUT_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)
NORMALIZED_DIR.mkdir(exist_ok=True)

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_PHOTOS = 20


@dataclass
class Scene:
    number: int
    title: str
    narration: str
    visual_prompt: str
    duration_seconds: int


DURATION_SETTINGS = {
    "30 δευτερόλεπτα": (30, 3),
    "1 λεπτό": (60, 6),
    "2 λεπτά": (120, 10),
    "5 λεπτά": (300, 20),
}


def clean_text(text: str) -> str:
    """Καθαρίζει τα περιττά κενά χωρίς να αλλοιώνει την ιστορία."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def calculate_scene_count(story: str, requested_scenes: int) -> int:
    """Επιλέγει ασφαλή αριθμό σκηνών, χωρίς σκηνές με ελάχιστες λέξεις."""
    word_count = len(story.split())
    if word_count == 0:
        return 0

    possible_scenes = max(1, word_count // 5)
    return max(1, min(requested_scenes, possible_scenes))


def split_story_balanced(story: str, scene_count: int) -> list[str]:
    """Χωρίζει όλη την ιστορία σε ισορροπημένα τμήματα."""
    words = story.split()
    if not words or scene_count <= 0:
        return []

    scene_count = min(scene_count, len(words))
    base_size, remainder = divmod(len(words), scene_count)

    scenes: list[str] = []
    start = 0

    for index in range(scene_count):
        size = base_size + (1 if index < remainder else 0)
        end = start + size
        scene_text = " ".join(words[start:end]).strip()
        if scene_text:
            scenes.append(scene_text)
        start = end

    return scenes


def build_visual_prompt(scene_text: str, style: str, video_format: str) -> str:
    """Δημιουργεί την περιγραφή της σκηνής για μελλοντική χρήση."""
    format_hint = {
        "Κάθετο": "κάθετο κάδρο 9:16",
        "Οριζόντιο": "οριζόντιο κάδρο 16:9",
        "Τετράγωνο": "τετράγωνο κάδρο 1:1",
    }.get(video_format, "κάθετο κάδρο 9:16")

    return (
        f"{style} κινηματογραφική σκηνή, {format_hint}, φυσικός φωτισμός, "
        "σταθεροί χαρακτήρες, ίδια πρόσωπα και ίδια ρούχα σε όλες τις σκηνές, "
        f"ρεαλιστική κίνηση και λεπτομέρειες. Περιεχόμενο: {scene_text}"
    )


def distribute_durations(total_seconds: int, scene_count: int) -> list[int]:
    """Μοιράζει όλη τη διάρκεια ισόποσα στις σκηνές."""
    if scene_count <= 0:
        return []

    base_duration, remainder = divmod(total_seconds, scene_count)
    return [
        base_duration + (1 if index < remainder else 0)
        for index in range(scene_count)
    ]


def create_storyboard(
    story: str,
    style: str,
    duration_label: str,
    video_format: str,
) -> list[Scene]:
    total_seconds, requested_scenes = DURATION_SETTINGS.get(duration_label, (60, 6))
    scene_count = calculate_scene_count(story, requested_scenes)
    grouped = split_story_balanced(story, scene_count)

    if not grouped:
        return []

    durations = distribute_durations(total_seconds, len(grouped))

    scenes: list[Scene] = []
    for index, (scene_text, scene_duration) in enumerate(
        zip(grouped, durations, strict=True), start=1
    ):
        scenes.append(
            Scene(
                number=index,
                title=f"Σκηνή {index}",
                narration=scene_text,
                visual_prompt=build_visual_prompt(scene_text, style, video_format),
                duration_seconds=scene_duration,
            )
        )

    return scenes


def video_dimensions(video_format: str) -> tuple[int, int]:
    """Επιστρέφει ανάλυση προεπισκόπησης για γρήγορη δημιουργία στο κινητό."""
    return {
        "Κάθετο": (480, 854),
        "Οριζόντιο": (854, 480),
        "Τετράγωνο": (600, 600),
    }.get(video_format, (480, 854))


def clear_directory(directory: Path) -> None:
    """Διαγράφει μόνο τα παλιά προσωρινά αρχεία του συγκεκριμένου φακέλου."""
    directory.mkdir(parents=True, exist_ok=True)
    for item in directory.iterdir():
        if item.is_file() or item.is_symlink():
            item.unlink(missing_ok=True)
        elif item.is_dir():
            shutil.rmtree(item)


def run_process(
    command: list[str],
    *,
    title: str,
    timeout: int = 900,
) -> None:
    """Εκτελεί εξωτερικό εργαλείο και εμφανίζει καθαρό σφάλμα στο Τέρμουξ."""
    result = subprocess.run(
        command,
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )

    if result.returncode == 0:
        return

    error_text = (result.stderr or result.stdout).strip()
    print(f"\n--- ΣΦΑΛΜΑ {title.upper()} ---", flush=True)
    print(error_text or "Δεν δόθηκαν λεπτομέρειες σφάλματος.", flush=True)
    print(f"--- ΤΕΛΟΣ ΣΦΑΛΜΑΤΟΣ {title.upper()} ---\n", flush=True)

    details = error_text.splitlines()
    last_line = details[-1] if details else f"Άγνωστο σφάλμα: {title}."
    raise RuntimeError(last_line)


def run_ffmpeg(command: list[str]) -> None:
    run_process(command, title="φφμεγκ")


def save_uploaded_photos(uploaded_files: list) -> list[Path]:
    """Αποθηκεύει με ασφάλεια έως είκοσι φωτογραφίες του χρήστη."""
    clear_directory(UPLOAD_DIR)
    saved: list[Path] = []

    real_files = [
        photo
        for photo in uploaded_files
        if photo and str(getattr(photo, "filename", "")).strip()
    ]

    if len(real_files) > MAX_PHOTOS:
        raise ValueError(f"Μπορείς να βάλεις έως {MAX_PHOTOS} φωτογραφίες.")

    for index, photo in enumerate(real_files, start=1):
        original_name = str(photo.filename)
        extension = Path(original_name).suffix.lower()

        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            raise ValueError(
                "Επιτρέπονται μόνο φωτογραφίες JPG, JPEG, PNG ή WEBP."
            )

        safe_stem = secure_filename(Path(original_name).stem) or f"photo-{index}"
        target = UPLOAD_DIR / f"{index:02d}-{safe_stem}{extension}"
        photo.save(target)

        if target.exists() and target.stat().st_size > 0:
            saved.append(target)

    return saved


def default_image_paths() -> list[Path]:
    """Επιστρέφει τις τρεις δοκιμαστικές εικόνες όταν δεν ανέβηκαν φωτογραφίες."""
    paths = [
        BASE_DIR / "static" / "images" / "scene-1.png",
        BASE_DIR / "static" / "images" / "scene-2.png",
        BASE_DIR / "static" / "images" / "scene-3.png",
    ]

    missing = [path.name for path in paths if not path.exists()]
    if missing:
        raise RuntimeError(f"Λείπουν εικόνες προεπισκόπησης: {', '.join(missing)}")

    return paths


def normalize_images(
    source_images: list[Path],
    video_format: str,
) -> list[Path]:
    """Μετατρέπει όλες τις φωτογραφίες σε ίδιο μέγεθος και ίδια μορφή PNG."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("Το φφμεγκ δεν βρέθηκε στο Τέρμουξ.")

    clear_directory(NORMALIZED_DIR)
    width, height = video_dimensions(video_format)
    video_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        "setsar=1"
    )

    normalized: list[Path] = []

    for index, source in enumerate(source_images, start=1):
        target = NORMALIZED_DIR / f"photo-{index:02d}.png"
        command = [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-vf",
            video_filter,
            "-frames:v",
            "1",
            str(target),
        ]
        run_ffmpeg(command)

        if not target.exists() or target.stat().st_size == 0:
            raise RuntimeError(f"Δεν μπόρεσε να διαβαστεί η φωτογραφία {index}.")

        normalized.append(target)

    return normalized


def create_preview_video(
    scenes: list[Scene],
    video_format: str,
    source_images: list[Path],
    using_own_photos: bool,
) -> str:
    """Δημιουργεί ΜΡ4 από τις φωτογραφίες που επέλεξε ο χρήστης."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("Το φφμεγκ δεν βρέθηκε στο Τέρμουξ.")

    normalized_images = normalize_images(source_images, video_format)

    list_path = OUTPUT_DIR / "lista-skinon.txt"
    output_name = (
        "vinteo-apo-dikes-mou-fotografies.mp4"
        if using_own_photos
        else "dokimastiko-vinteo.mp4"
    )
    output_path = OUTPUT_DIR / output_name

    selected_images: list[Path] = []
    with list_path.open("w", encoding="utf-8") as file:
        for index, scene in enumerate(scenes):
            image_path = normalized_images[index % len(normalized_images)].resolve()
            selected_images.append(image_path)
            file.write(f"file '{image_path.as_posix()}'\n")
            file.write(f"duration {scene.duration_seconds}\n")

        file.write(f"file '{selected_images[-1].as_posix()}'\n")

    common = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-vf",
        "format=yuv420p",
        "-fps_mode",
        "vfr",
        "-movflags",
        "+faststart",
    ]

    try:
        run_ffmpeg(
            common
            + [
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "28",
                str(output_path),
            ]
        )
    except RuntimeError:
        run_ffmpeg(
            common
            + [
                "-c:v",
                "mpeg4",
                "-q:v",
                "5",
                str(output_path),
            ]
        )

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("Το αρχείο βίντεο δεν δημιουργήθηκε σωστά.")

    return output_path.name


def ass_timestamp(total_seconds: float) -> str:
    """Μετατρέπει δευτερόλεπτα σε χρόνο μορφής ASS."""
    total_centiseconds = max(0, round(total_seconds * 100))
    hours, remainder = divmod(total_centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def escape_ass_text(text: str, line_width: int) -> str:
    """Καθαρίζει και χωρίζει μία μικρή φράση σε έως δύο γραμμές."""
    safe_text = (
        text.replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .strip()
    )
    wrapped = textwrap.wrap(
        safe_text,
        width=line_width,
        break_long_words=False,
        break_on_hyphens=False,
        max_lines=2,
        placeholder="…",
    )
    return r"\N".join(wrapped) if wrapped else safe_text


def split_subtitle_chunks(text: str, max_words: int = 5) -> list[str]:
    """Χωρίζει κάθε σκηνή σε μικρές φράσεις που αλλάζουν διαδοχικά."""
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    current: list[str] = []

    for word in words:
        current.append(word)
        ends_phrase = word.rstrip().endswith((".", "!", "?", ";", ":", ","))
        reached_limit = len(current) >= max_words

        if reached_limit or (ends_phrase and len(current) >= 3):
            chunks.append(" ".join(current).strip())
            current = []

    if current:
        if chunks and len(current) <= 2:
            chunks[-1] = f"{chunks[-1]} {' '.join(current)}".strip()
        else:
            chunks.append(" ".join(current).strip())

    return [chunk for chunk in chunks if chunk]


def create_ass_subtitles(scenes: list[Scene], video_format: str) -> Path:
    """Δημιουργεί μικρούς ελληνικούς υπότιτλους που αλλάζουν συνεχώς."""
    width, height = video_dimensions(video_format)
    style_settings = {
        "Κάθετο": (25, 24, 72),
        "Οριζόντιο": (24, 46, 34),
        "Τετράγωνο": (25, 34, 46),
    }
    font_size, line_width, margin_vertical = style_settings.get(
        video_format,
        (25, 24, 72),
    )

    subtitle_path = OUTPUT_DIR / "ellinikoi-ypotitloi.ass"
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes
WrapStyle: 2
Timer: 100.0000

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,sans-serif,{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&HA0000000,-1,0,0,0,100,100,0,0,3,2,0,2,22,22,{margin_vertical},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events: list[str] = []
    scene_start = 0.0

    for scene in scenes:
        chunks = split_subtitle_chunks(scene.narration, max_words=5)
        scene_duration = float(scene.duration_seconds)

        if not chunks:
            scene_start += scene_duration
            continue

        word_counts = [max(1, len(chunk.split())) for chunk in chunks]
        total_words = max(1, sum(word_counts))
        words_before = 0

        for index, (chunk, word_count) in enumerate(zip(chunks, word_counts)):
            start_time = scene_start + scene_duration * words_before / total_words
            words_before += word_count
            natural_end = scene_start + scene_duration * words_before / total_words

            end_time = natural_end
            if index < len(chunks) - 1:
                end_time = max(start_time + 0.35, natural_end - 0.06)

            subtitle_text = escape_ass_text(chunk, line_width)
            events.append(
                "Dialogue: 0,"
                f"{ass_timestamp(start_time)},{ass_timestamp(end_time)},"
                f"Default,,0,0,0,,{subtitle_text}"
            )

        scene_start += scene_duration

    subtitle_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return subtitle_path


def burn_subtitles(
    video_filename: str,
    scenes: list[Scene],
    video_format: str,
    using_own_photos: bool,
) -> str:
    """Ενσωματώνει μόνιμα τους ελληνικούς υπότιτλους στο βίντεο."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("Το φφμεγκ δεν βρέθηκε στο Τέρμουξ.")

    video_path = OUTPUT_DIR / video_filename
    subtitle_path = create_ass_subtitles(scenes, video_format)
    output_name = (
        "kinoumeno-vinteo-me-ellinikous-ypotitlous.mp4"
        if using_own_photos
        else "dokimastiko-vinteo-me-ellinikous-ypotitlous.mp4"
    )
    output_path = OUTPUT_DIR / output_name
    output_path.unlink(missing_ok=True)

    subtitle_filter = f"ass={subtitle_path.as_posix()}"
    common = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        "-vf",
        subtitle_filter,
        "-an",
        "-movflags",
        "+faststart",
    ]

    try:
        run_ffmpeg(
            common
            + [
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "27",
                "-pix_fmt",
                "yuv420p",
                str(output_path),
            ]
        )
    except RuntimeError:
        run_ffmpeg(
            common
            + [
                "-c:v",
                "mpeg4",
                "-q:v",
                "5",
                "-pix_fmt",
                "yuv420p",
                str(output_path),
            ]
        )

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("Το βίντεο με ελληνικούς υπότιτλους δεν δημιουργήθηκε.")

    return output_path.name



def resolve_voice(
    voice_label: str,
    language: str,
) -> tuple[str | None, str]:
    # Επιλέγει ελληνική ή αγγλική φωνή.
    if voice_label == "Χωρίς αφήγηση":
        return None, "Χωρίς αφήγηση"

    english = language == "Αγγλικά"
    male = voice_label == "Ανδρική φωνή"

    if english and male:
        return "en-US-GuyNeural", "Ανδρική αγγλική φωνή"
    if english:
        return "en-US-JennyNeural", "Γυναικεία αγγλική φωνή"
    if male:
        return "el-GR-NestorasNeural", "Ανδρική ελληνική φωνή"
    return "el-GR-AthinaNeural", "Γυναικεία ελληνική φωνή"


def create_narration(
    story: str,
    voice_label: str,
    language: str,
) -> tuple[str | None, str, str | None]:
    # Δημιουργεί αφήγηση και συγχρονισμένους υπότιτλους.
    voice_name, friendly_name = resolve_voice(voice_label, language)
    if voice_name is None:
        return None, friendly_name, None

    edge_tts = shutil.which("edge-tts")
    if not edge_tts:
        raise RuntimeError(
            "Το edge-tts δεν βρέθηκε. Γράψε: pip install edge-tts"
        )

    audio_path = OUTPUT_DIR / "afhghsh.mp3"
    subtitle_path = OUTPUT_DIR / "afhghsh.srt"
    audio_path.unlink(missing_ok=True)
    subtitle_path.unlink(missing_ok=True)

    command = [
        edge_tts,
        "--voice",
        voice_name,
        "--text",
        story,
        "--write-media",
        str(audio_path),
        "--write-subtitles",
        str(subtitle_path),
    ]
    run_process(command, title="αφήγησης", timeout=600)

    if not audio_path.exists() or audio_path.stat().st_size == 0:
        raise RuntimeError("Η αφήγηση δεν δημιουργήθηκε σωστά.")

    subtitle_name = None
    if subtitle_path.exists() and subtitle_path.stat().st_size > 0:
        subtitle_name = subtitle_path.name

    return audio_path.name, friendly_name, subtitle_name


def _srt_time_to_ms(value: str) -> int:
    hours, minutes, rest = value.strip().replace(".", ",").split(":")
    seconds, milliseconds = rest.split(",")
    return (
        int(hours) * 3_600_000
        + int(minutes) * 60_000
        + int(seconds) * 1_000
        + int(milliseconds)
    )


def _ms_to_srt_time(value: int) -> str:
    value = max(0, int(value))
    hours, remainder = divmod(value, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def _split_subtitle_text(text: str, max_chars: int = 25) -> list[str]:
    clean = re.sub(r"<[^>]+>", "", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    if not clean:
        return []

    words = clean.split(" ")
    chunks: list[str] = []
    current: list[str] = []

    for word in words:
        candidate = " ".join(current + [word]).strip()
        punctuation_break = bool(
            current and re.search(r"[.!?;·,:]$", current[-1])
        )

        if current and (
            len(candidate) > max_chars
            or len(current) >= 4
            or punctuation_break
        ):
            chunks.append(" ".join(current))
            current = [word]
        else:
            current.append(word)

    if current:
        chunks.append(" ".join(current))

    return chunks


def prepare_compact_subtitles(
    subtitle_filename: str,
    video_format: str,
) -> Path:
    source_path = OUTPUT_DIR / subtitle_filename
    if not source_path.exists():
        raise RuntimeError("Δεν βρέθηκαν οι χρονισμένοι υπότιτλοι.")

    raw = source_path.read_text(encoding="utf-8-sig", errors="replace")
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", raw.strip())

    max_chars = {
        "Κάθετο": 22,
        "Οριζόντιο": 34,
        "Τετράγωνο": 26,
    }.get(video_format, 22)

    time_pattern = re.compile(
        r"(?P<start>\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*"
        r"(?P<end>\d{2}:\d{2}:\d{2}[,.]\d{3})"
    )

    output_blocks: list[str] = []
    cue_number = 1

    for block in blocks:
        lines = [
            line.strip()
            for line in block.split("\n")
            if line.strip()
        ]
        time_index = next(
            (i for i, line in enumerate(lines) if "-->" in line),
            None,
        )
        if time_index is None:
            continue

        match = time_pattern.search(lines[time_index])
        if not match:
            continue

        text = " ".join(lines[time_index + 1 :]).strip()
        chunks = _split_subtitle_text(text, max_chars=max_chars)
        if not chunks:
            continue

        start_ms = _srt_time_to_ms(match.group("start"))
        end_ms = _srt_time_to_ms(match.group("end"))
        total_ms = max(500, end_ms - start_ms)

        weights = [
            max(1, len(chunk.replace(" ", "")))
            for chunk in chunks
        ]
        total_weight = sum(weights)
        cursor = start_ms

        for index, (chunk, weight) in enumerate(
            zip(chunks, weights)
        ):
            if index == len(chunks) - 1:
                chunk_end = end_ms
            else:
                duration = max(
                    350,
                    round(total_ms * weight / total_weight),
                )
                chunk_end = min(end_ms, cursor + duration)

            if chunk_end <= cursor:
                chunk_end = min(end_ms, cursor + 350)

            output_blocks.append(
                f"{cue_number}\n"
                f"{_ms_to_srt_time(cursor)} --> "
                f"{_ms_to_srt_time(chunk_end)}\n"
                f"{chunk}"
            )
            cue_number += 1
            cursor = chunk_end

            if cursor >= end_ms:
                break

    if not output_blocks:
        raise RuntimeError(
            "Δεν δημιουργήθηκαν μικρές φράσεις υποτίτλων."
        )

    output_path = (
        OUTPUT_DIR / "afhghsh-mikres-fraseis.srt"
    )
    output_path.write_text(
        "\n\n".join(output_blocks) + "\n",
        encoding="utf-8",
    )
    return output_path


def burn_synced_subtitles(
    video_filename: str,
    subtitle_filename: str,
    video_format: str,
    using_own_photos: bool,
) -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("Το φφμεγκ δεν βρέθηκε στο Τέρμουξ.")

    video_path = OUTPUT_DIR / video_filename
    subtitle_path = prepare_compact_subtitles(
        subtitle_filename,
        video_format,
    )

    style_settings = {
        "Κάθετο": (8, 54),
        "Οριζόντιο": (13, 28),
        "Τετράγωνο": (10, 40),
    }
    font_size, margin_vertical = style_settings.get(
        video_format,
        (8, 54),
    )

    escaped_path = (
        subtitle_path.resolve().as_posix().replace("'", r"\'")
    )
    subtitle_filter = (
        f"subtitles='{escaped_path}':"
        "force_style='FontName=DejaVu Sans,"
        f"FontSize={font_size},"
        "PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,"
        "BackColour=&H80000000,"
        "Bold=1,"
        "BorderStyle=1,"
        "Outline=2,"
        "Shadow=0,"
        "Alignment=2,"
        f"MarginV={margin_vertical}'"
    )

    output_name = (
        "dikes-mou-fotografies-me-mikrous-ypotitlous.mp4"
        if using_own_photos
        else "vinteo-me-mikrous-ypotitlous.mp4"
    )
    output_path = OUTPUT_DIR / output_name
    output_path.unlink(missing_ok=True)

    common = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        "-vf",
        subtitle_filter,
        "-an",
        "-movflags",
        "+faststart",
    ]

    try:
        run_ffmpeg(
            common
            + [
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "27",
                "-pix_fmt",
                "yuv420p",
                str(output_path),
            ]
        )
    except RuntimeError:
        run_ffmpeg(
            common
            + [
                "-c:v",
                "mpeg4",
                "-q:v",
                "5",
                "-pix_fmt",
                "yuv420p",
                str(output_path),
            ]
        )

    if (
        not output_path.exists()
        or output_path.stat().st_size == 0
    ):
        raise RuntimeError(
            "Το βίντεο με μικρούς υπότιτλους δεν δημιουργήθηκε."
        )

    return output_path.name



def combine_video_and_narration(
    video_filename: str,
    narration_filename: str,
    using_own_photos: bool,
    subtitles_added: bool,
) -> str:
    """Ενώνει το βίντεο με την ελληνική αφήγηση."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("Το φφμεγκ δεν βρέθηκε στο Τέρμουξ.")

    video_path = OUTPUT_DIR / video_filename
    narration_path = OUTPUT_DIR / narration_filename
    if using_own_photos and subtitles_added:
        output_name = "dikes-mou-fotografies-me-afhghsh-kai-ypotitlous.mp4"
    elif using_own_photos:
        output_name = "dikes-mou-fotografies-me-elliniki-afhghsh.mp4"
    elif subtitles_added:
        output_name = "vinteo-me-afhghsh-kai-ypotitlous.mp4"
    else:
        output_name = "vinteo-me-elliniki-afhghsh.mp4"
    output_path = OUTPUT_DIR / output_name

    command = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(narration_path),
        "-filter_complex",
        "[1:a]apad[audio]",
        "-map",
        "0:v:0",
        "-map",
        "[audio]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    run_ffmpeg(command)

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("Το βίντεο με αφήγηση δεν δημιουργήθηκε σωστά.")

    return output_path.name


@app.errorhandler(413)
def too_large(_error):
    return jsonify(
        {
            "ok": False,
            "message": "Οι φωτογραφίες είναι πολύ μεγάλες. Το συνολικό όριο είναι 100 MB.",
        }
    ), 413


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/download/<path:filename>")
def download_video(filename: str):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)


@app.post("/api/dimiourgia")
def dimiourgia():
    if request.mimetype == "multipart/form-data":
        data = request.form
        uploaded_files = request.files.getlist("photos")
    else:
        data = request.get_json(silent=True) or {}
        uploaded_files = []

    story = clean_text(str(data.get("story", "")))

    if not story:
        return jsonify({"ok": False, "message": "Γράψε πρώτα την ιστορία σου."}), 400

    if len(story) > 2000:
        return jsonify(
            {"ok": False, "message": "Η ιστορία ξεπερνά τους 2.000 χαρακτήρες."}
        ), 400

    options = {
        "style": str(data.get("style", "Ρεαλιστικό")),
        "duration": str(data.get("duration", "1 λεπτό")),
        "language": str(data.get("language", "Ελληνικά")),
        "voice": str(data.get("voice", "Γυναικεία φωνή")),
        "format": str(data.get("format", "Κάθετο")),
        "subtitles": str(data.get("subtitles", "Με υπότιτλους")),
    }

    scenes = create_storyboard(
        story=story,
        style=options["style"],
        duration_label=options["duration"],
        video_format=options["format"],
    )

    if not scenes:
        return jsonify(
            {"ok": False, "message": "Δεν μπόρεσαν να δημιουργηθούν σκηνές."}
        ), 400

    try:
        uploaded_photo_paths = save_uploaded_photos(uploaded_files)
    except ValueError as error:
        return jsonify({"ok": False, "message": str(error)}), 400

    using_own_photos = bool(uploaded_photo_paths)
    source_images = (
        uploaded_photo_paths
        if using_own_photos
        else default_image_paths()
    )

    video_url = None
    video_error = None
    narration_added = False
    narration_error = None
    voice_used = "Χωρίς αφήγηση"
    subtitles_added = False
    subtitles_error = None

    try:
        silent_video_filename = create_preview_video(
            scenes,
            options["format"],
            source_images,
            using_own_photos,
        )
        final_video_filename = silent_video_filename

        narration_filename = None
        timed_subtitles_filename = None

        if options["voice"] != "Χωρίς αφήγηση":
            try:
                (
                    narration_filename,
                    voice_used,
                    timed_subtitles_filename,
                ) = create_narration(
                    story,
                    options["voice"],
                    options["language"],
                )
            except (RuntimeError, subprocess.TimeoutExpired) as error:
                narration_error = str(error)

        if options["subtitles"] != "Χωρίς υπότιτλους":
            try:
                if timed_subtitles_filename:
                    final_video_filename = burn_synced_subtitles(
                        silent_video_filename,
                        timed_subtitles_filename,
                        options["format"],
                        using_own_photos,
                    )
                else:
                    final_video_filename = burn_subtitles(
                        silent_video_filename,
                        scenes,
                        options["format"],
                        using_own_photos,
                    )
                subtitles_added = True
            except (RuntimeError, subprocess.TimeoutExpired) as error:
                subtitles_error = str(error)

        if narration_filename:
            try:
                final_video_filename = combine_video_and_narration(
                    final_video_filename,
                    narration_filename,
                    using_own_photos,
                    subtitles_added,
                )
                narration_added = True
            except (RuntimeError, subprocess.TimeoutExpired) as error:
                narration_error = str(error)

        video_url = url_for("download_video", filename=final_video_filename)
        video_url = f"{video_url}?t={int(time.time())}"

    except (RuntimeError, subprocess.TimeoutExpired) as error:
        video_error = str(error)

    return jsonify(
        {
            "ok": True,
            "message": f"Η ιστορία χωρίστηκε σε {len(scenes)} σκηνές.",
            "story": story,
            "options": options,
            "scene_count": len(scenes),
            "scenes": [asdict(scene) for scene in scenes],
            "video_url": video_url,
            "video_error": video_error,
            "narration_added": narration_added,
            "narration_error": narration_error,
            "voice_used": voice_used,
            "subtitles_added": subtitles_added,
            "subtitles_error": subtitles_error,
            "using_own_photos": using_own_photos,
            "photo_count": len(source_images),
            "language": options["language"],
        }
    )



def _motion_filter_v9(width: int, height: int, scene_index: int, duration: int) -> tuple[str, int]:
    fps = 25
    frames = max(1, duration * fps)
    last = max(1, frames - 1)
    mode = scene_index % 6

    if mode == 0:
        zoom, x, y = f"1+0.12*on/{last}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif mode == 1:
        zoom, x, y = f"1.12-0.12*on/{last}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif mode == 2:
        zoom, x, y = "1.10", f"(iw-iw/zoom)*on/{last}", "ih/2-(ih/zoom/2)"
    elif mode == 3:
        zoom, x, y = "1.10", f"(iw-iw/zoom)*(1-on/{last})", "ih/2-(ih/zoom/2)"
    elif mode == 4:
        zoom, x, y = "1.10", "iw/2-(iw/zoom/2)", f"(ih-ih/zoom)*on/{last}"
    else:
        zoom, x, y = "1.10", "iw/2-(iw/zoom/2)", f"(ih-ih/zoom)*(1-on/{last})"

    return (
        f"zoompan=z='{zoom}':x='{x}':y='{y}':d=1:"
        f"s={width}x{height}:fps={fps},format=yuv420p"
    ), frames


def _make_motion_clip_v9(
    ffmpeg: str,
    image_path: Path,
    clip_path: Path,
    scene_index: int,
    duration: int,
    width: int,
    height: int,
    codec: str,
) -> None:
    video_filter, frames = _motion_filter_v9(
        width, height, scene_index, duration
    )

    command = [
        ffmpeg, "-y", "-loglevel", "error",
        "-loop", "1", "-framerate", "25",
        "-i", str(image_path),
        "-vf", video_filter,
        "-frames:v", str(frames),
        "-an",
    ]

    if codec == "libx264":
        command += [
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            "-pix_fmt", "yuv420p",
        ]
    else:
        command += [
            "-c:v", "mpeg4",
            "-q:v", "5",
            "-pix_fmt", "yuv420p",
        ]

    command.append(str(clip_path))
    run_ffmpeg(command)


def create_preview_video(
    scenes: list[Scene],
    video_format: str,
    source_images: list[Path],
    using_own_photos: bool,
) -> str:
    """Δημιουργεί βίντεο με ζουμ και ομαλή κίνηση στις φωτογραφίες."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("Το φφμεγκ δεν βρέθηκε στο Τέρμουξ.")

    normalized = normalize_images(source_images, video_format)
    clips_dir = OUTPUT_DIR / "scene-clips"
    clear_directory(clips_dir)
    width, height = video_dimensions(video_format)

    def build(codec: str) -> list[Path]:
        clear_directory(clips_dir)
        clips: list[Path] = []

        for index, scene in enumerate(scenes):
            image = normalized[index % len(normalized)]
            clip = clips_dir / f"scene-{index + 1:02d}.mp4"
            _make_motion_clip_v9(
                ffmpeg,
                image,
                clip,
                index,
                scene.duration_seconds,
                width,
                height,
                codec,
            )
            clips.append(clip)

        return clips

    try:
        clips = build("libx264")
        codec = "libx264"
    except RuntimeError:
        clips = build("mpeg4")
        codec = "mpeg4"

    list_file = OUTPUT_DIR / "lista-kinoumenon-skinon.txt"
    with list_file.open("w", encoding="utf-8") as file:
        for clip in clips:
            file.write(f"file '{clip.resolve().as_posix()}'\n")

    output_name = (
        "kinoumeno-vinteo-apo-dikes-mou-fotografies.mp4"
        if using_own_photos
        else "kinoumeno-dokimastiko-vinteo.mp4"
    )
    output_path = OUTPUT_DIR / output_name
    output_path.unlink(missing_ok=True)

    concat = [
        ffmpeg, "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        "-movflags", "+faststart",
        str(output_path),
    ]

    try:
        run_ffmpeg(concat)
    except RuntimeError:
        command = [
            ffmpeg, "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0",
            "-i", str(list_file),
        ]

        if codec == "libx264":
            command += [
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "28",
            ]
        else:
            command += ["-c:v", "mpeg4", "-q:v", "5"]

        command += [
            "-pix_fmt", "yuv420p",
            "-an",
            "-movflags", "+faststart",
            str(output_path),
        ]
        run_ffmpeg(command)

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("Το κινούμενο βίντεο δεν δημιουργήθηκε σωστά.")

    return output_path.name



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
