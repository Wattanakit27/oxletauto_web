from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from . import constants


def _unique_slug(model, name, pk, fallback, unicode=True):
    base = slugify(name, allow_unicode=unicode) or fallback
    slug, i = base, 2
    while model.objects.exclude(pk=pk).filter(slug=slug).exists():
        slug = f"{base}-{i}"
        i += 1
    return slug


class Brand(models.Model):
    name = models.CharField("ยี่ห้อ", max_length=60, unique=True)
    slug = models.SlugField(max_length=80, unique=True, blank=True)
    logo = models.ImageField("โลโก้", upload_to="brands/", blank=True, null=True)
    order = models.PositiveIntegerField("ลำดับ", default=0)

    class Meta:
        verbose_name = "ยี่ห้อ"
        verbose_name_plural = "ยี่ห้อ"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug(Brand, self.name, self.pk, "brand")
        super().save(*args, **kwargs)


class CarType(models.Model):
    name = models.CharField("ประเภทตัวถัง", max_length=60, unique=True)
    slug = models.SlugField(max_length=80, unique=True, blank=True)
    order = models.PositiveIntegerField("ลำดับ", default=0)

    class Meta:
        verbose_name = "ประเภทตัวถัง"
        verbose_name_plural = "ประเภทตัวถัง"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug(CarType, self.name, self.pk, "type")
        super().save(*args, **kwargs)


class Branch(models.Model):
    name = models.CharField("สาขา", max_length=80)
    address = models.TextField("ที่อยู่", blank=True)
    phone = models.CharField("เบอร์โทร", max_length=40, blank=True)
    hours = models.CharField("เวลาทำการ", max_length=80, default="08:30 - 16:30")
    map_url = models.URLField("ลิงก์แผนที่", blank=True)

    # Google Maps / Places รีวิว
    google_place_id = models.CharField("Google Place ID", max_length=200, blank=True)
    google_maps_url = models.URLField("ลิงก์ Google Maps (ดูรีวิวทั้งหมด)", blank=True)
    google_rating = models.DecimalField("คะแนน Google", max_digits=2, decimal_places=1, null=True, blank=True)
    google_reviews_count = models.PositiveIntegerField("จำนวนรีวิว Google", default=0)
    lat = models.FloatField("ละติจูด", null=True, blank=True)
    lng = models.FloatField("ลองจิจูด", null=True, blank=True)

    class Meta:
        verbose_name = "สาขา"
        verbose_name_plural = "สาขา"

    def __str__(self):
        return self.name


