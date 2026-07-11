# Oxlet Auto — เว็บไซต์โชว์รูม (Django)

Clone ฟังก์ชันจาก https://www.oxletauto.co.th/ — ดูพิมพ์เขียวที่ `../OXLET_WEBSITE_SPEC.md`

## รัน (dev / SQLite)
```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env          # DB_HOST เว้นว่าง = SQLite
python manage.py migrate
python manage.py seed_demo      # ข้อมูลตัวอย่าง (รถ/ยี่ห้อ/โปร/รีวิว)
python manage.py createsuperuser
python manage.py runserver
```
เปิด http://127.0.0.1:8000 · แอดมิน /admin/

## โครงสร้าง
```
config/      settings/urls/wsgi
cars/        models, views, urls, admin, constants, seed_demo
templates/   base + หน้าเว็บทั้งหมด
static/      โลโก้แบรนด์ / รูป (ดึงจาก oxlet_images)
```

## หน้าเว็บ
`/` หน้าแรก · `/all-cars/` ค้นหา+ฟิลเตอร์ · `/listings/<slug>/` รายละเอียดรถ ·
`/compare/` เปรียบเทียบ · `/brand/` · `/car-type/` · `/promotion/` · `/reviews/` ·
`/about/` · `/faq/` · `/contact/` · `/admin/`

## เฟสถัดไป
- ใส่รูปรถจริง (admin → Vehicle → upload) / ย้ายโลโก้แบรนด์เข้า static
- เครื่องคิดค่างวด (ดาวน์/ระยะผ่อน/ดอกเบี้ย)
- ฟอร์ม Lead → push เข้า LINE กลุ่มเซล (`cars/line.py`)
- เชื่อมสต็อกเรียลไทม์กับระบบ tracking (รถ stage=show ขึ้นเว็บ)
