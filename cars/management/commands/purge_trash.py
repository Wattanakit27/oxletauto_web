"""ลบรถในถังขยะที่อยู่เกิน 30 วันออกถาวร
ใช้: python manage.py purge_trash
ควรตั้งให้รันอัตโนมัติ (cron / Windows Task Scheduler) วันละครั้ง
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from cars.models import Vehicle


class Command(BaseCommand):
    help = "ลบรถในถังขยะที่เกิน 30 วันออกถาวร"

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=Vehicle.PURGE_DAYS)
        qs = Vehicle.objects.filter(deleted_at__isnull=False, deleted_at__lt=cutoff)
        n = qs.count()
        for car in qs:
            car.delete()
        self.stdout.write(self.style.SUCCESS(
            f"ลบถาวร {n} คัน (อยู่ถังขยะเกิน {Vehicle.PURGE_DAYS} วัน)"))