class Vehicle(models.Model):
    slug = models.SlugField("slug (URL)", max_length=200, unique=True, blank=True)
    # ผูกกับ "รถจริงในสต็อก" ฝั่ง backend (SaleforceOxletauto) ผ่าน API — เก็บ Car.code
    # (ไม่ใช้ FK เพราะคนละฐานข้อมูล/โปรเจกต์ · sync ผ่าน /api/cars/available) · ว่าง = รถที่เพิ่มเองในเว็บ
    stock_code = models.CharField("รหัสสต็อก (backend)", max_length=12, blank=True, db_index=True)
    # ★ ปุ่ม Active ฝั่ง backend — รถจากสต็อกขึ้นหน้าเว็บเมื่อกด Active เท่านั้น (False = ซ่อนจากลูกค้า
    #   แต่ประกาศ/ราคา/รูปที่ staff เติมไว้ยังอยู่ครบ กด Active อีกครั้งก็กลับมา) · รถที่เพิ่มเองในเว็บ = True เสมอ
    listed = models.BooleanField(
        "แสดงบนหน้าเว็บ", default=True,
        help_text="รถจากสต็อก backend: เปิด/ปิดด้วยปุ่ม Active ในระบบหลังบ้าน (แก้ที่นี่จะถูกทับตอน sync ครั้งถัดไป)")
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name="vehicles", verbose_name="ยี่ห้อ")
    model = models.CharField("รุ่น", max_length=80)
    submodel = models.CharField("รุ่นย่อย", max_length=120, blank=True)
    plate = models.CharField("ทะเบียนรถ", max_length=20, blank=True)
    year = models.PositiveIntegerField("ปี")
    car_type = models.ForeignKey(CarType, on_delete=models.SET_NULL, null=True, blank=True, related_name="vehicles", verbose_name="ประเภท")

    transmission = models.CharField("เกียร์", max_length=10, choices=constants.TRANSMISSION_CHOICES, default="auto")
    drivetrain = models.CharField("ขับเคลื่อน", max_length=10, choices=constants.DRIVETRAIN_CHOICES, default="2wd")
    fuel = models.CharField("เชื้อเพลิง", max_length=10, choices=constants.FUEL_CHOICES, default="petrol")
    engine_cc = models.PositiveIntegerField("เครื่องยนต์ (cc)", default=0)
    mileage = models.PositiveIntegerField("เลขไมล์ (กม.)", default=0)
    color_exterior = models.CharField("สีภายนอก", max_length=40, blank=True)
    color_interior = models.CharField("สีภายใน", max_length=40, blank=True)

    price = models.PositiveIntegerField("ราคา (บาท)", default=0)
    installment_min = models.PositiveIntegerField("ค่างวดเริ่มต้น (บาท)", default=0)
    interest_rate = models.DecimalField("ดอกเบี้ย (%)", max_digits=4, decimal_places=2, default=2.79)

    condition = models.CharField("สภาพ", max_length=12, choices=constants.CONDITION_CHOICES, default="certified")
    status = models.CharField("สถานะ", max_length=12, choices=constants.STATUS_CHOICES, default="available")
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="vehicles", verbose_name="สาขา")

    warranty = models.CharField("รับประกัน", max_length=120, default="เครื่อง+เกียร์ 1 ปี / 20,000 กม.")
    inspection_points = models.PositiveIntegerField("จุดตรวจสภาพ", default=150)
    description = models.TextField("รายละเอียด", blank=True)

    is_featured = models.BooleanField("รถแนะนำ (หน้าแรก)", default=False)
    created_at = models.DateTimeField("วันที่ลงประกาศ", auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField("ลบเมื่อ (อยู่ในถังขยะ)", null=True, blank=True)

    PURGE_DAYS = 30  # อยู่ในถังขยะกี่วันก่อนหายถาวร

    @property
    def purge_in_days(self):
        """เหลืออีกกี่วันก่อนถูกลบถาวร (None ถ้าไม่ได้อยู่ในถังขยะ)"""
        if not self.deleted_at:
            return None
        from datetime import timedelta

        from django.utils import timezone
        remaining = (self.deleted_at + timedelta(days=self.PURGE_DAYS)) - timezone.now()
        return max(0, remaining.days)

    class Meta:
        verbose_name = "รถ"
        verbose_name_plural = "รถ"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def title(self):
        parts = [self.brand.name, self.model]
        # ใส่รุ่นย่อยเฉพาะถ้ายังไม่ถูกรวมอยู่ใน model แล้ว (กันชื่อซ้ำ)
        if self.submodel and self.submodel.lower() not in (self.model or "").lower():
            parts.append(self.submodel)
        parts.append(str(self.year))
        return " ".join(p for p in parts if p)

    def save(self, *args, **kwargs):
        if not self.slug:
            # slug ASCII ล้วน (model มักมีรุ่นย่อยอยู่แล้ว เลยไม่ใส่ submodel ซ้ำ)
            self.slug = _unique_slug(
                Vehicle, f"{self.brand.name} {self.model} {self.year}",
                self.pk, "car", unicode=False,
            )
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("car_detail", args=[self.slug])

    @property
    def cover_image(self):
        cover = self.images.filter(is_cover=True).first() or self.images.first()
        return cover.image if cover else None


class VehicleImage(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField("รูป", upload_to="vehicles/")
    is_cover = models.BooleanField("รูปปก", default=False)
    order = models.PositiveIntegerField("ลำดับ", default=0)
    # รหัสต้นทาง (backend Car sale_photo id/path) — ผูกรูปที่ sync มา เพื่อ reconcile ปก/ลบ · ว่าง = staff เพิ่มเอง
    src = models.CharField("รหัสต้นทาง (sync)", max_length=300, blank=True, db_index=True)

    class Meta:
        verbose_name = "รูปรถ"
        verbose_name_plural = "รูปรถ"
        ordering = ["order", "id"]

    def __str__(self):
        return f"รูป {self.vehicle.title}"


class VehicleOption(models.Model):
    """อุปกรณ์/ออปชัน เช่น กล้องหลัง, ABS, ล้อแม็ก"""
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="options")
    name = models.CharField("ออปชัน", max_length=80)

    class Meta:
        verbose_name = "อุปกรณ์/ออปชัน"
        verbose_name_plural = "อุปกรณ์/ออปชัน"

    def __str__(self):
        return self.name


class Promotion(models.Model):
    title = models.CharField("หัวข้อโปร", max_length=160)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.SET_NULL, null=True, blank=True, related_name="promotions", verbose_name="รถที่เกี่ยวข้อง")
    detail = models.TextField("รายละเอียด", blank=True)
    image = models.ImageField("รูปโปร", upload_to="promotions/", blank=True, null=True)
    active = models.BooleanField("แสดงอยู่", default=True)
    order = models.PositiveIntegerField("ลำดับ", default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "โปรโมชัน"
        verbose_name_plural = "โปรโมชัน"
        ordering = ["order", "-created_at"]

    def __str__(self):
        return self.title


class Review(models.Model):
    SOURCE_CHOICES = [("manual", "กรอกเอง"), ("google", "Google Maps")]

    customer_name = models.CharField("ชื่อลูกค้า", max_length=120)
    content = models.TextField("รีวิว", blank=True)
    rating = models.PositiveSmallIntegerField("ดาว", default=5)
    image = models.ImageField("รูป", upload_to="reviews/", blank=True, null=True)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviews")
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviews", verbose_name="สาขา")
    active = models.BooleanField("แสดงอยู่", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # ที่มา: กรอกเอง หรือดึงจาก Google
    source = models.CharField("ที่มา", max_length=10, choices=SOURCE_CHOICES, default="manual")
    author_photo = models.URLField("รูปโปรไฟล์ (Google)", blank=True)
    google_url = models.URLField("ลิงก์รีวิว Google", blank=True)
    relative_time = models.CharField("เวลา (Google)", max_length=60, blank=True)
    reviewed_at = models.DateTimeField("วันที่รีวิวจริง", null=True, blank=True)
    external_id = models.CharField("รหัสรีวิว Google", max_length=200, blank=True, db_index=True)

    class Meta:
        verbose_name = "รีวิวลูกค้า"
        verbose_name_plural = "รีวิวลูกค้า"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.customer_name} ({self.rating}★)"


class BranchPhoto(models.Model):
    """รูปจริงของร้านจาก Google Place Photos (โชว์ในหน้ารีวิว)"""
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField("รูป", upload_to="branch_photos/")
    order = models.PositiveIntegerField("ลำดับ", default=0)

    class Meta:
        verbose_name = "รูปร้าน (Google)"
        verbose_name_plural = "รูปร้าน (Google)"
        ordering = ["order", "id"]

    def __str__(self):
        return f"รูป {self.branch.name}"


class ReviewImage(models.Model):
    """รูปแนบในรีวิว (เหมือนลูกค้าแนบรูปรถ) — แนบได้หลายรูป/รีวิว"""
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField("รูป", upload_to="review_photos/")
    order = models.PositiveIntegerField("ลำดับ", default=0)

    class Meta:
        verbose_name = "รูปแนบรีวิว"
        verbose_name_plural = "รูปแนบรีวิว"
        ordering = ["order", "id"]

    def __str__(self):
        return f"รูปรีวิว {self.review_id}"


class Video(models.Model):
    """คลิปรีวิว — YouTube ดึงอัตโนมัติ / TikTok ใส่เอง"""
    SOURCE_CHOICES = [("youtube", "YouTube"), ("tiktok", "TikTok")]

    source = models.CharField("แพลตฟอร์ม", max_length=10, choices=SOURCE_CHOICES, default="youtube")
    channel = models.CharField("ช่อง", max_length=80, blank=True)
    video_id = models.CharField("รหัสคลิป", max_length=80)
    url = models.URLField("ลิงก์คลิป")
    title = models.CharField("ชื่อคลิป", max_length=255, blank=True)
    thumbnail = models.URLField("รูปหน้าปก", blank=True)
    published_at = models.DateTimeField("วันที่ลง", null=True, blank=True)
    external_id = models.CharField(max_length=120, unique=True)
    active = models.BooleanField("แสดงอยู่", default=True)
    is_featured = models.BooleanField("คลิปแนะนำ (หน้าแรก)", default=False)
    order = models.PositiveIntegerField("ลำดับ (เลข 0 = ใช้วันที่)", default=0)

    class Meta:
        verbose_name = "คลิปรีวิว"
        verbose_name_plural = "คลิปรีวิว"
        ordering = ["order", "-published_at"]

    def __str__(self):
        return f"[{self.source}] {self.title or self.video_id}"

    @property
    def embed_url(self):
        if self.source == "youtube":
            return f"https://www.youtube.com/embed/{self.video_id}"
        if self.source == "tiktok":
            return f"https://www.tiktok.com/embed/v2/{self.video_id}"
        return self.url


class Lead(models.Model):
    """ฟอร์มขอราคา / ติดต่อ — เฟสถัดไปต่อ LINE push"""
    name = models.CharField("ชื่อ", max_length=80)
    phone = models.CharField("เบอร์โทร", max_length=40)
    email = models.EmailField("อีเมล", blank=True)
    message = models.TextField("ข้อความ", blank=True)
    source_page = models.CharField("มาจากหน้า", max_length=120, blank=True)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.SET_NULL, null=True, blank=True, related_name="leads", verbose_name="รถที่สนใจ")
    is_handled = models.BooleanField("ติดตามแล้ว", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    # ต.ค.69 — ส่งต่อเข้าห้องพัก Lead ของ SaleForce (กลุ่ม LINE "ADMIN เก็บ Lead") · ว่าง = ยังไม่ได้ส่ง/ไม่ได้ตั้งค่า
    forwarded_at = models.DateTimeField("ส่งเข้าห้องพัก Lead เมื่อ", null=True, blank=True)
    forward_error = models.CharField("ส่งไม่สำเร็จเพราะ", max_length=200, blank=True)

    class Meta:
        verbose_name = "Lead (คนสนใจ)"
        verbose_name_plural = "Lead (คนสนใจ)"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} - {self.phone}"


