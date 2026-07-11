"""นำเข้าโลโก้แบรนด์ + รูปรถจริงจากโฟลเดอร์ ../oxlet_images
ใช้: python manage.py import_media
- โลโก้ -> Brand.logo
- รูปรถ (จัดกลุ่มตามชื่อไฟล์ <กลุ่ม>-<มุม>.jpg) -> VehicleImage (รูปใหญ่สุด = ปก)
idempotent: ข้ามของที่มีอยู่แล้ว
"""
import re
from collections import defaultdict
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand

from cars.models import Brand, Review, Vehicle, VehicleImage

# ชื่อแบรนด์ -> ไฟล์โลโก้ (ในต้นทาง)
LOGO_MAP = {
    "Toyota": "logo-toyota.png",
    "Honda": "logo-honda.png",
    "Isuzu": "logo-isizu-new.png",
    "Nissan": "logo-nissan.png",
    "Mitsubishi": "logo-mitsubishi.png",
    "Mazda": "logo-mazda.png",
    "Ford": "logo-ford.png",
    "Benz": "logo-benz.png",
    "MG": "logo-mg-new.png",
}

SRC = Path(settings.BASE_DIR).parent / "oxlet_images"
CAR_DIR = SRC / "uploads" / "2026" / "06"
GROUP_RE = re.compile(r"^(\d+)-\d+\.jpg$", re.IGNORECASE)


class Command(BaseCommand):
    help = "นำเข้าโลโก้แบรนด์ + รูปรถจาก oxlet_images"

    def handle(self, *args, **opts):
        if not SRC.exists():
            self.stderr.write(f"ไม่พบโฟลเดอร์ต้นทาง: {SRC}")
            return
        self._logos()
        self._car_photos()
        self._reviews()
        self.stdout.write(self.style.SUCCESS("import_media เสร็จแล้ว"))

    def _find(self, filename):
        for p in SRC.rglob(filename):
            return p
        return None

    def _logos(self):
        n = 0
        for brand in Brand.objects.all():
            if brand.logo:
                continue
            fn = LOGO_MAP.get(brand.name)
            if not fn:
                continue
            path = self._find(fn)
            if not path:
                continue
            with path.open("rb") as f:
                brand.logo.save(fn, File(f), save=True)
            n += 1
        self.stdout.write(f"  โลโก้แบรนด์: {n}")

    def _car_photos(self):
        # จัดกลุ่มรูปตามเลขหน้า ('1-3.jpg' -> กลุ่ม 1)
        groups = defaultdict(list)
        if CAR_DIR.exists():
            for p in CAR_DIR.iterdir():
                m = GROUP_RE.match(p.name)
                if m and p.stat().st_size > 80 * 1024:
                    groups[int(m.group(1))].append(p)
        ordered = [sorted(groups[g], key=lambda x: -x.stat().st_size) for g in sorted(groups)]

        n_cover = 0
        vehicles = list(Vehicle.objects.all())
        for i, veh in enumerate(vehicles):
            if veh.images.exists() or not ordered:
                continue
            photos = ordered[i % len(ordered)][:6]  # รูปใหญ่สุดก่อน = ปก, รวมแกลเลอรี 6 รูป
            for j, path in enumerate(photos):
                with path.open("rb") as f:
                    VehicleImage.objects.create(
                        vehicle=veh, is_cover=(j == 0), order=j,
                        image=File(f, name=f"{veh.slug}-{j}.jpg"),
                    )
            n_cover += 1
        self.stdout.write(f"  รถที่ใส่รูปแล้ว: {n_cover} คัน")

    def _reviews(self):
        # รูปรับรถ (DSC*) ใส่ให้รีวิว
        n = 0
        delivery = self._find("DSC07732.jpg")
        if delivery:
            for r in Review.objects.filter(image=""):
                with delivery.open("rb") as f:
                    r.image.save("review.jpg", File(f), save=True)
                n += 1
                break  # ใส่ตัวอย่าง 1 รูปพอ
        self.stdout.write(f"  รีวิวที่ใส่รูป: {n}")
