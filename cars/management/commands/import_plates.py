"""นำเข้าป้ายทะเบียนจาก tabien-scraper (plates.csv + โฟลเดอร์ images/)

ใช้:
    python manage.py import_plates                       # ใช้ path ปริยาย (~/Documents/tabien-scraper)
    python manage.py import_plates --dir D:\\tabien-scraper
    python manage.py import_plates --dry-run             # ลองดูก่อน ไม่เขียน DB
    python manage.py import_plates --force-images        # แทนที่รูปเดิมทุกใบ

idempotent: จับคู่ด้วย (source, source_id) — รันซ้ำได้ ข้อมูลอัปเดตทับของเดิม ไม่เกิดแถวซ้ำ
รูปตั้งชื่อไฟล์ในระบบเป็น <source>-<source_id>.png (ASCII ล้วน ปลอดภัยทั้ง local และ R2)
"""
import csv
import re
from datetime import datetime
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from cars.models import LicensePlate

DEFAULT_DIR = Path.home() / "Documents" / "tabien-scraper"

# plate_style / vehicle_type จากต้นทาง -> LicensePlate.TYPE_CHOICES
STYLE_TO_TYPE = [
    ("กราฟิก", "graphic"),
    ("ประมูล", "graphic"),
    ("ขาว-ดำ", "white"),
    ("ขาวดำ", "white"),
    ("ฟ้า", "blue"),
    ("เขียว", "green"),
    ("ทอง", "gold"),
]
VEHICLE_TO_TYPE = [
    ("รย.2", "blue"),       # รถตู้ ป้ายฟ้า
    ("ป้ายฟ้า", "blue"),
    ("มอเตอร์ไซค์", "white"),
    ("มอเตอร์ไซต์", "white"),
]
SOLD_BADGES = {"ขายแล้ว", "จองแล้ว"}
# ben_1กก7337_7471.png -> ("ben", "7471")
IMG_RE = re.compile(r"^(?P<source>[^_]+)_.*_(?P<sid>\d+)$")