class Booking(models.Model):
    """จองรถออนไลน์ (เดโม) — โอนมัดจำผ่าน PromptPay แล้วแนบสลิป"""
    STATUS_CHOICES = [
        ("pending", "รอตรวจสลิป"),
        ("confirmed", "ยืนยันแล้ว"),
        ("cancelled", "ยกเลิก"),
    ]
    vehicle = models.ForeignKey(Vehicle, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="bookings", verbose_name="รถที่จอง")
    name = models.CharField("ชื่อผู้จอง", max_length=80)
    phone = models.CharField("เบอร์โทร", max_length=40)
    deposit_amount = models.PositiveIntegerField("ยอดมัดจำ (บาท)", default=0)
    slip = models.ImageField("สลิปโอนเงิน", upload_to="booking_slips/", blank=True, null=True)
    status = models.CharField("สถานะ", max_length=12, choices=STATUS_CHOICES, default="pending")
    note = models.TextField("หมายเหตุ", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "การจองรถ (เดโม)"
        verbose_name_plural = "การจองรถ (เดโม)"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} · {self.vehicle}"


class SiteSetting(models.Model):
    """ตั้งค่าเว็บ (มีแถวเดียว) — ชื่อร้าน/เบอร์/LINE/เวลาทำการ แก้ได้ในแอดมิน"""
    site_name = models.CharField("ชื่อร้าน", max_length=80, default="Oxlet Auto")
    tagline = models.CharField("สโลแกน", max_length=160, default="โชว์รูมรถมือสอง พร้อมศูนย์บริการ")
    phone = models.CharField("เบอร์โทร", max_length=40, default="097-821-8888")
    line_id = models.CharField("LINE ID", max_length=40, default="@oxletauto")
    hours = models.CharField("เวลาทำการ", max_length=80, default="08.00 - 18.30")
    about_text = models.TextField(
        "เนื้อหาหน้าเกี่ยวกับเรา", blank=True,
        default="เราคัดรถมือสองคุณภาพ ผ่านการตรวจสภาพมาตรฐานสถาบันญี่ปุ่นกว่า 150 จุด "
                "การันตีโครงสร้างเดิม ไม่ชนหนัก ไม่จมน้ำ พร้อมศูนย์บริการครบวงจรดูแลหลังการขาย")
    visitor_count = models.PositiveIntegerField(
        "ยอดผู้เข้าชม (ตั้งเลขตั้งต้นได้ ระบบนับต่อเอง)", default=12000)
    promptpay_id = models.CharField(
        "พร้อมเพย์ร้าน (เบอร์/เลขบัตร) — รับมัดจำจองรถ", max_length=20, default="0812345678")
    deposit_amount = models.PositiveIntegerField("ยอดมัดจำจองรถ ขั้นต่ำ (บาท)", default=1000)

    class Meta:
        verbose_name = "ตั้งค่าเว็บ"
        verbose_name_plural = "ตั้งค่าเว็บ"

    def __str__(self):
        return "ตั้งค่าเว็บ"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class SocialLink(models.Model):
    """ช่องทางติดต่อ/โซเชียล — แก้/เพิ่ม/ลบได้ในแอดมิน"""
    label = models.CharField("ชื่อช่องทาง", max_length=40)
    value = models.CharField("ข้อความที่แสดง", max_length=120, blank=True)
    url = models.CharField("ลิงก์ (รองรับ tel:, https:, line:)", max_length=500)
    icon = models.CharField("ไอคอน (Bootstrap)", max_length=40, default="bi-link-45deg",
                            help_text="เช่น bi-line, bi-facebook, bi-instagram, bi-telephone-fill")
    color = models.CharField("สี (hex)", max_length=20, default="#3b1c6e")
    order = models.PositiveIntegerField("ลำดับ", default=0)
    active = models.BooleanField("แสดงอยู่", default=True)

    class Meta:
        verbose_name = "ช่องทางติดต่อ"
        verbose_name_plural = "ช่องทางติดต่อ"
        ordering = ["order", "id"]

    def __str__(self):
        return self.label


