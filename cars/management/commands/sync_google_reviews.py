"""ดึงรีวิว Google ของทุกสาขา (ที่ตั้ง Place ID ไว้) มาเก็บใน DB
ใช้: python manage.py sync_google_reviews
ควรตั้ง cron/scheduled รันวันละครั้ง (ไม่ใช่ทุก request — กันค่า API + rate limit)
"""
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.core.management.base import BaseCommand

from cars.google_reviews import fetch_place
from cars.models import Branch, Review


class Command(BaseCommand):
    help = "ซิงค์รีวิว Google Maps ของทุกสาขาเข้า DB"

    def handle(self, *args, **opts):
        key = settings.GOOGLE_MAPS_API_KEY
        if not key:
            self.stderr.write("ยังไม่ตั้ง GOOGLE_MAPS_API_KEY ใน .env — ข้าม")
            return

        branches = Branch.objects.exclude(google_place_id="")
        if not branches:
            self.stderr.write("ยังไม่มีสาขาที่ตั้ง Google Place ID (ตั้งใน /admin/ → สาขา)")
            return

        total_new = 0
        for b in branches:
            data = fetch_place(b.google_place_id, key)
            if not data["ok"]:
                self.stderr.write(f"  {b.name}: {data['error']}")
                continue

            b.google_rating = data["rating"]
            b.google_reviews_count = data["total"]
            if data["maps_url"] and not b.google_maps_url:
                b.google_maps_url = data["maps_url"]
            if data.get("lat"):
                b.lat, b.lng = data["lat"], data["lng"]
            b.save(update_fields=["google_rating", "google_reviews_count", "google_maps_url", "lat", "lng"])

            for rv in data["reviews"]:
                reviewed_at = None
                if rv.get("time"):
                    reviewed_at = datetime.fromtimestamp(rv["time"], tz=dt_timezone.utc)
                _, created = Review.objects.update_or_create(
                    external_id=rv["external_id"],
                    defaults=dict(
                        source="google",
                        branch=b,
                        customer_name=rv["author"] or "ลูกค้า Google",
                        content=rv["text"],
                        rating=rv["rating"],
                        author_photo=rv["photo"],
                        google_url=rv["url"],
                        relative_time=rv["relative_time"],
                        reviewed_at=reviewed_at,
                        active=True,
                    ),
                )
                total_new += int(created)
            self.stdout.write(
                f"  {b.name}: {data['rating']}★ ({data['total']} รีวิว) "
                f"ดึงมา {len(data['reviews'])} รีวิว"
            )

        self.stdout.write(self.style.SUCCESS(f"ซิงค์เสร็จ — รีวิวใหม่ {total_new} รายการ"))
