# -*- coding: utf-8 -*-
"""ตรวจปุ่ม Active (ต.ค.69) ฝั่งเว็บโชว์รูม — webhook /api/stock-update/ + การซ่อนรถจากลูกค้า

    python scripts/test_stock_active.py

ใช้ฐานข้อมูลทดสอบ (SQLite ชั่วคราว) + Django test client จริง · ไม่ยิงเน็ต (ไม่ส่งรูป) · ตรวจว่า:
  - ไม่มี secret = 401
  - backend รุ่นเก่า (ไม่ส่ง active) = พฤติกรรมเดิม (สร้างประกาศ โชว์ทันที)
  - active=false = ไม่สร้าง · มีประกาศอยู่ = ซ่อน (ไม่ลบ ราคาที่เติมไว้ยังอยู่)
  - active=true + สเตปยังไม่ถึงพร้อมขาย = รอ (ไม่สร้าง) · มีประกาศที่ซ่อนอยู่ = เปิดคืน
  - รถที่ซ่อน: ลูกค้าไม่เห็นทุกทาง (ค้นหา/หน้ารถ/เปรียบเทียบ/จอง/แชทบอท/ลิงก์ /stock/) · staff ยังเปิดดูได้
  - รถที่ staff เพิ่มเองในเว็บไม่โดนอะไร
"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["DB_HOST"] = ""      # SQLite ชั่วคราวเสมอ — ห้ามแตะฐานข้อมูลจริง
os.environ["R2_BUCKET"] = ""
os.environ["DEBUG"] = "True"

import django

django.setup()

from django.conf import settings
from django.test.utils import setup_test_environment
from django.test.runner import DiscoverRunner

setup_test_environment()
runner = DiscoverRunner(verbosity=0, interactive=False)
old_cfg = runner.setup_databases()
settings.ALLOWED_HOSTS = ["*"]

from django.contrib.auth.models import User
from django.test import Client

from cars import ai, views
from cars.models import Brand, Vehicle

views.SYNC_PHOTOS_BG = False
SECRET = "test-secret"
settings.STOCK_SYNC_SECRET = SECRET

fail = []


def eq(got, want, what):
    if got == want:
        print("  ok   %s" % what)
    else:
        fail.append(what)
        print("  FAIL %s → ได้ %r ควรได้ %r" % (what, got, want))


anon = Client()
staff = Client()
_u = User.objects.create_user("staff", password="x", is_staff=True)
staff.force_login(_u)


def hook(payload, secret=SECRET):
    h = {"HTTP_X_STOCK_SECRET": secret} if secret else {}
    r = anon.post("/api/stock-update/", data=json.dumps(payload), content_type="application/json", **h)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {}


def base(code, stage="show", **kw):
    d = {"code": code, "stage": stage, "status": "active", "brand": "Toyota", "model": "Yaris",
         "year": 2022, "color": "ขาว", "km": 30000, "plate": "1กก1234", "photos": []}
    d.update(kw)
    return d


def public_codes():
    return set(views._available().exclude(stock_code="").values_list("stock_code", flat=True))


print("[1] ไม่มี secret / secret ผิด")
eq(hook(base("CB-0001"), secret="")[0], 401, "ไม่มี secret = 401")
eq(hook(base("CB-0001"), secret="ผิด")[0], 401, "secret ผิด = 401")
eq(Vehicle.objects.filter(stock_code="CB-0001").exists(), False, "ไม่สร้างอะไรเลย")

print("[2] backend รุ่นเก่า (ไม่ส่ง active) = พฤติกรรมเดิม")
st, j = hook(base("CB-0001"))
eq((st, j.get("created"), j.get("listed")), (200, True, True), "สร้างประกาศ + โชว์ทันที")
eq(bool(j.get("path")), True, "คืน path หน้ารถ")
eq("CB-0001" in public_codes(), True, "ลูกค้าเห็นในหน้าค้นหา")

print("[3] ยังไม่ Active → ไม่สร้างประกาศ")
st, j = hook(base("CB-0002", active=False))
eq((st, j.get("action"), j.get("listed"), j.get("created")), (200, "inactive", False, False), "ตอบว่า inactive")
eq(Vehicle.objects.filter(stock_code="CB-0002").exists(), False, "ไม่มีประกาศเกิดขึ้น")
st, j = hook(base("CB-0002", active="false"))
eq(Vehicle.objects.filter(stock_code="CB-0002").exists(), False, "active เป็นข้อความ 'false' ก็ไม่สร้าง")

print("[4] กด Active ตอนรถยังไม่ถึงพร้อมขาย → รอ")
st, j = hook(base("CB-0003", stage="repair", active=True))
eq((j.get("action"), j.get("listed")), ("waiting", False), "ตอบว่า waiting")
eq(Vehicle.objects.filter(stock_code="CB-0003").exists(), False, "ยังไม่สร้าง")
st, j = hook(base("CB-0003", stage="show", active=True))
eq((j.get("created"), j.get("listed"), j.get("status")), (True, True, "available"), "ถึงพร้อมขาย → ขึ้นเว็บ")

print("[5] ปิด Active รถที่ขึ้นเว็บอยู่ → ซ่อน (ไม่ลบ)")
v = Vehicle.objects.get(stock_code="CB-0003")
v.price = 459000
v.description = "staff เติมเอง"
v.save()
slug = v.slug
st, j = hook(base("CB-0003", stage="show", active=False))
eq((j.get("action"), j.get("listed"), j.get("path")), ("hidden", False, ""), "ตอบว่า hidden ไม่มี path")
v.refresh_from_db()
eq((v.listed, v.price, v.description, v.deleted_at), (False, 459000, "staff เติมเอง", None), "ประกาศยังอยู่ ราคา/รายละเอียดไม่หาย")
eq("CB-0003" in public_codes(), False, "หน้าค้นหาไม่มีแล้ว")
eq(anon.get("/listings/%s/" % slug).status_code, 404, "ลูกค้าเปิดหน้ารถไม่ได้ (404)")
eq(staff.get("/listings/%s/" % slug).status_code, 200, "staff ยังเปิดดูได้")
eq("ลูกค้ายังไม่เห็นรถคันนี้" in staff.get("/listings/%s/" % slug).content.decode(), True, "staff เห็นป้ายบอกว่าซ่อนอยู่")
eq(anon.get("/listings/%s/book/" % slug).status_code, 404, "ลูกค้าเข้าหน้าจองไม่ได้")
eq(len(anon.get("/compare/?car=%s" % slug).context["cars"]), 0, "หน้าเปรียบเทียบไม่มีรถคันนี้")
eq(len(staff.get("/compare/?car=%s" % slug).context["cars"]), 1, "staff เปรียบเทียบได้")
eq(anon.get("/stock/CB-0003/").status_code, 404, "ลิงก์ /stock/ ลูกค้าเปิดไม่ได้")
eq(staff.get("/stock/CB-0003/").status_code, 302, "ลิงก์ /stock/ staff เด้งไปหน้ารถ")
eq(ai._available().filter(stock_code="CB-0003").exists(), False, "แชทบอท AI ไม่เอาไปเสนอ")
st, j = hook(base("CB-0003", stage="show", active=False))
eq(j.get("action"), "inactive", "ส่งปิดซ้ำ = ไม่เปลี่ยนอะไร")

print("[6] กด Active กลับ → กลับมาครบ")
st, j = hook(base("CB-0003", stage="show", active=True))
v.refresh_from_db()
eq((j.get("created"), j.get("listed"), v.listed, v.price), (False, True, True, 459000), "ใช้ประกาศเดิม ไม่สร้างซ้ำ ราคาเดิม")
eq(Vehicle.objects.filter(stock_code="CB-0003").count(), 1, "ยังมีประกาศเดียว")
eq(anon.get("/stock/CB-0003/").status_code, 302, "ลิงก์ /stock/ ใช้ได้แล้ว")

print("[7] ซ่อนอยู่ + Active ตอนสเตปหลังจอง → เปิดคืนตามสถานะเดิม")
hook(base("CB-0003", stage="reserve", active=True))
hook(base("CB-0003", stage="reserve", active=False))
st, j = hook(base("CB-0003", stage="finance", active=True))
eq((j.get("action"), j.get("listed"), j.get("status")), ("shown", True, "reserved"), "เปิดคืนเป็น 'จองแล้ว'")

print("[8] ขายแล้ว → ซ่อนเสมอ")
st, j = hook(base("CB-0003", stage="sold", status="sold", active=True))
eq((j.get("action"), j.get("listed")), ("sold", False), "ตอบ sold · listed=False")
eq("CB-0003" in public_codes(), False, "ไม่อยู่ในหน้าค้นหา")
st, j = hook(base("CB-0009", stage="sold", status="sold", active=True))
eq(Vehicle.objects.filter(stock_code="CB-0009").exists(), False, "ไม่สร้างประกาศของรถที่ขายแล้ว")

print("[9] รถที่ staff เพิ่มเองในเว็บไม่โดนอะไร")
b = Brand.objects.get_or_create(name="Honda")[0]
m = Vehicle.objects.create(brand=b, model="City", year=2021, price=399000)
eq((m.listed, m.stock_code), (True, ""), "ค่าเริ่มต้น listed=True")
eq(views._available().filter(pk=m.pk).exists(), True, "ลูกค้าเห็นตามเดิม")
eq(anon.get(m.get_absolute_url()).status_code, 200, "หน้ารถเปิดได้ตามเดิม")

print("[10] code ว่าง / body เพี้ยน")
eq(hook({"stage": "show"})[0], 400, "ไม่มี code = 400")
r = anon.post("/api/stock-update/", data="[1,2]", content_type="application/json", HTTP_X_STOCK_SECRET=SECRET)
eq(r.status_code, 400, "body ไม่ใช่ object = 400 (ไม่พัง)")

print("[11] ราคาขายจาก backend")
st, j = hook(base("CB-0020", price=459000))
v20 = Vehicle.objects.get(stock_code="CB-0020")
eq((j.get("created"), v20.price, j.get("price")), (True, 459000, 459000), "สร้างใหม่ได้ราคาเลย (ไม่เป็น 0)")
hook(base("CB-0020", price="445,000"))
v20.refresh_from_db()
eq(v20.price, 445000, "ราคาเปลี่ยนที่ backend → ทับบนเว็บ (รับเลขมีจุลภาค)")
v20.price = 999000
v20.save()
hook(base("CB-0020"))
v20.refresh_from_db()
eq(v20.price, 999000, "backend ไม่ส่งราคา = คงราคาที่ staff ตั้ง")
for bad in (0, -5, "ติดต่อสอบถาม", None, 10 ** 12):
    hook(base("CB-0020", price=bad))
v20.refresh_from_db()
eq(v20.price, 999000, "ราคา 0/ติดลบ/ข้อความ/ใหญ่เกินจริง = ไม่แตะราคาเดิม")
hook(base("CB-0020", active=False, price=410000))
v20.refresh_from_db()
eq((v20.listed, v20.price), (False, 410000), "ซ่อนอยู่ก็อัปเดตราคา (เปิดคืนมาได้ราคาล่าสุด)")
st, j = hook(base("CB-0021", active=False, price=300000))
eq(Vehicle.objects.filter(stock_code="CB-0021").exists(), False, "ยังไม่ Active = ไม่สร้างแม้ส่งราคามา")
hook(base("CB-0020", stage="sold", status="sold", price=1))
v20.refresh_from_db()
eq((v20.status, v20.price), ("sold", 410000), "ขายแล้ว = ไม่แตะราคา")

runner.teardown_databases(old_cfg)
print()
print("ผ่านทั้งหมด" if not fail else "ไม่ผ่าน %d ข้อ: %s" % (len(fail), ", ".join(fail)))
sys.exit(1 if fail else 0)