class LicensePlate(models.Model):
    """ป้ายทะเบียนขาย (เลขสวย/เลขมงคล) — เพิ่ม/แก้/ลบจากหน้าเว็บ"""
    STATUS_CHOICES = [("available", "พร้อมขาย"), ("reserved", "จองแล้ว"), ("sold", "ขายแล้ว")]
    TYPE_CHOICES = [
        ("graphic", "ป้ายประมูล (กราฟิก)"),
        ("white", "ป้ายขาว-ดำทั่วไป"),
        ("blue", "ป้ายฟ้า (รถตู้ รย.2)"),
        ("green", "ป้ายเขียว (กระบะ)"),
        ("gold", "ป้ายทอง"),
    ]

    prefix = models.CharField("หมวดอักษร", max_length=10, blank=True, help_text="เช่น กก, ฌฌ, 1กก")
    number = models.CharField("เลขทะเบียน", max_length=10, help_text="เช่น 8888, 1234")
    province = models.CharField("จังหวัด", max_length=40, default="กรุงเทพมหานคร")
    plate_type = models.CharField("ประเภทป้าย", max_length=10, choices=TYPE_CHOICES, default="graphic")
    price = models.PositiveIntegerField("ราคา (บาท)", default=0)
    status = models.CharField("สถานะ", max_length=12, choices=STATUS_CHOICES, default="available")
    image = models.ImageField("รูปป้าย (ถ้ามี)", upload_to="plates/", blank=True, null=True)
    note = models.TextField("รายละเอียด", blank=True)
    is_featured = models.BooleanField("ป้ายแนะนำ", default=False)
    is_own = models.BooleanField("ป้ายของร้านเรา", default=True,
                                 help_text="ป้ายที่เราถือเอง — จะโชว์ขึ้นก่อนป้ายที่ดึงมาจากเว็บอื่นเสมอ")
    created_at = models.DateTimeField(auto_now_add=True)

    # ---- ข้อมูลจากเว็บต้นทาง (เติมโดย import_plates, เว้นว่างถ้าเพิ่มเอง) ----
    source = models.CharField("แหล่งข้อมูล", max_length=30, blank=True,
                              help_text="เช่น chokdee, ben — เว้นว่าง = เพิ่มเอง")
    source_id = models.CharField("รหัสที่ต้นทาง", max_length=30, blank=True)
    source_url = models.URLField("ลิงก์ต้นทาง", max_length=500, blank=True)
    category = models.CharField("หมวดหมู่", max_length=120, blank=True)
    vehicle_type = models.CharField("ประเภทรถ", max_length=60, blank=True,
                                    help_text="เช่น รถยนต์ (รย.1), กระบะ (รย.3)")
    style = models.CharField("รูปแบบป้าย/เลข", max_length=60, blank=True,
                             help_text="ตามต้นทาง เช่น ป้ายขาว-ดำ, 2-2")
    sum_total = models.PositiveIntegerField("ผลรวมตามต้นทาง", null=True, blank=True,
                                            help_text="รวมค่าตัวอักษรด้วย (ผลรวมเลขล้วนคำนวณให้เอง)")
    synced_at = models.DateTimeField("ดึงข้อมูลล่าสุด", null=True, blank=True)

    class Meta:
        verbose_name = "ป้ายทะเบียน"
        verbose_name_plural = "ป้ายทะเบียน"
        ordering = ["-is_own", "-is_featured", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_id"],
                condition=~models.Q(source_id=""),
                name="uniq_plate_per_source",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "plate_type"]),
            models.Index(fields=["-is_own", "-is_featured", "-created_at"]),
            models.Index(fields=["price"]),
        ]

    def __str__(self):
        return f"{self.prefix} {self.number}".strip()

    @property
    def digit_sum(self):
        """ผลรวมเลข (คนไทยดูเลขมงคล) — รวมเลขหน้าหมวดด้วย เช่น 3ขห 2277 = 3+2+2+7+7"""
        return sum(int(c) for c in (self.prefix + self.number) if c.isdigit())

    @property
    def line_url(self):
        from .contact_links import line_message_url
        msg = (f"สนใจป้ายทะเบียน {self.prefix} {self.number} {self.province} "
               f"ราคา {self.price:,} บาท ครับ/ค่ะ 🙏")
        return line_message_url(msg)


class FAQ(models.Model):
    """คำถามที่พบบ่อย — เพิ่ม/แก้/ลบได้จากหน้าเว็บ"""
    question = models.CharField("คำถาม", max_length=200)
    answer = models.TextField("คำตอบ")
    order = models.PositiveIntegerField("ลำดับ", default=0)
    active = models.BooleanField("แสดงอยู่", default=True)

    class Meta:
        verbose_name = "คำถามที่พบบ่อย (FAQ)"
        verbose_name_plural = "คำถามที่พบบ่อย (FAQ)"
        ordering = ["order", "id"]

    def __str__(self):
        return self.question
