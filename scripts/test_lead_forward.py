# -*- coding: utf-8 -*-
"""ตรวจฟอร์ม "ขอราคาพิเศษ / นัดดูรถ" → ส่งต่อเข้าห้องพัก Lead ของ SaleForce (ต.ค.69)

    python scripts/test_lead_forward.py

SQLite ชั่วคราว + test client จริง · ปลอมแค่ SaleForce ที่ขอบระบบ (urllib.request.urlopen) · ตรวจว่า:
  - กรอกฟอร์มแล้วลีดยังเก็บในเว็บนี้เหมือนเดิม + ส่ง JSON ไป SaleForce พร้อมรหัสลับ/ข้อมูลรถ
  - ส่งสำเร็จ = จดเวลา · SaleForce ตอบว่าโพสต์ LINE ไม่สำเร็จ = จดเหตุผล · ต่อไม่ได้ = จดเหตุผล (เห็นในหน้า admin)
  - ไม่ได้ตั้ง SALEFORCE_LEAD_URL = ไม่ส่งอะไรออก · ลูกค้าเห็นข้อความ "ขอราคาเรียบร้อย" ทุกกรณี
"""
import io
import json
import os
import sys
import urllib.error

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["DB_HOST"] = ""
os.environ["R2_BUCKET"] = ""
os.environ["DEBUG"] = "True"

import django

django.setup()

from django.conf import settings
from django.test.runner import DiscoverRunner
from django.test.utils import setup_test_environment

setup_test_environment()
runner = DiscoverRunner(verbosity=0, interactive=False)
old_cfg = runner.setup_databases()
settings.ALLOWED_HOSTS = ["*"]

import urllib.request

from django.test import Client

from cars import views
from cars.models import Brand, Lead, Vehicle

views.FORWARD_BG = False
fail = []


def eq(got, want, what):
    if got == want:
        print("  ok   %s" % what)
    else:
        fail.append(what)
        print("  FAIL %s → ได้ %r ควรได้ %r" % (what, got, want))


CALLS = []
MODE = {"reply": {"ok": True, "pushed": True}, "raise": None}


class _Resp:
    def __init__(self, body):
        self._b = json.dumps(body).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(req, timeout=None):
    CALLS.append({"url": req.full_url, "headers": dict(req.header_items()), "body": json.loads(req.data.decode())})
    if MODE["raise"]:
        raise MODE["raise"]
    return _Resp(MODE["reply"])


urllib.request.urlopen = fake_urlopen
c = Client()
b = Brand.objects.get_or_create(name="Toyota")[0]
car = Vehicle.objects.create(brand=b, model="Hilux Revo", year=2018, price=429000, plate="5กน1573",
                             status="available", stock_code="CS03560")


from django.urls import reverse
LEAD_URL = reverse("lead_submit")


def submit(name="สมชาย", phone="0812345678"):
    return c.post(LEAD_URL, {"name": name, "phone": phone, "email": "a@b.co", "vehicle": car.slug,
                             "source_page": "car_detail"}, HTTP_REFERER=car.get_absolute_url(), follow=True)


print("[1] ยังไม่ตั้งค่า = ไม่ส่งออก")
settings.SALEFORCE_LEAD_URL = ""
settings.STOCK_SYNC_SECRET = "s3cret"
r = submit()
eq(Lead.objects.count(), 1, "เก็บลีดในเว็บนี้")
eq(len(CALLS), 0, "ไม่ยิงออกไปไหน")
eq("ขอราคาเรียบร้อย" in r.content.decode(), True, "ลูกค้าเห็นข้อความสำเร็จ")

print("[2] ตั้งค่าแล้ว — ส่งสำเร็จ")
settings.SALEFORCE_LEAD_URL = "https://saleforce.example/api/showroom/lead"
r = submit(name="สมหญิง", phone="0899999999")
lead = Lead.objects.order_by("-id").first()
eq(len(CALLS), 1, "ยิงไป SaleForce 1 ครั้ง")
call = CALLS[-1]
eq(call["url"], "https://saleforce.example/api/showroom/lead", "ไป URL ที่ตั้ง")
eq(call["headers"].get("X-stock-secret"), "s3cret", "แนบรหัสลับ")
body = call["body"]
eq((body["lead_id"], body["name"], body["phone"]), (lead.pk, "สมหญิง", "0899999999"), "ข้อมูลลูกค้า")
eq((body["car"]["code"], body["car"]["plate"], body["car"]["price"]), ("CS03560", "5กน1573", 429000), "ข้อมูลรถ")
eq(body["car"]["url"], "http://testserver" + car.get_absolute_url(), "ลิงก์หน้ารถ")
lead.refresh_from_db()
eq((lead.forwarded_at is not None, lead.forward_error), (True, ""), "จดว่าส่งแล้ว")

print("[3] SaleForce รับแล้วแต่โพสต์ LINE ไม่สำเร็จ")
MODE["reply"] = {"ok": True, "pushed": False, "error": "LINE ไม่รับ (400)"}
submit(name="ก", phone="0811111111")
lead = Lead.objects.order_by("-id").first()
eq(lead.forwarded_at is not None, True, "นับว่าเข้าห้องพัก Lead แล้ว")
eq("โพสต์ LINE ไม่สำเร็จ" in lead.forward_error, True, "จดเหตุผล")

print("[4] ต่อ SaleForce ไม่ได้ / SaleForce ปฏิเสธ")
MODE["reply"] = {"ok": True, "pushed": True}
MODE["raise"] = OSError("connection refused")
r = submit(name="ข", phone="0822222222")
lead = Lead.objects.order_by("-id").first()
eq((lead.forwarded_at, "ต่อ SaleForce ไม่ได้" in lead.forward_error), (None, True), "จดว่าส่งไม่ถึง")
eq("ขอราคาเรียบร้อย" in r.content.decode(), True, "หน้าเว็บไม่พัง")
err_body = io.BytesIO(json.dumps({"ok": False, "error": "unauthorized"}).encode())
MODE["raise"] = urllib.error.HTTPError("u", 401, "Unauthorized", {}, err_body)
submit(name="ค", phone="0833333333")
lead = Lead.objects.order_by("-id").first()
eq((lead.forwarded_at, lead.forward_error), (None, "unauthorized"), "จดคำตอบของ SaleForce")
MODE["raise"] = None

runner.teardown_databases(old_cfg)
print()
print("ผ่านทั้งหมด" if not fail else "ไม่ผ่าน %d ข้อ: %s" % (len(fail), ", ".join(fail)))
sys.exit(1 if fail else 0)
