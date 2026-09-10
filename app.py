import os
import io
import json
import base64
import random
import logging
import httpx
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

import sheets_logger  # noqa: E402 (ต้อง import หลัง logging.basicConfig เพื่อให้ log ตอน init ใช้ format เดียวกัน)

app = Flask(__name__)

# ── QR CODE SETUP ─────────────────────────────────────────
GAME_URL = os.environ.get("GAME_URL", "https://the-elevate-snap-it-game.onrender.com/")

# ── GEMINI CLIENT SETUP (multi API-key rotation) ──────────
# ตั้งค่าได้ 2 แบบ (ใช้แบบไหนก็ได้):
#   1) GEMINI_API_KEYS = "key1,key2,key3"   (คั่นด้วยจุลภาค แนะนำ)
#   2) GEMINI_API_KEY_1 / GEMINI_API_KEY_2 / GEMINI_API_KEY_3 (แยกตัวแปร)
# ยังรองรับ GEMINI_API_KEY ตัวเดียวแบบเดิมด้วย (backward compatible)
MODEL = "gemini-flash-lite-latest"  # alias ของ Google เอง ชี้ไปที่โมเดล lite รุ่นล่าสุดเสมอ
# กันปัญหาที่เจอมาแล้ว: ระบุชื่อรุ่นตรงๆ (เช่น "gemini-2.0-flash-lite") พอ Google เลิก
# ซัพพอร์ตรุ่นนั้น (404 "no longer available") แอปก็พังทันทีจนกว่าจะมาแก้โค้ด/deploy ใหม่

# กันไม่ให้ 1 request ที่ Gemini ตอบช้า/ค้าง ไปฉุด gunicorn worker จน hit WORKER TIMEOUT
# (ค่า default ของ gunicorn คือ 30s — ถ้า Gemini ค้างนานกว่านั้น worker ทั้งตัวจะโดน
# SIGKILL กลางคัน ทำให้ request อื่นๆ ที่รออยู่ในคิวพังไปด้วย) แทนที่จะรอจนถูกฆ่า
# เราตัดจบเองก่อนที่ระดับ HTTP client แล้วลองคีย์ถัดไปแทน
GEMINI_REQUEST_TIMEOUT_MS = 25_000  # 25 วินาทีต่อ 1 คีย์ (Gemini เองบางครั้งตอบช้าจริงๆ
# ระดับ 10-15 วิ ก่อนจะสำเร็จ — ตั้งสั้นไปจะไปตัดจบ request ที่กำลังจะสำเร็จอยู่ดีๆ)
# ถ้าเปลี่ยนค่านี้ ให้ปรับ gunicorn --timeout ให้เผื่อไว้มากกว่า (จำนวนคีย์ทั้งหมด × ค่านี้)
# ด้วย ดู GEMINI_API_SETUP.md

def _split_keys(raw):
    """แยกค่าด้วยจุลภาคเสมอ เผื่อมีคนใส่หลายคีย์รวมกันในตัวแปรเดียว ไม่ว่าจะตั้งชื่อ
    ตัวแปรว่าอะไรก็ตาม (GEMINI_API_KEY หรือ GEMINI_API_KEYS)"""
    return [k.strip() for k in (raw or "").split(",") if k.strip()]


def _load_api_keys():
    keys = []

    keys.extend(_split_keys(os.environ.get("GEMINI_API_KEYS")))

    for i in range(1, 10):  # GEMINI_API_KEY_1 .. GEMINI_API_KEY_9
        keys.extend(_split_keys(os.environ.get(f"GEMINI_API_KEY_{i}")))

    keys.extend(_split_keys(os.environ.get("GEMINI_API_KEY")))

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
    """สุ่มลำดับ client (API key) แล้วลองยิงไปเรื่อยๆ จนกว่าจะสำเร็จหรือหมดทุกคีย์ —
    ไม่ว่าจะโดน rate-limit/quota เต็ม (429), Gemini ล้ม (503/504), คีย์เสีย/ไม่มีสิทธิ์
    (400/401/403 ฯลฯ), หรือค้าง/ตอบช้าเกิน GEMINI_REQUEST_TIMEOUT_MS ก็ข้ามไปลองคีย์ถัดไป
    ทันที (เดิมจะ raise ทันทีถ้า error code ไม่ใช่ 429/503 ทำให้คีย์ที่เสีย/ผิดสิทธิ์ 1 ตัว
    พังทั้ง request แม้คีย์อื่นจะใช้ได้ปกติก็ตาม) วิธีนี้กระจายโหลดข้าม process ของ gunicorn
    ได้โดยไม่ต้องมี shared state (เช่น Redis) และไม่มี downtime ถ้าคีย์ใดคีย์หนึ่งใช้ไม่ได้"""
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
                config=types.GenerateContentConfig(
                    http_options=types.HttpOptions(timeout=GEMINI_REQUEST_TIMEOUT_MS),
                ),
            )
            logger.info(f"🔑 Used Gemini API key #{i + 1}/{len(clients)}")
            return response
        except genai_errors.APIError as e:
            last_err = e
            logger.warning(f"⚠️ Key #{i + 1} failed ({e.code}: {getattr(e, 'message', e)}), trying next key...")
            continue
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            last_err = e
            logger.warning(f"⚠️ Key #{i + 1} timed out/unreachable ({e}), trying next key...")
            continue

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


@app.route("/log-result", methods=["POST"])
def log_result():
    """บันทึกผลการเล่น 1 เกม (จบครบ 3 ภารกิจ หรือหมดเวลา) ลง Google Sheets เพื่อดูประวัติ
    เป็นแค่ analytics เสริม ไม่ใช่ core flow ของเกม — ยิงแบบ fire-and-forget เสมอ
    (คิวงานเข้า thread แยกใน sheets_logger) เพื่อไม่บล็อก response และไม่ทำให้เกมพังถ้า
    Google Sheets ล่มหรือยังไม่ได้ตั้งค่า credentials"""
    try:
        data = request.get_json() or {}
        image_correct = int(data.get("image_correct", 0))
        time_left_sec = int(data.get("time_left_sec", 0))
        total_score = int(data.get("total_score", 0))
        reward = str(data.get("reward", ""))[:1].upper()

        # อยู่หลัง proxy ของ Render — IP จริงของผู้เล่นมาจาก X-Forwarded-For ไม่ใช่ request.remote_addr
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
        user_agent = request.headers.get("User-Agent", "")

        sheets_logger.log_game_result(image_correct, time_left_sec, total_score, reward, ip, user_agent)
    except Exception as e:
        # ไม่ให้ endpoint นี้ทำให้อะไรพัง — log ไว้เฉยๆ พอ
        logger.error(f"❌ Failed to queue /log-result: {e}")

    return jsonify({"status": "queued"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🚀 Starting server on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