class Command(BaseCommand):
    help = "นำเข้าป้ายทะเบียน + รูป จาก tabien-scraper (plates.csv, images/)"

    def add_arguments(self, parser):
        parser.add_argument("--dir", default=str(DEFAULT_DIR),
                            help=f"โฟลเดอร์ scraper (ปริยาย {DEFAULT_DIR})")
        parser.add_argument("--csv", help="ไฟล์ CSV (ปริยาย <dir>/plates.csv)")
        parser.add_argument("--images", help="โฟลเดอร์รูป (ปริยาย <dir>/images)")
        parser.add_argument("--limit", type=int, help="นำเข้าแค่ N แถวแรก (ไว้ทดสอบ)")
        parser.add_argument("--dry-run", action="store_true", help="ไม่เขียน DB แค่รายงานผล")
        parser.add_argument("--no-images", action="store_true", help="ข้ามการคัดลอกรูป")
        parser.add_argument("--force-images", action="store_true",
                            help="แทนที่รูปเดิม (ปริยาย: ใส่เฉพาะใบที่ยังไม่มีรูป)")
        parser.add_argument("--mark-missing-sold", action="store_true",
                            help="ป้ายของ source นี้ที่ไม่มีใน CSV แล้ว ให้ตั้งเป็น 'ขายแล้ว'")

    # ---------- helpers ----------

    def _plate_type(self, style, vehicle_type):
        for key, val in STYLE_TO_TYPE:
            if key in style:
                return val
        for key, val in VEHICLE_TO_TYPE:
            if key in vehicle_type:
                return val
        return "graphic"   # ป้ายประมูลจากเว็บพวกนี้เป็นค่าเริ่มต้น

    def _int(self, raw):
        try:
            return int(round(float(raw)))
        except (TypeError, ValueError):
            return None

    def _dt(self, raw):
        try:
            dt = datetime.fromisoformat(raw)
        except (TypeError, ValueError):
            return None
        return timezone.make_aware(dt) if timezone.is_naive(dt) else dt

    def _image_index(self, img_dir):
        """map (source, source_id) -> Path — อ่านเฉพาะไฟล์ชั้นบนสุด
        (โฟลเดอร์ย่อยตามหมวดเป็นรูปชุดเดียวกันซ้ำ)"""
        index = {}
        if not img_dir.is_dir():
            return index
        for p in img_dir.iterdir():
            if not p.is_file():
                continue
            m = IMG_RE.match(p.stem)
            if m:
                index[(m.group("source"), m.group("sid"))] = p
        return index

    # ---------- main ----------

    def handle(self, *args, **opts):
        base = Path(opts["dir"])
        csv_path = Path(opts["csv"]) if opts["csv"] else base / "plates.csv"
        img_dir = Path(opts["images"]) if opts["images"] else base / "images"
        if not csv_path.is_file():
            raise CommandError(f"ไม่พบไฟล์ CSV: {csv_path}")

        with csv_path.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        if opts["limit"]:
            rows = rows[: opts["limit"]]

        images = {} if opts["no_images"] else self._image_index(img_dir)
        self.stdout.write(f"CSV {csv_path} — {len(rows)} แถว | รูปที่จับคู่ได้ {len(images)} ไฟล์")

        created = updated = with_image = skipped = 0
        seen = {}   # source -> set(source_id)

        for row in rows:
            source = (row.get("source") or "").strip()
            source_id = (row.get("source_id") or "").strip()
            prefix = (row.get("prefix") or "").strip()
            number = (row.get("number") or "").strip()
            if not (prefix or number):        # แถวเสีย — ลองแยกจากช่อง plate
                parts = (row.get("plate") or "").split()
                prefix, number = (parts + ["", ""])[:2]
            if not (prefix or number) or not source_id:
                skipped += 1
                continue
            seen.setdefault(source, set()).add(source_id)

            style = (row.get("plate_style") or "").strip()
            vehicle_type = (row.get("vehicle_type") or "").strip()
            badge = (row.get("badge") or "").strip()
            sold = row.get("in_stock", "").strip().lower() == "false" or badge in SOLD_BADGES

            fields = {
                "prefix": prefix[:10],
                "number": number[:10],
                "province": (row.get("province") or "กรุงเทพมหานคร").strip()[:40],
                "plate_type": self._plate_type(style, vehicle_type),
                "price": self._int(row.get("price")) or 0,
                "status": "sold" if sold else "available",
                "source_url": (row.get("url") or "").strip()[:500],
                "category": (row.get("category") or "").strip()[:120],
                "vehicle_type": vehicle_type[:60],
                "style": style[:60],
                "sum_total": self._int(row.get("sum_total")),
                "synced_at": self._dt(row.get("scraped_at")),
            }

            if opts["dry_run"]:
                exists = LicensePlate.objects.filter(source=source, source_id=source_id).exists()
                updated += exists
                created += not exists
                continue

            with transaction.atomic():
                # is_own อยู่ใน create_defaults เท่านั้น — ถ้าสตาฟติ๊กว่าเป็นป้ายของร้านเอง
                # การ import รอบถัดไปจะไม่ไปล้างค่าทิ้ง
                obj, is_new = LicensePlate.objects.update_or_create(
                    source=source, source_id=source_id, defaults=fields,
                    create_defaults={**fields, "is_own": False})
            created, updated = created + is_new, updated + (not is_new)

            path = images.get((source, source_id))
            if path and (opts["force_images"] or not obj.image):
                if obj.image:
                    obj.image.delete(save=False)
                with path.open("rb") as fh:
                    obj.image.save(f"{source}-{source_id}.png", File(fh), save=True)
                with_image += 1

        missing_marked = 0
        if opts["mark_missing_sold"] and not opts["dry_run"]:
            for source, ids in seen.items():
                missing_marked += (LicensePlate.objects
                                   .filter(source=source).exclude(source_id__in=ids)
                                   .exclude(status="sold").update(status="sold"))

        head = "[dry-run] " if opts["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(
            f"{head}เพิ่มใหม่ {created} | อัปเดต {updated} | ใส่รูป {with_image} | "
            f"ข้าม {skipped} | ตั้งขายแล้ว(หายจาก CSV) {missing_marked} | "
            f"รวมในระบบ {LicensePlate.objects.count()} ใบ"))
