from django.db import migrations


def seed(apps, schema_editor):
    SiteSetting = apps.get_model("cars", "SiteSetting")
    SocialLink = apps.get_model("cars", "SocialLink")
    from cars.contact_links import line_message_url

    SiteSetting.objects.get_or_create(pk=1, defaults=dict(
        site_name="Oxlet Auto",
        tagline="โชว์รูมรถมือสอง พร้อมศูนย์บริการ",
        phone="097-821-8888",
        line_id="@oxletauto",
        hours="08.00 - 18.30",
    ))

    if not SocialLink.objects.exists():
        data = [
            ("โทร", "097-821-8888", "tel:0978218888", "bi-telephone-fill", "#0d6efd"),
            ("LINE", "@oxletauto", line_message_url(), "bi-line", "#06c755"),
            ("Facebook", "Oxlet Auto", "https://www.facebook.com/oxlet.bankao", "bi-facebook", "#1877f2"),
            ("Instagram", "@oxletauto", "https://www.instagram.com/oxletauto/", "bi-instagram", "#e1306c"),
            ("YouTube", "Oxlet Auto", "https://www.youtube.com/channel/UCjEjYmV1cjQUBLiZosRUmEw", "bi-youtube", "#ff0000"),
            ("TikTok", "@oxletauto", "https://www.tiktok.com/@oxletauto", "bi-tiktok", "#000000"),
        ]
        for i, (label, value, url, icon, color) in enumerate(data):
            SocialLink.objects.create(label=label, value=value, url=url, icon=icon, color=color, order=i)


def unseed(apps, schema_editor):
    apps.get_model("cars", "SocialLink").objects.all().delete()
    apps.get_model("cars", "SiteSetting").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("cars", "0011_sitesetting_sociallink")]
    operations = [migrations.RunPython(seed, unseed)]
