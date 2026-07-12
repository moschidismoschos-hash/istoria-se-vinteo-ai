from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)


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

    # Περίπου 5 ή περισσότερες λέξεις ανά σκηνή.
    possible_scenes = max(1, word_count // 5)
    return max(1, min(requested_scenes, possible_scenes))


def split_story_balanced(story: str, scene_count: int) -> list[str]:
    """Χωρίζει όλη την ιστορία σε ισορροπημένα τμήματα ίσου περίπου μήκους."""
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
    """Δημιουργεί περιγραφή που αργότερα θα σταλεί στη μηχανή εικόνας/βίντεο."""
    format_hint = {
        "Κάθετο": "κάθετο κάδρο 9:16",
        "Οριζόντιο": "οριζόντιο κάδρο 16:9",
        "Τετράγωνο": "τετράγωνο κάδρο 1:1",
    }.get(video_format, "κάθετο κάδρο 9:16")

    return (
        f"{style} κινηματογραφική σκηνή, {format_hint}, φυσικός φωτισμός, "
        f"σταθεροί χαρακτήρες, ίδια πρόσωπα και ίδια ρούχα σε όλες τις σκηνές, "
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


@app.get("/")
def home():
    return render_template("index.html")


@app.post("/api/dimiourgia")
def dimiourgia():
    data = request.get_json(silent=True) or {}
    story = clean_text(str(data.get("story", "")))

    if not story:
        return jsonify({"ok": False, "message": "Γράψε πρώτα την ιστορία σου."}), 400

    if len(story) > 2000:
        return jsonify({"ok": False, "message": "Η ιστορία ξεπερνά τους 2.000 χαρακτήρες."}), 400

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
        return jsonify({"ok": False, "message": "Δεν μπόρεσαν να δημιουργηθούν σκηνές."}), 400

    return jsonify(
        {
            "ok": True,
            "message": f"Η ιστορία χωρίστηκε σε {len(scenes)} σκηνές.",
            "story": story,
            "options": options,
            "scene_count": len(scenes),
            "scenes": [asdict(scene) for scene in scenes],
            "preview_images": [
                "/static/images/scene-1.png",
                "/static/images/scene-2.png",
                "/static/images/scene-3.png",
            ],
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
