"""เพิ่มคลิป TikTok จากลิงก์ (ดึงรูปปก/ชื่อ/ช่อง อัตโนมัติ)
ใช้: python manage.py add_tiktok <url1> <url2> ...
"""
import json
import re
import urllib.parse
import urllib.request

from django.core.management.base import BaseCommand

from cars.models import Video

UA = {"User-Agent": "Mozilla/5.0"}


class Command(BaseCommand):
    help = "เพิ่มคลิป TikTok จากลิงก์"

    def add_arguments(self, parser):
        parser.add_argument("urls", nargs="+", help="ลิงก์คลิป TikTok")
        parser.add_argument("--featured", action="store_true", help="ตั้งเป็นคลิปแนะนำหน้าแรก")

    def handle(self, *args, **opts):
        ok = 0
        for url in opts["urls"]:
            m = re.search(r"/video/(\d+)", url)
            if not m:
                self.stderr.write(f"  ลิงก์ไม่ถูกต้อง: {url}")
                continue
            vid = m.group(1)
            ch = re.search(r"@([\w.]+)/video", url)
            channel = "@" + ch.group(1) if ch else ""
            title, thumb = "", ""
            try:
                o = "https://www.tiktok.com/oembed?url=" + urllib.parse.quote(url, safe="")
                d = json.loads(urllib.request.urlopen(urllib.request.Request(o, headers=UA), timeout=30).read().decode("utf-8"))
                title, thumb = d.get("title", "")[:255], d.get("thumbnail_url", "")
            except Exception as e:
                self.stderr.write(f"  oembed พลาด {vid}: {e}")
            Video.objects.update_or_create(
                external_id=f"tiktok:{vid}",
                defaults=dict(source="tiktok", channel=channel, video_id=vid, url=url,
                              title=title, thumbnail=thumb, order=40,
                              active=True, is_featured=opts["featured"]),
            )
            ok += 1
            self.stdout.write(f"  [{ok}] {channel} | {title[:42] or vid}")
        self.stdout.write(self.style.SUCCESS(
            f"เพิ่ม {ok} คลิป | รวม TikTok {Video.objects.filter(source='tiktok').count()}"))
