from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cars", "0026_vehicle_listed"),
    ]

    operations = [
        migrations.AddField(
            model_name="lead",
            name="forwarded_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="ส่งเข้าห้องพัก Lead เมื่อ"),
        ),
        migrations.AddField(
            model_name="lead",
            name="forward_error",
            field=models.CharField(blank=True, max_length=200, verbose_name="ส่งไม่สำเร็จเพราะ"),
        ),
    ]
