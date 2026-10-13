# -*- coding: utf-8 -*-
"""ตรวจปุ่มจองรถ (ต.ค.69 เจ้าของสั่ง "ซ่อนหน้า scan ไว้ก่อน เปลี่ยนให้กด link Line Oxlet พร้อมพิมพ์ข้อความ")

    python scripts/test_booking_line.py

SQLite ชั่วคราว + test client จริง · ตรวจว่า:
  - ONLINE_BOOKING ปิด (ค่าเริ่มต้น): หน้ารถไม่มีลิงก์หน้าจอง QR · ปุ่มจองเปิดแชท LINE @oxletauto
    พร้อมข้อความ "สนใจรุ่นนี้ มาจากเว็บ Oxlet" + ชื่อรถ/ทะเบียน/ราคา/ลิงก์หน้ารถ
  - ลิงก์หน้าจองเก่า (/listings/<slug>/book/) เด้งไปแชท LINE แทน ไม่เจอหน้า QR
  - รถที่ซ่อนอยู่ (ยังไม่ Active) ลิงก์จองยัง 404 ตามเดิม
  - ONLINE_BOOKING เปิด = กลับเป็นหน้า QR เหมือนเดิม
"""
import io
import os
import sys
from urllib.parse import unquote, urlsplit

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["DB_HOST"] = ""      # SQLite ชั่วคราวเสมอ — ห้ามแตะฐานข้อมูลจริง
os.environ["R2_BUCKET"] = ""
os.environ["DEBUG"] = "True"
os.environ["ONLINE_BOOKING"] = ""

import django

django.setup()

from django.conf import settings
from django.test.runner import DiscoverRunner
from django.test.utils import setup_test_environment

setup_test_environment()
runner = DiscoverRunner(verbosity=0, interactive=False)
old_cfg = runner.setup_databases()
settings.ALLOWED_HOSTS = ["*"]

from django.test import Client

from cars.models import Brand, Vehicle

fail = []


def eq(got, want, what):
    if got == want:
        print("  ok   %s" % what)
    else:
        fail.append(what)
        print("  FAIL %s → ได้ %r ควรได้ %r" % (what, got, want))


def line_text(url):
    """https://line.me/R/oaMessage/%40oxletauto/?<ข้อความ> → (oa, ข้อความ)"""
    u = urlsplit(url)
    return unquote(u.path.rstrip("/").split("/")[-1]), unquote(u.query)


anon = Client()
b = Brand.objects.get_or_create(name="Toyota")[0]
car = Vehicle.objects.create(brand=b, model="Hilux Revo", year=2018, price=429000, plate="1กก1234",
                             status="available", stock_code="CS1")
hidden = Vehicle.objects.create(brand=b, model="Yaris", year=2020, price=300000, status="available",
                                stock_code="CS2", listed=False)

print("[1] ค่าเริ่มต้น: ปิดหน้าจอง QR")
eq(settings.ONLINE_BOOKING, False, "ONLINE_BOOKING ปิดโดยปริยาย")
r = anon.get(car.get_absolute_url())
html = r.content.decode()
eq(r.status_code, 200, "หน้ารถเปิดได้")
eq("/book/" in html, False, "ไม่มีลิงก์ไปหน้าจอง QR")
eq("จองรถคันนี้ทาง LINE" in html, True, "มีปุ่มจองทาง LINE")
book_url = r.context["book_line_url"]
eq(book_url.startswith("https://line.me/R/oaMessage/"), True, "ปุ่มจอง = ลิงก์แชท LINE")
eq(book_url in html.replace("&amp;", "&"), True, "ลิงก์อยู่ในหน้าจริง")
oa, text = line_text(book_url)
eq(oa, "@oxletauto", "เปิดแชท @oxletauto")
eq(text.splitlines()[0], "สนใจรุ่นนี้ มาจากเว็บ Oxlet ครับ/ค่ะ 🚗", "บรรทัดแรกบอกว่ามาจากเว็บ Oxlet")
for part, what in [(car.title, "ชื่อรถ"), ("ทะเบียน 1กก1234", "ทะเบียน"), ("ราคา 429,000 บาท", "ราคา"),
                   ("http://testserver" + car.get_absolute_url(), "ลิงก์หน้ารถ")]:
    eq(part in text, True, "ข้อความมี%s" % what)
_, ask = line_text(r.context["line_url"])
eq("มาจากเว็บ Oxlet" in ask, True, "ปุ่มสอบถามทาง LINE ก็บอกว่ามาจากเว็บ")

print("[2] ลิงก์หน้าจองเก่า → แชท LINE")
r = anon.get("/listings/%s/book/" % car.slug)
eq(r.status_code, 302, "เด้ง")
eq(r["Location"], book_url, "ไปแชท LINE พร้อมข้อความเดียวกับปุ่ม")
r = anon.post("/listings/%s/book/" % car.slug, {"name": "x"})
eq(r.status_code, 302, "POST ก็เด้ง (ไม่รับจอง/สลิป)")
car.refresh_from_db()
eq(car.status, "available", "รถไม่ถูกตั้งเป็นจองแล้ว")
eq(anon.get("/listings/%s/book/" % hidden.slug).status_code, 404, "รถที่ซ่อนอยู่ = 404 ตามเดิม")

print("[3] รถไม่มีทะเบียน/ราคา")
nop = Vehicle.objects.create(brand=b, model="Vios", year=2019, price=0, status="available")
_, t = line_text(anon.get(nop.get_absolute_url()).context["book_line_url"])
eq(("ทะเบียน" in t, "ราคา" in t), (False, False), "ไม่ใส่บรรทัดที่ไม่มีค่า")

print("[4] เปิด ONLINE_BOOKING = หน้า QR เหมือนเดิม")
settings.ONLINE_BOOKING = True
html = anon.get(car.get_absolute_url()).content.decode()
eq("/listings/%s/book/" % car.slug in html, True, "มีลิงก์หน้าจอง")
r = anon.get("/listings/%s/book/" % car.slug)
eq(r.status_code, 200, "หน้าจอง QR เปิดได้")
settings.ONLINE_BOOKING = False

runner.teardown_databases(old_cfg)
print()
print("ผ่านทั้งหมด" if not fail else "ไม่ผ่าน %d ข้อ: %s" % (len(fail), ", ".join(fail)))
sys.exit(1 if fail else 0)
