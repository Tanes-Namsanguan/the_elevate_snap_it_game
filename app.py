import os
import io
import json
import base64
import random
import logging
import qrcode
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from flask import Flask, request, jsonify, render_template, send_file

# ── LOGGING SETUP ─────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ── QR CODE SETUP ─────────────────────────────────────────
GAME_URL = os.environ.get("GAME_URL", "https://the-elevate-snap-it-game.onrender.com/")

# ── GEMINI CLIENT SETUP (multi API-key rotation) ──────────
# ตั้งค่าได้ 2 แบบ (ใช้แบบไหนก็ได้):
#   1) GEMINI_API_KEYS = "key1,key2,key3"   (คั่นด้วยจุลภาค แนะนำ)
#   2) GEMINI_API_KEY_1 / GEMINI_API_KEY_2 / GEMINI_API_KEY_3 (แยกตัวแปร)
# ยังรองรับ GEMINI_API_KEY ตัวเดียวแบบเดิมด้วย (backward compatible)
MODEL = "gemini-3.5-flash-lite"


def _load_api_keys():
    keys = []

    multi = os.environ.get("GEMINI_API_KEYS", "")
    keys.extend([k.strip() for k in multi.split(",") if k.strip()])

    for i in range(1, 10):  # GEMINI_API_KEY_1 .. GEMINI_API_KEY_9
        k = os.environ.get(f"GEMINI_API_KEY_{i}")
        if k and k.strip():
            keys.append(k.strip())

    single = os.environ.get("GEMINI_API_KEY")
    if single and single.strip():
        keys.append(single.strip())

    # ตัดตัวซ้ำ แต่คงลำดับเดิมไว้
    seen = set()
    unique_keys = []
    for k in keys:
        if k not in seen:
            seen.add(k)
            unique_keys.append(k)
    return unique_keys


GEMINI_API_KEYS = _load_api_keys()

if not GEMINI_API_KEYS:
    logger.error("❌ No Gemini API key found! Set GEMINI_API_KEYS (comma-separated) or GEMINI_API_KEY.")

clients = []
for idx, key in enumerate(GEMINI_API_KEYS, start=1):
    try:
        clients.append(genai.Client(api_key=key))
        logger.info(f"✅ Gemini client #{idx} initialized (key starts with: {key[:8]}...)")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Gemini client #{idx}: {e}")

logger.info(f"🔑 {len(clients)} Gemini API key(s) loaded — requests will be spread across them, model: {MODEL}")


# ── ROUTES ────────────────────────────────────────────────
@app.route("/")
def index():
    logger.info("📄 GET / — serving index.html")
    return render_template("index.html")


@app.route("/health")
def health():
    status = {
        "status": "ok",
        "gemini_keys_configured": len(GEMINI_API_KEYS),
        "gemini_clients_ready": len(clients),
        "model": MODEL,
    }
    logger.info(f"🏥 Health check: {status}")
    return jsonify(status)


@app.route("/qrcode")
def qrcode_image():
    """Return a PNG QR code that links to the game (or ?url=... to encode a custom link)."""
    target_url = request.args.get("url", GAME_URL)
    logger.info(f"🔗 GET /qrcode — generating QR code for: {target_url}")

    qr = qrcode.QRCode(
        version=None,  # auto-size based on data
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(target_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png", download_name="the-elevate-qr.png")


def _generate_with_failover(prompt, image_bytes):
    """สุ่มลำดับ client (API key) แล้วลองยิงไปเรื่อยๆ — ถ้าคีย์ไหนโดน rate-limit/quota
    เต็ม (429) หรือ Gemini ล้ม (503) ก็ข้ามไปลองคีย์ถัดไปให้อัตโนมัติ วิธีนี้กระจาย
    โหลดข้าม process ของ gunicorn ได้โดยไม่ต้องมี shared state (เช่น Redis) และไม่มี
    downtime ถ้าคีย์ใดคีย์หนึ่งใช้โควต้าฟรีหมดในระหว่างวัน"""
    order = list(range(len(clients)))
    random.shuffle(order)

    last_err = None
    for i in order:
        try:
            response = clients[i].models.generate_content(
                model=MODEL,
                contents=[
                    types.Part.from_text(text=prompt),
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                ],
            )
            logger.info(f"🔑 Used Gemini API key #{i + 1}/{len(clients)}")
            return response
        except genai_errors.APIError as e:
            last_err = e
            if e.code in (429, 503):  # quota exceeded / overloaded — try next key
                logger.warning(f"⚠️ Key #{i + 1} failed ({e.code}), trying next key...")
                continue
            raise  # other API errors (bad request, auth, etc.) — don't retry

    raise last_err if last_err else RuntimeError("No Gemini API keys available")


@app.route("/analyze", methods=["POST"])
def analyze():
    logger.info("📸 POST /analyze — received request")
    try:
        if not clients:
            logger.error("❌ No Gemini client initialized")
            return jsonify({"error": "Gemini client not initialized — check GEMINI_API_KEY(S)"}), 500

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

        response = _generate_with_failover(prompt, image_bytes)

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
