"""
sheets_logger.py — บันทึกประวัติผลการเล่นแต่ละเกมลง Google Sheets

ตั้งค่าผ่าน environment variable 2 ตัว (ดู README.md):
  GOOGLE_SHEETS_CREDENTIALS     JSON string ของ service account key (ห้ามเก็บไฟล์ไว้ใน repo)
  GOOGLE_SHEETS_SPREADSHEET_ID  ID ของ spreadsheet ปลายทาง

ถ้าไม่ได้ตั้งค่าไว้ ฟีเจอร์นี้จะถูกปิดเงียบๆ (log warning ครั้งเดียวตอน start)
โดยไม่กระทบการทำงานส่วนอื่นของแอป — เพราะ history log เป็นแค่ analytics เสริม
ไม่ใช่ core flow ของเกม
"""
import os
import json
import hashlib
import logging
import threading
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

SPREADSHEET_ID = os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID")
SHEET_RANGE = "Sheet1!A:G"
BANGKOK_TZ = timezone(timedelta(hours=7))

def _build_service():
    """สร้าง Google Sheets API client จาก service account credentials (lazy, ครั้งเดียว)."""
    raw_creds = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
    if not raw_creds or not SPREADSHEET_ID:
        logger.warning(
            "⚠️ Google Sheets logging disabled — set GOOGLE_SHEETS_CREDENTIALS and "
            "GOOGLE_SHEETS_SPREADSHEET_ID to enable history log."
        )
        return None

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        info = json.loads(raw_creds)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        logger.info("✅ Google Sheets client initialized")
        return service
    except Exception as e:
        logger.error(f"❌ Failed to initialize Google Sheets client: {e}")
        return None


# สร้าง client ตอน import โมดูล (ครั้งเดียว) เหมือน pattern ของ Gemini clients ใน app.py
_service = _build_service()


def _get_service():
    return _service


def _make_device_id(ip, user_agent):
    """แฮช ip + user_agent ด้วย SHA-256 แล้วตัด 10 ตัวอักษรแรก เพื่อระบุ "อุปกรณ์" แบบไม่เก็บ PII ตรงๆ"""
    digest = hashlib.sha256(f"{ip}{user_agent}".encode("utf-8")).hexdigest()
    return f"dev_{digest[:10]}"


def _format_time_left(time_left_sec):
    """66 -> "1:06" """
    minutes, seconds = divmod(int(time_left_sec), 60)
    return f"{minutes}:{seconds:02d}"


def _append_row(image_correct, time_left_sec, total_score, reward, ip, user_agent):
    service = _get_service()
    if not service:
        return

    device_id = _make_device_id(ip, user_agent)
    time_left_display = _format_time_left(time_left_sec)
    ts = datetime.now(BANGKOK_TZ).isoformat()

    row = [ts, device_id, image_correct, time_left_sec, time_left_display, total_score, reward]

    try:
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=SHEET_RANGE,
            valueInputOption="USER_ENTERED",
            body={"values": [row]},
        ).execute()
        logger.info(f"📊 Logged game result to Google Sheets: {row}")
    except Exception as e:
        # เขียน sheet ไม่สำเร็จ (quota, network, permission ฯลฯ) — log ไว้เฉยๆ ไม่ให้กระทบ flow หลัก
        logger.error(f"❌ Failed to append row to Google Sheets: {e}")


def log_game_result(image_correct, time_left_sec, total_score, reward, ip, user_agent):
    """บันทึกผลการเล่น 1 เกมลง Google Sheets แบบไม่บล็อก request

    image_correct: จำนวนภาพที่ถูก (1-3)
    time_left_sec:  เวลาที่เหลือ (วินาที)
    total_score:    คะแนนรวม (0-300)
    reward:         "S" | "M" | "L"
    ip / user_agent: ใช้สร้าง device_id เท่านั้น ไม่ถูกบันทึกลง sheet ตรงๆ
    """
    threading.Thread(
        target=_append_row,
        args=(image_correct, time_left_sec, total_score, reward, ip, user_agent),
        daemon=True,
    ).start()
