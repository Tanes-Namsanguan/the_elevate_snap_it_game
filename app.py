import os
import json
import base64
from google import genai
from google.genai import types
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
MODEL = "gemini-2.0-flash-lite"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        data = request.get_json()
        image_b64 = data.get("image_base64", "")
        challenge_en = data.get("challenge_en", "")
        challenge_th = data.get("challenge_th", "")

        if not image_b64 or not challenge_en:
            return jsonify({"error": "Missing image or challenge"}), 400

        prompt = f"""You are a game judge for a photo challenge game called "The Elevate".
The player was asked to photograph: {challenge_en}
Look at the image carefully and decide if it contains a {challenge_en}.
Respond ONLY with a JSON object, no markdown, no extra text:
{{
  "correct": true or false,
  "found": "what you see in the image (1 short sentence in Thai)",
  "feedback": "fun encouraging message in Thai, 1-2 sentences, casual tone, use emoji"
}}
Be fair — if the photo is close enough or partially matches, consider it correct."""

        image_bytes = base64.b64decode(image_b64)

        response = client.models.generate_content(
            model=MODEL,
            contents=[
                types.Part.from_text(text=prompt),
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
            ],
        )

        text = response.text.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        result = json.loads(text)
        return jsonify(result)

    except json.JSONDecodeError:
        return jsonify({
            "correct": False,
            "found": "ไม่สามารถอ่านผลลัพธ์ได้",
            "feedback": "เกิดข้อผิดพลาด ลองใหม่อีกครั้งนะ 🙏"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
