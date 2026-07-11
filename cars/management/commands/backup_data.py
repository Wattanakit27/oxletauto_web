"""สำรองข้อมูล DB + รูป (media) เป็นไฟล์ zip เดียว — พร้อมย้ายไป Postgres/Supabase

ใช้:  python manage.py backup_data
ได้ไฟล์:  backups/backup_<วันเวลา>.zip   (ข้างในมี data.json + โฟลเดอร์ media/)

กู้คืน / ย้ายขึ้น DB ใหม่ (เช่น Supabase):
  1) แตก zip:  ได้ data.json + media/
  2) ตั้งค่า DB_HOST ใน .env ให้ชี้ Postgres แล้ว  python manage.py migrate
  3) python manage.py loaddata data.json
  4) ก๊อปโฟลเดอร์ media/ ที่แตกออกมา ไปวางทับ media/ ของโปรเจกต์
"""
import io
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

# โมเดลที่ไม่ต้อง dump (สร้างเองอัตโนมัติ / เป็นข้อมูลชั่วคราว)
EXCLUDE = ["contenttypes", "auth.permission", "admin.logentry", "sessions.session"]


class Command(BaseCommand):
    help = "สำรองข้อมูล DB + รูป media เป็นไฟล์ zip เดียว (ใช้ย้ายไป Postgres/Supabase)"

    def handle(self, *args, **options):
        backup_dir = settings.BASE_DIR / "backups"
        backup_dir.mkdir(exist_ok=True)
        ts = timezone.localtime().strftime("%Y%m%d_%H%M%S")
        zip_path = backup_dir / f"backup_{ts}.zip"

        # 1) dump ข้อมูล DB เป็น string
        buf = io.StringIO()
        call_command(
            "dumpdata",
            exclude=EXCLUDE,
            use_natural_foreign_keys=True,
            use_natural_primary_keys=True,
            indent=2,
            stdout=buf,
        )
        data_json = buf.getvalue()

        # 2) ใส่ data.json + ไฟล์ media ทั้งหมดลง zip เดียว
        media_root = Path(settings.MEDIA_ROOT)
        n_media = 0
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("data.json", data_json)
            if media_root.exists():
                for p in media_root.rglob("*"):
                    if p.is_file():
                        arc = "media/" + str(p.relative_to(media_root)).replace("\\", "/")
                        z.write(p, arcname=arc)
                        n_media += 1

        mb = zip_path.stat().st_size / (1024 * 1024)
        self.stdout.write(self.style.SUCCESS(f"✓ สำรองครบในไฟล์เดียว: {zip_path}"))
        self.stdout.write(f"  • ข้อมูล DB : data.json")
        self.stdout.write(f"  • รูป media : {n_media} ไฟล์")
        self.stdout.write(f"  • ขนาดรวม  : {mb:.1f} MB")
