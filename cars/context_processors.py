from django.conf import settings

from .models import Branch, SiteSetting, SocialLink


def site_globals(request):
    """ตัวแปรที่ใช้ทุกหน้า (navbar/footer) — ดึงจาก DB แก้ได้ในแอดมิน"""
    s = SiteSetting.get()
    return {
        "SITE_NAME": s.site_name,
        "SITE_TAGLINE": s.tagline,
        "SITE_PHONE": s.phone,
        "SITE_HOURS": s.hours,
        "SITE_LINE": s.line_id,
        "SITE_URL": settings.SITE_URL,
        "branches": Branch.objects.all(),
        "SOCIALS": list(SocialLink.objects.filter(active=True)),
    }
