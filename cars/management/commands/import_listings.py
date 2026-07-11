"""นำเข้ารถจริงจาก scraped_cars.json เข้า DB
- จับคู่รูปกับไฟล์ใน ../oxlet_images ก่อน, ขาดค่อยโหลดจากเว็บ
- ล้างรถเดโมเดิมทิ้งก่อน (ให้เหลือแต่รถจริง)
ใช้: python manage.py import_listings
"""
import json
import urllib.request
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand

from cars.models import Brand, Branch, CarType, Vehicle, VehicleImage, VehicleOption

JSON = Path(settings.BASE_DIR) / "scraped_cars.json"
LOCAL_IMG = Path(settings.BASE_DIR).parent / "oxlet_images"
WP_BASE = "https://www.oxletauto.co.th/wp-content/"
UA = {"User-Agent": "Mozilla/5.0 (compatible; OxletImport/1.0)"}

TRANS = {"อัตโนมัติ": "auto", "ธรรมดา": "manual", "ออโต้": "auto"}
FUEL = {"เบนซิน": "petrol", "ดีเซล": "diesel", "ไฮบริด": "hybrid",
        "ไฟฟ้า": "ev", "hybrid": "hybrid", "e:hev": "hybrid"}
DRIVE = {"2WD": "2wd", "4WD": "4wd", "AWD": "awd", "FWD": "fwd", "RWD": "rwd"}


def digits(s):
    return int("".join(c for c in str(s) if c.isdigit()) or 0)


def map_choice(text, table, default):
    t = (text or "").lower()
    for key, val in table.items():
        if key.lower() in t:
            return val
    return default


class Command(BaseCommand):
    help = "นำเข้ารถจริงจาก scraped_cars.json"

    def add_arguments(self, parser):
        parser.add_argument("--keep-demo", action="store_true", help="ไม่ลบรถเดโมเดิม")

    def handle(self, *args, **opts):
        if not JSON.exists():
            self.stderr.write(f"ไม่พบ {JSON} — รัน scrape_listings.py ก่อน")
            return
        cars = json.loads(JSON.read_text(encoding="utf-8"))

        if not opts["keep_demo"]:
            n = Vehicle.objects.count()
            Vehicle.objects.all().delete()
            self.stdout.write(f"ลบรถเดโมเดิม {n} คัน")

        branch, _ = Branch.objects.get_or_create(
            name="สาขาชลบุรี",
            defaults={"address": "168 ม.2 ต.บ้านเก่า อ.พานทอง จ.ชลบุรี 20160", "phone": "097-821-8888"},
        )

        created = img_local = img_dl = img_fail = 0
        for i, c in enumerate(cars):
            sp = {k.strip(): v.strip() for k, v in c.get("specs", {}).items()}
            brand, _ = Brand.objects.get_or_create(name=(c["brand"] or "อื่นๆ").strip())
            ctype = None
            if sp.get("ประเภท"):
                ctype, _ = CarType.objects.get_or_create(name=sp["ประเภท"])

            veh = Vehicle.objects.create(
                brand=brand,
                model=(c["model"] or c["title"])[:80],
                submodel=sp.get("รุ่นย่อย", "")[:120],
                year=c["year"] or 2020,
                car_type=ctype,
                transmission=map_choice(sp.get("ระบบเกียร์"), TRANS, "auto"),
                fuel=map_choice(sp.get("ประเภทเชื้อเพลิง"), FUEL, "petrol"),
                drivetrain=map_choice(sp.get("ขับเคลื่อน"), DRIVE, "2wd"),
                engine_cc=digits(sp.get("เครื่องยนต์")),
                mileage=digits(sp.get("เลขไมล์")),
                color_exterior=sp.get("สี", "")[:40],
                color_interior=sp.get("สีภายใน", "")[:40],
                price=c["price"],
                installment_min=round(c["price"] / 84 / 100) * 100 if c["price"] else 0,
                branch=branch,
                is_featured=(i < 12),
                description=c["title"],
            )
            for opt in ["กล้องหลัง", "ล้อแม็ก", "ABS", "ถุงลมนิรภัย", "กุญแจรีโมท", "แอร์ดิจิทัล"]:
                VehicleOption.objects.create(vehicle=veh, name=opt)

            for j, rel in enumerate(c.get("images", [])):
                fp = self._image_file(rel)
                if fp is None:
                    img_fail += 1
                    continue
                local, data = fp
                if local:
                    img_local += 1
                else:
                    img_dl += 1
                VehicleImage.objects.create(
                    vehicle=veh, is_cover=(j == 0), order=j,
                    image=File(data, name=f"{veh.slug}-{j}.jpg"),
                )
                data.close()
            created += 1
            if created % 20 == 0:
                self.stdout.write(f"  ...{created}/{len(cars)} คัน")

        self.stdout.write(self.style.SUCCESS(
            f"นำเข้าเสร็จ: {created} คัน · รูปใช้ของในเครื่อง {img_local} / โหลดเพิ่ม {img_dl} / พลาด {img_fail}"
        ))

    def _image_file(self, rel):
        """คืน (is_local, file-handle) — ใช้ไฟล์ในเครื่องก่อน, ขาดค่อยโหลด"""
        local = LOCAL_IMG / rel.replace("/", "\\")
        if local.exists():
            return True, open(local, "rb")
        try:
            req = urllib.request.Request(WP_BASE + rel, headers=UA)
            import io
            data = urllib.request.urlopen(req, timeout=40).read()
            # เซฟลง oxlet_images ไว้ใช้รอบหน้าด้วย
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(data)
            return False, io.BytesIO(data)
        except Exception:
            return None
