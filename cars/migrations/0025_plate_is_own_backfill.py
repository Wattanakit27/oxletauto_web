"""ป้ายที่ดึงมาจากเว็บอื่น (มี source) ไม่ใช่ป้ายของร้าน — is_own = False
ป้ายที่เพิ่มเองในระบบ (source ว่าง) ถือเป็นของร้าน จึงคง default True ไว้
"""
from django.db import migrations


def mark_imported(apps, schema_editor):
    apps.get_model("cars", "LicensePlate").objects.exclude(source="").update(is_own=False)


class Migration(migrations.Migration):
    dependencies = [("cars", "0024_alter_licenseplate_options_licenseplate_is_own_and_more")]
    operations = [migrations.RunPython(mark_imported, migrations.RunPython.noop)]
