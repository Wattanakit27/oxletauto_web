"""ข้อมูลตัวอย่างให้เว็บมีของแสดงทันที: python manage.py seed_demo"""
from django.core.management.base import BaseCommand

from cars.models import (
    Brand,
    Branch,
    CarType,
    Promotion,
    Review,
    Vehicle,
    VehicleOption,
)

BRANDS = ["Toyota", "Honda", "Isuzu", "Nissan", "Mitsubishi", "Mazda", "Ford", "BMW", "Benz", "MG"]
CAR_TYPES = [
    "รถเก๋งสี่ประตู", "รถเก๋งชนิดสองประตู", "รถแฮทช์แบค", "รถ SUV", "รถกระบะ",
    "รถตู้", "รถมินิแวน", "รถเล็ก", "รถเปิดประทุน", "รถซูเปอร์คาร์",
]
DEMO_CARS = [
    ("Honda", "City Hatchback", "1.0 Turbo RS", 2021, "รถแฮทช์แบค", "auto", 1000, 103000, 489000, 10300, "ขาว", "ดำ", True),
    ("Toyota", "Fortuner", "2.8V 4WD", 2016, "รถ SUV", "auto", 2800, 120000, 949000, 14500, "ดำ", "ดำ", True),
    ("Toyota", "Camry", "2.0G", 2017, "รถเก๋งสี่ประตู", "auto", 2000, 95000, 759000, 11200, "เทา", "ครีม", True),
    ("Honda", "Civic", "1.8E", 2018, "รถเก๋งสี่ประตู", "auto", 1800, 78000, 629000, 9300, "ขาว", "ดำ", True),
    ("Mazda", "2", "1.3 High Connect", 2019, "รถแฮทช์แบค", "auto", 1300, 65000, 399000, 6100, "แดง", "ดำ", False),
    ("Isuzu", "D-Max", "1.9 Ddi", 2020, "รถกระบะ", "manual", 1900, 88000, 579000, 8800, "เงิน", "เทา", False),
    ("Nissan", "Almera", "1.0 Turbo VL", 2021, "รถเก๋งสี่ประตู", "auto", 1000, 42000, 459000, 6900, "ดำ", "ดำ", False),
    ("Toyota", "Yaris", "1.2 Sport", 2022, "รถแฮทช์แบค", "auto", 1200, 30000, 519000, 7800, "ขาว", "ดำ", False),
]


class Command(BaseCommand):
    help = "สร้างข้อมูลตัวอย่าง (ยี่ห้อ/ประเภท/รถ/โปร/รีวิว/สาขา)"

    def handle(self, *args, **opts):
        for i, name in enumerate(BRANDS):
            Brand.objects.get_or_create(name=name, defaults={"order": i})
        for i, name in enumerate(CAR_TYPES):
            CarType.objects.get_or_create(name=name, defaults={"order": i})

        cb, _ = Branch.objects.get_or_create(
            name="สาขาชลบุรี",
            defaults={"address": "168 ม.2 ต.บ้านเก่า อ.พานทอง จ.ชลบุรี 20160", "phone": "097-821-8888"},
        )
        Branch.objects.get_or_create(
            name="สาขาสมุทรปราการ", defaults={"phone": "097-821-8888"}
        )

        for (brand, model, sub, year, ctype, trans, cc, mile, price, inst, ce, ci, feat) in DEMO_CARS:
            b = Brand.objects.get(name=brand)
            t = CarType.objects.filter(name=ctype).first()
            v, created = Vehicle.objects.get_or_create(
                brand=b, model=model, submodel=sub, year=year,
                defaults=dict(
                    car_type=t, transmission=trans, engine_cc=cc, mileage=mile,
                    price=price, installment_min=inst, color_exterior=ce,
                    color_interior=ci, is_featured=feat, branch=cb,
                    description="รถสภาพดี ตรวจเช็กแล้ว พร้อมออกรถ จัดไฟแนนซ์ได้ทุกธนาคาร",
                ),
            )
            if created:
                for opt in ["กล้องหลัง", "ล้อแม็ก", "ABS", "ถุงลมนิรภัย", "กุญแจรีโมท", "แอร์ดิจิทัล"]:
                    VehicleOption.objects.create(vehicle=v, name=opt)

        promos = [
            ("Honda Civic 1.8E 2018 ไมล์แท้ ราคาดีที่สุดในตลาด ดอกเบี้ยเริ่ม 1.99%", "Civic"),
            ("Toyota Fortuner 2.8V 4WD ลดทันที 150,000 บาท", "Fortuner"),
            ("ลูกค้า SCB Payroll อนุมัติง่าย 100%", None),
            ("ดอกเบี้ย 2.79% เครดิตดี รับของแถมมูลค่ากว่า 40,000 บาท", None),
        ]
        for i, (title, model) in enumerate(promos):
            veh = Vehicle.objects.filter(model__icontains=model).first() if model else None
            Promotion.objects.get_or_create(title=title, defaults={"vehicle": veh, "order": i})

        reviews = [
            ("คุณสมชาย", "รถสวยตรงปก บริการดีมาก จัดไฟแนนซ์ผ่านง่าย", 5),
            ("คุณนภา", "ประทับใจศูนย์บริการ ดูแลหลังการขายดีจริง", 5),
            ("คุณวิทยา", "ราคาคุ้ม รถเช็กมาดี ออกรถไว", 5),
        ]
        for name, content, rating in reviews:
            Review.objects.get_or_create(customer_name=name, defaults={"content": content, "rating": rating})

        self.stdout.write(self.style.SUCCESS(
            f"seed_demo เสร็จแล้ว: รถ {Vehicle.objects.count()} คัน, "
            f"ยี่ห้อ {Brand.objects.count()}, โปร {Promotion.objects.count()}, รีวิว {Review.objects.count()}"
        ))
