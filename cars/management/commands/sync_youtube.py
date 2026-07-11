"""ดึงคลิปล่าสุดจากช่อง YouTube (RSS feed ฟรี ไม่ต้อง API key)
ใช้: python manage.py sync_youtube
ตั้ง cron รันวันละครั้งให้คลิปใหม่ขึ้นเอง
"""
import re
import urllib.request
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime

from cars.models import Video

RSS = "https://www.youtube.com/feeds/videos.xml?channel_id="


class Command(BaseCommand):
    help = "ดึงคลิป YouTube ล่าสุดจากช่อง"

    def handle(self, *args, **opts):
        cid = settings.YOUTUBE_CHANNEL_ID
        if not cid:
            self.stderr.write("ยังไม่ตั้ง YOUTUBE_CHANNEL_ID")
            return
        try:
            xml = urllib.request.urlopen(RSS + cid, timeout=30).read().decode("utf-8")
        except Exception as e:
            self.stderr.write(f"ดึง RSS ไม่สำเร็จ: {e}")
            return

        entries = re.findall(r"<entry>(.*?)</entry>", xml, re.S)
        n_new = 0
        for ent in entries:
            vid = _find(r"<yt:videoId>([\w-]+)</yt:videoId>", ent)
            if not vid:
                continue
            title = _find(r"<title>([^<]+)</title>", ent)
            pub = _find(r"<published>([^<]+)</published>", ent)
            published = parse_datetime(pub) if pub else None
            _, created = Video.objects.update_or_create(
                external_id=f"youtube:{vid}",
                defaults=dict(
                    source="youtube", video_id=vid,
                    url=f"https://www.youtube.com/watch?v={vid}",
                    title=title or "",
                    thumbnail=f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                    published_at=published, active=True,
                ),
            )
            n_new += int(created)

        self.stdout.write(self.style.SUCCESS(
            f"ซิงค์ YouTube เสร็จ — ทั้งหมด {Video.objects.filter(source='youtube').count()} คลิป (ใหม่ {n_new})"
        ))


def _find(pattern, text):
    m = re.search(pattern, text)
    return m.group(1) if m else ""
