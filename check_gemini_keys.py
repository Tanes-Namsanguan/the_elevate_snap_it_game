"""
check_gemini_keys.py — ทดสอบ Gemini API key ทุกตัวที่ตั้งไว้ใน environment variables
ว่าใช้งานได้จริงหรือไม่ (ยิง request จริงแบบสั้นๆ ไปที่ Gemini ทีละคีย์)

วิธีรัน:
  - Local:  ตั้ง env var ก่อนแล้วรัน `python check_gemini_keys.py`
  - Render: เปิด Shell ของ service (Dashboard > service > Shell) แล้วรัน
            `python check_gemini_keys.py` ตรงนั้นเลย (จะได้ env var จริงที่ deploy ใช้อยู่)

อ่าน env var แบบเดียวกับ app.py ทุกประการ (GEMINI_API_KEYS / GEMINI_API_KEY_1..9 /
GEMINI_API_KEY แบบคั่นด้วยจุลภาค) เพื่อให้ผลตรงกับที่แอปจริงใช้งาน
"""
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # กัน UnicodeEncodeError บน Windows console (cp874/cp1252)

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

# ใช้ loader ตัวเดียวกับ app.py เป๊ะๆ เพื่อไม่ให้ผลการทดสอบเพี้ยนไปจากของจริง
from app import _load_api_keys, MODEL


def _mask(key):
    return f"{key[:8]}...{key[-4:]}" if len(key) > 12 else f"{key[:4]}..."


def main():
    keys = _load_api_keys()
    if not keys:
        print("❌ ไม่พบ Gemini API key เลย — เช็ค GEMINI_API_KEYS / GEMINI_API_KEY_1..9 / GEMINI_API_KEY")
        sys.exit(1)

    print(f"พบ {len(keys)} คีย์ — กำลังทดสอบทีละตัวด้วย model={MODEL}\n")

    ok_count = 0
    for idx, key in enumerate(keys, start=1):
        masked = _mask(key)
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model=MODEL,
                contents=[types.Part.from_text(text="Reply with exactly one word: OK")],
                config=types.GenerateContentConfig(http_options=types.HttpOptions(timeout=15_000)),
            )
            text = (response.text or "").strip()
            print(f"✅ Key #{idx} ({masked}) — ใช้ได้ | response: {text[:50]!r}")
            ok_count += 1
        except genai_errors.APIError as e:
            print(f"❌ Key #{idx} ({masked}) — FAILED | code={e.code} message={getattr(e, 'message', e)}")
        except Exception as e:
            print(f"❌ Key #{idx} ({masked}) — FAILED | {type(e).__name__}: {e}")

    print(f"\nสรุป: ใช้ได้ {ok_count}/{len(keys)} คีย์")


if __name__ == "__main__":
    main()
