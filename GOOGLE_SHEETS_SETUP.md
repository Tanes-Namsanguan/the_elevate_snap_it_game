# วิธีตั้งค่า Google Sheets History Log

ทุกครั้งที่ผู้เล่นจบเกม (ครบ 3 ภารกิจ หรือหมดเวลา) แอปจะยิง request ไป backend
(`POST /log-result`) แล้ว backend จะบันทึกผลลง Google Sheets 1 แถวแบบ fire-and-forget
(ไม่บล็อกเกม ถ้า Sheets ล่มหรือยังไม่ตั้งค่าไว้ เกมยังเล่นได้ปกติ — แค่ไม่มีการบันทึก log)

## 1) สร้าง Google Sheet ปลายทาง

1. สร้าง Google Sheet ใหม่ (หรือใช้ของเดิม) ตั้งชื่อชีทแรกว่า `Sheet1`
2. เพิ่มหัวคอลัมน์แถวแรก (ไม่บังคับ แต่แนะนำ เพื่อดูง่าย):
   `timestamp | device_id | image_correct | time_left_sec | time_left_display | total_score | reward`
3. copy **Spreadsheet ID** จาก URL (ส่วนระหว่าง `/d/` กับ `/edit`):
   `https://docs.google.com/spreadsheets/d/`**`<SPREADSHEET_ID>`**`/edit`

## 2) สร้าง Service Account + ขอ credentials

1. เข้า [Google Cloud Console](https://console.cloud.google.com/) → เลือก/สร้างโปรเจกต์
2. เปิดใช้งาน **Google Sheets API** (APIs & Services → Enable APIs → ค้นหา "Google Sheets API")
3. ไปที่ **IAM & Admin → Service Accounts → Create Service Account**
4. สร้างเสร็จแล้ว เปิด service account นั้น → แท็บ **Keys → Add Key → Create new key → JSON**
   จะได้ไฟล์ `.json` ดาวน์โหลดมา — **ห้าม commit ไฟล์นี้ลง repo เด็ดขาด**
5. เปิด Google Sheet ที่สร้างไว้ข้อ 1 → กด **Share** → แชร์ให้กับ `client_email`
   ที่อยู่ในไฟล์ JSON (สิทธิ์ **Editor**) ไม่งั้น API จะเขียนไม่ได้ (permission denied)

## 3) ตั้งค่า Environment Variables

**Local dev:** copy `.env.example` เป็น `.env` แล้วใส่ค่า (ต้องมี `python-dotenv` หรือ export
เองก่อนรัน — โปรเจกต์นี้ไม่ได้ auto-load `.env`)

**Render (production):** ไปที่ Render Dashboard → service ของเกม → **Environment** → เพิ่ม:

```
GOOGLE_SHEETS_CREDENTIALS={"type":"service_account","project_id":"...","private_key":"...","client_email":"...", ...}
GOOGLE_SHEETS_SPREADSHEET_ID=<SPREADSHEET_ID จากข้อ 1>
```

- `GOOGLE_SHEETS_CREDENTIALS` คือเนื้อหา **ทั้งไฟล์** JSON ของ service account key แบบวางเป็นสตริงบรรทัดเดียว
  (เปิดไฟล์ `.json` ที่ดาวน์โหลดมา copy ทั้งหมดวางได้เลย ไม่ต้องแก้ format)
- ถ้าไม่ได้ตั้งค่าตัวแปรทั้งสองนี้ ฟีเจอร์นี้จะปิดเงียบๆ (log warning ตอน start) ไม่กระทบการเล่นเกม

รันเสร็จลองเล่นเกมให้จบ 1 เกม แล้วเช็ค log ของแอป (หรือดูในชีทตรงๆ) ว่ามีแถวใหม่ถูกเพิ่มเข้ามา

## 4) โครงสร้างข้อมูลที่บันทึก (1 แถวต่อ 1 เกมที่จบ)

| คอลัมน์ | ตัวอย่าง | คำอธิบาย |
| --- | --- | --- |
| timestamp | `2026-01-15T14:32:07+07:00` | เวลาที่จบเกม (ISO 8601, timezone Asia/Bangkok) |
| device_id | `dev_a1b2c3d4e5` | แฮช SHA-256 (ตัด 10 ตัวแรก) ของ IP + User-Agent — ใช้แยก "อุปกรณ์" แบบไม่เก็บ IP ตรงๆ |
| image_correct | `2` | จำนวนภาพที่ถูก (1-3) |
| time_left_sec | `66` | เวลาที่เหลือ (วินาที) |
| time_left_display | `1:06` | เวลาที่เหลือ แบบ นาที:วินาที |
| total_score | `132` | คะแนนรวม (เวลาที่เหลือ × จำนวนภาพที่ถูก) |
| reward | `M` | ระดับรางวัล: `S` เล็ก / `M` กลาง / `L` ใหญ่ |
