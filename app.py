from __future__ import annotations

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)


@app.get("/")
def home():
    return render_template("index.html")


@app.post("/api/dimiourgia")
def dimiourgia():
    data = request.get_json(silent=True) or {}
    story = str(data.get("story", "")).strip()

    if not story:
        return jsonify({"ok": False, "message": "Γράψε πρώτα την ιστορία σου."}), 400

    options = {
        "style": str(data.get("style", "Ρεαλιστικό")),
        "duration": str(data.get("duration", "1 λεπτό")),
        "voice": str(data.get("voice", "Ελληνικά")),
        "format": str(data.get("format", "Κάθετο")),
    }

    # Πρώτη λειτουργική έκδοση: δέχεται την ιστορία και τις επιλογές.
    # Η πραγματική σύνδεση με υπηρεσία δημιουργίας βίντεο θα προστεθεί
    # στο επόμενο στάδιο χωρίς να αλλάξει η εμφάνιση της εφαρμογής.
    return jsonify(
        {
            "ok": True,
            "message": "Η ιστορία καταχωρίστηκε σωστά.",
            "story": story,
            "options": options,
            "scenes": [
                "/static/images/scene-1.png",
                "/static/images/scene-2.png",
                "/static/images/scene-3.png",
            ],
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
