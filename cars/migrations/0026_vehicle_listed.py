# ปุ่ม Active ฝั่ง backend (ต.ค.69) — รถจากสต็อกขึ้นหน้าเว็บเมื่อกด Active เท่านั้น
# default=True → ประกาศที่มีอยู่แล้วทุกคัน (ทั้งที่ staff เพิ่มเองและที่ sync มาจาก backend) ยังโชว์เหมือนเดิม

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cars', '0025_plate_is_own_backfill'),
    ]

    operations = [
        migrations.AddField(
            model_name='vehicle',
            name='listed',
            field=models.BooleanField(
                default=True,
                help_text='รถจากสต็อก backend: เปิด/ปิดด้วยปุ่ม Active ในระบบหลังบ้าน (แก้ที่นี่จะถูกทับตอน sync ครั้งถัดไป)',
                verbose_name='แสดงบนหน้าเว็บ'),
        ),
    ]
