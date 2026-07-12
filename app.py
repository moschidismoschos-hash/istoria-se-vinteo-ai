from __future__ import annotations

import re
import shutil
import subprocess
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


def resolve_greek_voice(voice_label: str) -> tuple[str | None, str]:
    """Μετατρέπει την επιλογή της εφαρμογής σε διαθέσιμη ελληνική φωνή."""
    if voice_label == "Χωρίς αφήγηση":
        return None, "Χωρίς αφήγηση"

    if voice_label == "Ανδρική φωνή":
        return "el-GR-NestorasNeural", "Ανδρική ελληνική φωνή"

    return "el-GR-AthinaNeural", "Γυναικεία ελληνική φωνή"


def create_greek_narration(story: str, voice_label: str) -> tuple[str | None, str]:
    """Δημιουργεί ελληνική αφήγηση ΜΡ3 με το εγκατεστημένο edge-tts."""
    voice_name, friendly_name = resolve_greek_voice(voice_label)
    if voice_name is None:
        return None, friendly_name

    edge_tts = shutil.which("edge-tts")
    if not edge_tts:
        raise RuntimeError("Το edge-tts δεν βρέθηκε. Γράψε: pip install edge-tts")

    audio_path = OUTPUT_DIR / "elliniki-afhghsh.mp3"
    audio_path.unlink(missing_ok=True)

    command = [
        edge_tts,
        "--voice",
        voice_name,
        "--text",
        story,
        "--write-media",
        str(audio_path),
    ]
    run_process(command, title="ελληνικής αφήγησης", timeout=600)

    if not audio_path.exists() or audio_path.stat().st_size == 0:
        raise RuntimeError("Η ελληνική αφήγηση δεν δημιουργήθηκε σωστά.")

    return audio_path.name, friendly_name


def combine_video_and_narration(
    video_filename: str,
    narration_filename: str,
    using_own_photos: bool,
) -> str:
    """Ενώνει το βίντεο με την ελληνική αφήγηση."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("Το φφμεγκ δεν βρέθηκε στο Τέρμουξ.")

    video_path = OUTPUT_DIR / video_filename
    narration_path = OUTPUT_DIR / narration_filename
    output_name = (
        "dikes-mou-fotografies-me-elliniki-afhghsh.mp4"
        if using_own_photos
        else "vinteo-me-elliniki-afhghsh.mp4"
    )
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
        "voice": str(data.get("voice", "Ελληνικά")),
        "format": str(data.get("format", "Κάθετο")),
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
    source_images = uploaded_photo_paths if using_own_photos else default_image_paths()

    video_url = None
    video_error = None
    narration_added = False
    narration_error = None
    voice_used = "Χωρίς αφήγηση"

    try:
        silent_video_filename = create_preview_video(
            scenes,
            options["format"],
            source_images,
            using_own_photos,
        )
        final_video_filename = silent_video_filename

        if options["voice"] != "Χωρίς αφήγηση":
            try:
                narration_filename, voice_used = create_greek_narration(
                    story,
                    options["voice"],
                )
                if narration_filename:
                    final_video_filename = combine_video_and_narration(
                        silent_video_filename,
                        narration_filename,
                        using_own_photos,
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
            "using_own_photos": using_own_photos,
            "photo_count": len(source_images),
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
