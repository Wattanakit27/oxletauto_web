"""ดึงรูปจริงของร้านจาก Google Place Photos มาเก็บ (โชว์ในหน้ารีวิว)
ใช้: python manage.py sync_google_photos
"""
import io
import json
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand

from cars.models import Branch, BranchPhoto

DETAILS = "https://maps.googleapis.com/maps/api/place/details/json"
PHOTO = "https://maps.googleapis.com/maps/api/place/photo"
UA = {"User-Agent": "Mozilla/5.0 (compatible; OxletImport/1.0)"}


class Command(BaseCommand):
    help = "ดึงรูปร้านจาก Google Place Photos"

    def add_arguments(self, parser):
        parser.add_argument("--max", type=int, default=8, help="จำนวนรูปต่อสาขา")

    def handle(self, *args, **opts):
        key = settings.GOOGLE_MAPS_API_KEY
        if not key:
            self.stderr.write("ยังไม่ตั้ง GOOGLE_MAPS_API_KEY — ข้าม")
            return

        total = 0
        for b in Branch.objects.exclude(google_place_id=""):
            # 1) ขอรายการ photo_reference
            u = DETAILS + "?" + urllib.parse.urlencode(
                {"place_id": b.google_place_id, "fields": "photos", "key": key})
            data = json.loads(urllib.request.urlopen(u, timeout=30).read().decode("utf-8"))
            refs = [p["photo_reference"] for p in data.get("result", {}).get("photos", [])]
            if not refs:
                self.stdout.write(f"  {b.name}: ไม่มีรูป")
                continue

            b.photos.all().delete()  # ดึงใหม่ทุกครั้ง (รูปไม่เยอะ)
            for i, ref in enumerate(refs[: opts["max"]]):
                pu = PHOTO + "?" + urllib.parse.urlencode(
                    {"maxwidth": 1200, "photo_reference": ref, "key": key})
                try:
                    img = urllib.request.urlopen(urllib.request.Request(pu, headers=UA), timeout=40).read()
                    BranchPhoto.objects.create(
                        branch=b, order=i,
                        image=File(io.BytesIO(img), name=f"{b.pk}-{i}.jpg"),
                    )
                    total += 1
                except Exception as e:
                    self.stderr.write(f"    รูป {i} พลาด: {e}")
            self.stdout.write(f"  {b.name}: ดึง {b.photos.count()} รูป")

        self.stdout.write(self.style.SUCCESS(f"เสร็จ — รูปร้านทั้งหมด {total} รูป"))
