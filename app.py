import os
import json
import base64
import logging
from google import genai
from google.genai import types
from flask import Flask, request, jsonify, render_template

# ── LOGGING SETUP ─────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ── GEMINI CLIENT SETUP ───────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL = "gemini-3.5-flash-lite"

if not GEMINI_API_KEY:
    logger.error("❌ GEMINI_API_KEY is not set! Please add it to environment variables.")
else:
    logger.info(f"✅ GEMINI_API_KEY loaded (starts with: {GEMINI_API_KEY[:8]}...)")

try:
    client = genai.Client(api_key=GEMINI_API_KEY)
    logger.info(f"✅ Gemini client initialized — model: {MODEL}")
except Exception as e:
    logger.error(f"❌ Failed to initialize Gemini client: {e}")
    client = None


# ── ROUTES ────────────────────────────────────────────────
@app.route("/")
def index():
    logger.info("📄 GET / — serving index.html")
    return render_template("index.html")


@app.route("/health")
def health():
    status = {
        "status": "ok",
        "gemini_key_set": bool(GEMINI_API_KEY),
        "gemini_client_ready": client is not None,
        "model": MODEL,
    }
    logger.info(f"🏥 Health check: {status}")
    return jsonify(status)


@app.route("/analyze", methods=["POST"])
def analyze():
    logger.info("📸 POST /analyze — received request")
    try:
        if client is None:
            logger.error("❌ Gemini client not initialized")
            return jsonify({"error": "Gemini client not initialized — check GEMINI_API_KEY"}), 500

        data = request.get_json()
        if not data:
            logger.warning("⚠️ No JSON body received")
            return jsonify({"error": "No JSON body"}), 400

        image_b64 = data.get("image_base64", "")
        challenge_en = data.get("challenge_en", "")
        challenge_th = data.get("challenge_th", "")

        logger.info(f"🎯 Challenge: '{challenge_th}' ({challenge_en})")
        logger.info(f"🖼️  Image size: {len(image_b64)} chars (base64)")

        if not image_b64 or not challenge_en:
            logger.warning("⚠️ Missing image or challenge")
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
        logger.info(f"🔄 Sending to Gemini ({len(image_bytes)} bytes)...")

        response = client.models.generate_content(
            model=MODEL,
            contents=[
                types.Part.from_text(text=prompt),
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
            ],
        )

        text = response.text.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        logger.info(f"📨 Gemini raw response: {text[:200]}")

        result = json.loads(text)
        logger.info(f"✅ Result: correct={result.get('correct')} | found={result.get('found', '')[:50]}")
        return jsonify(result)

    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON parse error: {e} | raw text: {text[:200] if 'text' in locals() else 'N/A'}")
        return jsonify({
            "correct": False,
            "found": "ไม่สามารถอ่านผลลัพธ์ได้",
            "feedback": "เกิดข้อผิดพลาด ลองใหม่อีกครั้งนะ 🙏"
        })
    except Exception as e:
        logger.error(f"❌ Unexpected error in /analyze: {type(e).__name__}: {e}")
        return jsonify({"error": f"{type(e).__name__}: {str(e)}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🚀 Starting server on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
