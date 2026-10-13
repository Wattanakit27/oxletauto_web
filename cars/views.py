import json
import threading
import time
import urllib.request

from django.conf import settings
from django.core.files.base import ContentFile
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import constants
from .ai import chat_reply
from .contact_links import car_inquiry_text, line_message_url
from .forms import (
    BookingForm,
    BranchForm,
    FAQForm,
    LicensePlateForm,
    PromotionForm,
    SiteSettingForm,
    SocialLinkForm,
    VehicleForm,
)
from .models import (
    FAQ,
    Booking,
    Branch,
    Brand,
    CarType,
    Lead,
    LicensePlate,
    Promotion,
    Review,
    SiteSetting,
    SocialLink,
    Vehicle,
    VehicleImage,
)
from .promptpay import promptpay_payload


def _available():
    # listed=False = รถจากสต็อกที่ยังไม่กด Active ในระบบหลังบ้าน → ลูกค้าไม่เห็น (ai._available ต้องตรงกัน)
    return (Vehicle.objects.filter(deleted_at__isnull=True, listed=True)
            .exclude(status="sold").select_related("brand", "car_type"))


def _visible(request):
    """เงื่อนไขรถที่ "คนนี้" เปิดดูหน้ารถได้ — staff เห็นรถที่ซ่อนอยู่ด้วย (ไว้ตรวจก่อนกด Active)"""
    q = Q(deleted_at__isnull=True)
    if not request.user.is_staff:
        q &= Q(listed=True)
    return q


def _sync_car_photos(vehicle_id, photos):
    """reconcile รูป Vehicle ให้ตรงกับรูปขายฝั่ง backend (photos=[{url,key}] · index0=ปก) — รันใน thread.
    - src=key ผูกรูปกับต้นทาง: มี key แล้ว→อัปเดตปก/ลำดับ (ไม่โหลดซ้ำ) · ยังไม่มี→โหลดใหม่
    - ลบรูปที่เคย sync แต่ถูกลบที่ backend (มี src · ไม่อยู่ใน list) · ไม่แตะรูปที่ staff เพิ่มเอง (src ว่าง)
    - ปก authoritative = รูป index0 ของ backend"""
    v = Vehicle.objects.filter(id=vehicle_id).first()
    if not v:
        return
    # กันรูปซ้ำ src เดียวกัน (จาก race/ของเก่า) — เก็บอันแรก ลบที่เหลือ (self-heal)
    _seen = set()
    for im in v.images.exclude(src="").order_by("id"):
        if im.src in _seen:
            im.delete()
        else:
            _seen.add(im.src)
    keys = []
    for i, p in enumerate(photos):
        if not isinstance(p, dict):
            continue
        key = str(p.get("key") or "").strip()
        url = str(p.get("url") or "").strip()
        if not key or not url:
            continue
        keys.append(key)
        img = v.images.filter(src=key).first()
        if img:
            if img.is_cover != (i == 0) or img.order != i:
                img.is_cover = (i == 0)
                img.order = i
                img.save(update_fields=["is_cover", "order"])
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "oxlet-sync"})
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = resp.read()
            if not data:
                continue
            name = url.split("?")[0].split("/")[-1] or ("photo%d.jpg" % i)
            if "." not in name:
                name += ".jpg"
            img = VehicleImage(vehicle=v, src=key, is_cover=(i == 0), order=i)
            img.image.save(name, ContentFile(data), save=True)
        except Exception:
            pass
    if not keys:
        return
    # ลบรูปที่เคย sync แต่ถูกลบที่ backend (มี src · ไม่อยู่ใน keys) — คงรูปที่ staff เพิ่มเอง (src ว่าง)
    v.images.exclude(src="").exclude(src__in=keys).delete()
    # ปก = รูป index0 ของ backend → ล้าง cover อื่นให้เหลือปกตัวเดียว
    cover = v.images.filter(src=keys[0]).first()
    if cover:
        v.images.exclude(pk=cover.pk).filter(is_cover=True).update(is_cover=False)
        if not cover.is_cover:
            cover.is_cover = True
            cover.save(update_fields=["is_cover"])


def _truthy(v, default=True):
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _price_in(v):
    """ราคาขายที่ backend ส่งมา → int บาท หรือ None (ไม่ส่ง/0/ติดลบ/เพี้ยน = ไม่แตะราคาบนเว็บ)"""
    try:
        n = int(float(str(v).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None
    return n if 0 < n < 100_000_000 else None


def _stock_reply(v, action, code, created=False, **extra):
    """คำตอบของ webhook — backend เอา `listed` ไปโชว์ว่า "ขึ้นเว็บแล้วจริงไหม" (ไม่เดาเอง)"""
    listed = bool(v and v.listed and v.status != "sold" and not v.deleted_at)
    out = {"ok": True, "action": action, "code": code, "created": created, "listed": listed,
           "status": v.status if v else "", "price": v.price if v else None,
           "path": v.get_absolute_url() if (v and listed) else ""}
    out.update(extra)
    return JsonResponse(out)


@csrf_exempt
@require_POST
def api_stock_update(request):
    """Webhook รับจาก backend (SaleforceOxletauto) — รถในสต็อกเปลี่ยนสถานะ / กดปุ่ม Active (realtime).
    ยืนยันด้วย secret · ผูกด้วย Vehicle.stock_code = Car.code ของ backend

    ★ ปุ่ม Active (ต.ค.69): รถจาก backend ขึ้นหน้าเว็บเมื่อ `active=true` **และ** ถึงสเตปพร้อมขาย/จอง
      - active=false → มีประกาศอยู่ = ซ่อน (listed=False · ข้อมูล/ราคา/รูปยังอยู่) · ยังไม่มี = ไม่สร้าง
      - active=true + พร้อมขาย/จอง → มีประกาศ = อัปเดตสถานะ + เปิดโชว์ · ยังไม่มี = สร้างใหม่ (ราคาจาก backend · ไม่มี = 0)
      - active=true + สเตปอื่น → มีประกาศ = เปิดโชว์ (สถานะเดิม) · ยังไม่มี = รอถึงพร้อมขาย (`waiting`)
      - ขายแล้ว → ซ่อน (status=sold) เสมอ ไม่ว่า active จะเป็นอะไร
      - ไม่ส่ง `active` มา (backend รุ่นเก่า) = ถือว่า true → พฤติกรรมเดิมทุกอย่าง
    ★ ราคาขาย (ต.ค.69): `price` จาก backend = แหล่งความจริงของราคา → มีค่า = ทับราคาบนเว็บทุกครั้ง
      (สร้างใหม่ก็ใช้เลย ไม่เป็น 0 แล้ว) · ไม่ส่ง/ว่าง = คงราคาที่ staff ตั้งในเว็บไว้
    คำตอบมี `listed` = ตอนนี้ลูกค้าเห็นรถคันนี้บนเว็บไหม (backend เอาไปโชว์สถานะจริง)."""
    secret = getattr(settings, "STOCK_SYNC_SECRET", "")
    got = request.headers.get("X-Stock-Secret") or request.POST.get("secret") or ""
    if not secret or got != secret:
        return JsonResponse({"ok": False, "error": "unauthorized"}, status=401)
    try:
        data = json.loads(request.body or "{}")
    except (ValueError, TypeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    code = str(data.get("code") or "").strip()
    stage = str(data.get("stage") or "").strip()
    status_in = str(data.get("status") or "").strip()
    active = _truthy(data.get("active"), default=True)
    price = _price_in(data.get("price"))
    if not code:
        return JsonResponse({"ok": False, "error": "no code"}, status=400)

    # ขายแล้ว → ซ่อน (อัปเดตเฉพาะประกาศที่มีอยู่ · ไม่สร้างประกาศ sold ใหม่)
    if stage == "sold" or status_in == "sold":
        matched = (Vehicle.objects.filter(stock_code=code, deleted_at__isnull=True)
                   .update(status="sold"))
        return JsonResponse({"ok": True, "action": "sold", "matched": matched, "created": False,
                             "code": code, "listed": False, "status": "sold", "path": ""})

    v = Vehicle.objects.filter(stock_code=code, deleted_at__isnull=True).first()
    if v and price and v.price != price:      # ราคาตาม backend เสมอ (รวมตอนซ่อนอยู่ — เปิดคืนมาได้ราคาล่าสุด)
        v.price = price
        v.save(update_fields=["price", "updated_at"])

    # ยังไม่ Active → ซ่อน (ไม่ลบ — staff เติมราคา/รายละเอียดไว้แล้ว กด Active ใหม่ต้องได้คืนครบ)
    if not active:
        if v and v.listed:
            v.listed = False
            v.save(update_fields=["listed", "updated_at"])
            return _stock_reply(v, "hidden", code)
        return _stock_reply(v, "inactive", code)

    if stage == "show":
        new_status = "available"
    elif stage == "reserve":
        new_status = "reserved"
    else:
        new_status = ""

    if not new_status:
        # Active แล้วแต่รถยังไม่ถึงพร้อมขาย/จอง — มีประกาศอยู่ (เคยขึ้นแล้ว) = เปิดโชว์ตามสถานะเดิม
        if v and not v.listed:
            v.listed = True
            v.save(update_fields=["listed", "updated_at"])
            return _stock_reply(v, "shown", code)
        return _stock_reply(v, "waiting" if not v else "ignored", code, stage=stage)

    # พร้อมขาย/จอง — มีประกาศแล้ว = อัปเดตสถานะ · ยังไม่มี = สร้างใหม่ (โชว์ลูกค้าทันที · staff เติมราคาทีหลัง)
    created = False
    if v:
        fields = []
        if v.status != new_status:
            v.status = new_status
            fields.append("status")
        if not v.listed:
            v.listed = True
            fields.append("listed")
        if fields:
            v.save(update_fields=fields + ["updated_at"])
    else:
        brand, _ = Brand.objects.get_or_create(name=(data.get("brand") or "").strip() or "ไม่ระบุ")
        try:
            year = int(data.get("year") or 0)
        except (ValueError, TypeError):
            year = 0
        year = year or timezone.now().year
        try:
            km = int(data.get("km") or 0)
        except (ValueError, TypeError):
            km = 0
        v = Vehicle.objects.create(
            stock_code=code, brand=brand,
            model=(data.get("model") or "").strip() or "-",
            year=year,
            color_exterior=(data.get("color") or "").strip(),
            plate=(data.get("plate") or "").strip(),
            mileage=km, price=price or 0, status=new_status, listed=True,
        )
        created = True

    # รูปขายจาก backend → reconcile (เปลี่ยนปก/เพิ่ม/ลบให้ตรงกัน) ใน thread
    photos = data.get("photos")
    if isinstance(photos, list) and photos:
        if SYNC_PHOTOS_BG:
            threading.Thread(target=_sync_car_photos, args=(v.id, list(photos)), daemon=True).start()
        else:
            _sync_car_photos(v.id, list(photos))

    return _stock_reply(v, new_status, code, created=created,
                        photos=len(photos) if isinstance(photos, list) else 0)


SYNC_PHOTOS_BG = True   # เทสต์ปิดไว้ (thread โหลดรูปไม่ให้วิ่งชนฐานข้อมูลทดสอบ)


def stock_redirect(request, code):
    """/stock/<รหัสรถ backend>/ → หน้ารถบนเว็บ — ระบบหลังบ้านใช้ทำลิงก์ "ดูบนเว็บ" โดยไม่ต้องรู้ slug
    รถที่ยังไม่ Active = ลูกค้าเปิดไม่ได้ (404) · staff เปิดดูได้"""
    v = (Vehicle.objects.filter(_visible(request), stock_code=str(code or "").strip())
         .order_by("-created_at").first())
    if not v:
        from django.http import Http404
        raise Http404("ไม่พบรถคันนี้บนเว็บ")
    return redirect(v.get_absolute_url())


def home(request):
    from .models import BranchPhoto, Video
    avail = _available()
    # การ์ดประเภทรถ: ดึงรถตัวแทน 1 คัน/ประเภท ที่ "พร้อมขายจริง" (status=available เท่านั้น
    # ไม่เอาจอง/ขายแล้ว) และต้องมีรูป — ถ้าคันนั้นถูกจอง/ขายทีหลัง จะหลุดออกแล้วสลับคันใหม่ให้เอง
    categories = []
    for t in CarType.objects.all()[:4]:
        car = (avail.filter(car_type=t, status="available", images__isnull=False)
               .distinct().first())
        categories.append({"type": t, "car": car})
    # ยอดผู้เข้าชม — นับ 1 ครั้ง/เซสชัน (ตั้งเลขตั้งต้นได้ที่ ตั้งค่าเว็บ → visitor_count)
    SiteSetting.get()  # กันกรณียังไม่มีแถว pk=1
    if not request.session.get("visited"):
        SiteSetting.objects.filter(pk=1).update(visitor_count=F("visitor_count") + 1)
        request.session["visited"] = True
    visitor_count = SiteSetting.objects.values_list("visitor_count", flat=True).first()
    ctx = {
        "featured": avail.filter(is_featured=True)[:8] or avail[:8],
        "total_cars": avail.count(),
        "visitor_count": visitor_count,
        "categories": categories,
        "promotions": Promotion.objects.filter(active=True)[:6],
        "reviews": _reviews_ranked()[:6],
        "featured_yt": Video.objects.filter(active=True, is_featured=True, source="youtube")[:4],
        "featured_tt": Video.objects.filter(active=True, is_featured=True, source="tiktok")[:6],
        "branch_photos": BranchPhoto.objects.select_related("branch")[:16],
        "brands": Brand.objects.all(),
        "car_types": CarType.objects.all(),
        "price_ranges": constants.PRICE_RANGES,
        "transmissions": constants.TRANSMISSION_CHOICES,
    }
    return render(request, "home.html", ctx)


def all_cars(request):
    qs = _available()

    # --- ฟิลเตอร์ ---
    brand = request.GET.get("brand")
    model = request.GET.get("model")
    car_type = request.GET.get("type")
    transmission = request.GET.get("transmission")
    drivetrain = request.GET.get("drivetrain")
    price_range = request.GET.get("price")
    year = request.GET.get("year")
    keyword = request.GET.get("q")

    if brand:
        qs = qs.filter(brand__slug=brand)
    if model:
        qs = qs.filter(model__iexact=model)
    if car_type:
        qs = qs.filter(car_type__slug=car_type)
    if transmission:
        qs = qs.filter(transmission=transmission)
    if drivetrain:
        qs = qs.filter(drivetrain=drivetrain)
    if year:
        qs = qs.filter(year=year)
    if price_range:
        for key, _label, lo, hi in constants.PRICE_RANGES:
            if key == price_range:
                qs = qs.filter(price__gte=lo, price__lt=hi)
                break
    if keyword:
        qs = qs.filter(
            Q(model__icontains=keyword)
            | Q(submodel__icontains=keyword)
            | Q(brand__name__icontains=keyword)
        )

    # --- เรียงลำดับ ---
    sort = request.GET.get("sort", "-created_at")
    valid_sorts = {s[0] for s in constants.SORT_OPTIONS}
    if sort not in valid_sorts:
        sort = "-created_at"
    qs = qs.order_by(sort)

    # --- แบ่งหน้า ---
    paginator = Paginator(qs, 12)
    page = paginator.get_page(request.GET.get("page"))

    # คง query string ตอนเปลี่ยนหน้า
    params = request.GET.copy()
    params.pop("page", None)

    ctx = {
        "page": page,
        "total": paginator.count,
        "brands": Brand.objects.all(),
        "car_types": CarType.objects.all(),
        "price_ranges": constants.PRICE_RANGES,
        "transmissions": constants.TRANSMISSION_CHOICES,
        "drivetrains": constants.DRIVETRAIN_CHOICES,
        "sort_options": constants.SORT_OPTIONS,
        "current": request.GET,
        "querystring": params.urlencode(),
    }
    return render(request, "all_cars.html", ctx)


def car_detail(request, slug):
    car = get_object_or_404(
        Vehicle.objects.select_related("brand", "car_type", "branch").filter(_visible(request)),
        slug=slug,
    )
    related = (
        _available()
        .filter(brand=car.brand)
        .exclude(pk=car.pk)[:4]
    )
    inquiry_text = car_inquiry_text(
        car.title, request.build_absolute_uri(),
        getattr(car, "price", None), getattr(car, "plate", ""),
    )
    ctx = {"car": car, "related": related, "line_url": line_message_url(inquiry_text)}
    return render(request, "car_detail.html", ctx)


def book_car(request, slug):
    """เดโม: จองรถออนไลน์ — โอนมัดจำผ่าน PromptPay QR แล้วแนบสลิป
    เมื่อจองสำเร็จจะตั้งรถเป็น 'จองแล้ว' ทันที (กันคนอื่นจองซ้ำ)
    """
    car = get_object_or_404(Vehicle.objects.filter(_visible(request)), slug=slug)
    s = SiteSetting.get()
    available = car.status == "available"

    if request.method == "POST":
        if not available:
            messages.error(request, "ขออภัย รถคันนี้เพิ่งถูกจอง/ขายไปแล้ว 🙏")
            return redirect("car_detail", slug=slug)
        form = BookingForm(request.POST, request.FILES)
        if form.is_valid():
            booking = form.save(commit=False)
            booking.vehicle = car
            booking.deposit_amount = s.deposit_amount
            booking.save()
            # กันจองซ้ำ: ตั้งรถเป็น "จองแล้ว" ทันที
            car.status = "reserved"
            car.save(update_fields=["status"])
            # TODO (ของจริง): แจ้งเตือนเซลผ่าน LINE + ตรวจสลิปอัตโนมัติ (cars/line.py)
            return redirect(reverse("book_car", args=[slug]) + f"?ok={booking.pk}")
    else:
        form = BookingForm()

    ctx = {
        "car": car,
        "form": form,
        "available": available,
        "deposit": s.deposit_amount,
        "promptpay_id": s.promptpay_id,
        "pp_payload": promptpay_payload(s.promptpay_id, s.deposit_amount),
        "ok": request.GET.get("ok"),
    }
    return render(request, "book.html", ctx)


def compare(request):
    slugs = [s for s in request.GET.getlist("car") if s][:3]
    cars = list(Vehicle.objects.filter(_visible(request), slug__in=slugs).select_related("brand", "car_type"))
    return render(request, "compare.html", {"cars": cars})


def brand_list(request):
    return render(request, "brand_list.html", {"brands": Brand.objects.all()})


def car_type_list(request):
    return render(request, "car_type_list.html", {"car_types": CarType.objects.all()})


def promotion_list(request):
    return render(
        request,
        "promotion.html",
        {"promotions": Promotion.objects.filter(active=True)},
    )


def _reviews_ranked():
    # เฉพาะรีวิวที่มีข้อความ + ดี (≥4★) → รีวิวที่มีรูปขึ้นก่อน (พอเพิ่มรูปทีหลังจะเด้งขึ้นบน) → ใหม่ก่อน → ดาวสูง
    return (
        Review.objects.filter(active=True, rating__gte=4)
        .exclude(content="")
        .annotate(when=Coalesce("reviewed_at", "created_at"), n_photos=Count("photos"))
        .prefetch_related("photos")
        .order_by("-n_photos", "-when", "-rating")
    )


def reviews(request):
    from .models import BranchPhoto
    return render(
        request,
        "reviews.html",
        {
            "reviews": _reviews_ranked(),
            "branches_google": Branch.objects.filter(google_rating__isnull=False),
            "branch_photos": BranchPhoto.objects.select_related("branch")[:16],
        },
    )


def about(request):
    from .models import Video
    return render(
        request,
        "about.html",
        {
            "about_text": SiteSetting.get().about_text,
            "yt_videos": Video.objects.filter(active=True, source="youtube")[:8],
            "tt_videos": Video.objects.filter(active=True, source="tiktok")[:30],
        },
    )


def gmaps_reviews(request):
    """หน้าทดลอง: ฝัง Places UI Kit (Google เรนเดอร์รีวิว+รูปเอง)"""
    from django.conf import settings
    return render(
        request,
        "gmaps_reviews.html",
        {
            "google_branches": Branch.objects.exclude(google_place_id=""),
            "gmaps_key": settings.GOOGLE_MAPS_API_KEY,
        },
    )


def faq(request):
    faqs = FAQ.objects.filter(active=True)
    return render(request, "faq.html", {"faqs": faqs})


def contact(request):
    if request.method == "POST":
        _save_lead(request, source="contact")
        messages.success(request, "ส่งข้อมูลแล้ว ทีมงานจะติดต่อกลับโดยเร็วครับ")
        return redirect("contact")
    return render(request, "contact.html", {})


def lead_submit(request):
    """รับฟอร์มขอราคาจากหน้ารถ/โปรโมชัน"""
    if request.method == "POST":
        _save_lead(request, source=request.POST.get("source_page", "quote"))
        messages.success(request, "ขอราคาเรียบร้อย ทีมขายจะติดต่อกลับครับ")
    return redirect(request.META.get("HTTP_REFERER", "home"))


def _save_lead(request, source=""):
    vehicle = None
    slug = request.POST.get("vehicle")
    if slug:
        vehicle = Vehicle.objects.filter(slug=slug).first()
    Lead.objects.create(
        name=request.POST.get("name", "").strip(),
        phone=request.POST.get("phone", "").strip(),
        email=request.POST.get("email", "").strip(),
        message=request.POST.get("message", "").strip(),
        source_page=source,
        vehicle=vehicle,
    )
    # TODO เฟสถัดไป: push เข้า LINE กลุ่มเซล (cars/line.py)


@require_POST
def chat(request):
    """AI ผู้ช่วยขาย — รับข้อความ ตอบโดยอิงสต็อกรถจริง (Gemini)"""
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"reply": "ขออภัยค่ะ ส่งข้อความไม่ถูกต้อง 🙏"}, status=400)

    message = (body.get("message") or "").strip()[:500]
    history = body.get("history") or []
    if not message:
        return JsonResponse({"reply": "พิมพ์คำถามได้เลยค่ะ เช่น 'มี Honda Civic ไหม' 🙂"})

    # กันยิงรัว: จำกัด 15 ข้อความ/นาที ต่อ session
    now = time.time()
    hits = [t for t in request.session.get("ai_hits", []) if now - t < 60]
    if len(hits) >= 15:
        return JsonResponse({"reply": "สอบถามถี่ไปนิดนะคะ 🙏 พักสักครู่แล้วลองใหม่ หรือทักไลน์ @oxletauto ได้เลยค่ะ"})
    hits.append(now)
    request.session["ai_hits"] = hits

    return JsonResponse({"reply": chat_reply(message, history)})


# ============================================================
#  จัดการรถจากหน้าเว็บ (โหมดแอดมิน) — เห็น/ใช้ได้เฉพาะ staff
# ============================================================

@staff_member_required(login_url="login")
def car_add(request):
    if request.method == "POST":
        form = VehicleForm(request.POST)
        if form.is_valid():
            car = form.save()
            files = request.FILES.getlist("images")
            for i, f in enumerate(files):
                VehicleImage.objects.create(vehicle=car, image=f, is_cover=(i == 0))
            messages.success(request, "เพิ่มรถแล้ว ✓ (เพิ่ม/จัดการรูปต่อได้ด้านล่าง)")
            return redirect("car_edit", slug=car.slug)
    else:
        form = VehicleForm()
    return render(request, "manage/car_form.html", {"form": form, "mode": "add"})


@staff_member_required(login_url="login")
def car_edit(request, slug):
    car = get_object_or_404(Vehicle, slug=slug)
    if request.method == "POST":
        form = VehicleForm(request.POST, instance=car)
        if form.is_valid():
            form.save()
            messages.success(request, "บันทึกการแก้ไขแล้ว ✓")
            return redirect("car_edit", slug=car.slug)
    else:
        form = VehicleForm(instance=car)
    return render(request, "manage/car_form.html", {"form": form, "car": car, "mode": "edit"})


@staff_member_required(login_url="login")
@require_POST
def car_delete(request, slug):
    """soft delete — ย้ายลงถังขยะ (กู้คืนได้ 30 วัน)"""
    car = get_object_or_404(Vehicle, slug=slug, deleted_at__isnull=True)
    car.deleted_at = timezone.now()
    car.save(update_fields=["deleted_at"])
    messages.success(request, f"ย้าย {car.title} ลงถังขยะแล้ว 🗑️ — กู้คืนได้ภายใน 30 วัน")
    return redirect("all_cars")


@staff_member_required(login_url="login")
def car_trash(request):
    """ถังขยะ — รถที่ถูกลบ (ยังกู้คืนได้)"""
    cars = (Vehicle.objects.filter(deleted_at__isnull=False)
            .select_related("brand").order_by("-deleted_at"))
    return render(request, "manage/trash.html", {"cars": cars})


@staff_member_required(login_url="login")
@require_POST
def car_restore(request, slug):
    car = get_object_or_404(Vehicle, slug=slug, deleted_at__isnull=False)
    car.deleted_at = None
    car.save(update_fields=["deleted_at"])
    messages.success(request, f"กู้คืน {car.title} แล้ว ✓")
    return redirect("car_trash")


@staff_member_required(login_url="login")
@require_POST
def car_purge(request, slug):
    """ลบถาวรทันที (ไม่รอ 30 วัน)"""
    car = get_object_or_404(Vehicle, slug=slug, deleted_at__isnull=False)
    title = car.title
    car.delete()
    messages.success(request, f"ลบ {title} ถาวรแล้ว ✓")
    return redirect("car_trash")


@staff_member_required(login_url="login")
def car_sold(request):
    """คลังรถที่ขายแล้ว (staff เท่านั้น) — ลูกค้าไม่เห็น"""
    cars = (Vehicle.objects.filter(status="sold", deleted_at__isnull=True)
            .select_related("brand").order_by("-updated_at"))
    return render(request, "manage/sold.html", {"cars": cars})


@staff_member_required(login_url="login")
@require_POST
def car_relist(request, slug):
    """ดึงรถขายแล้วกลับมาขายใหม่ (status -> available)"""
    car = get_object_or_404(Vehicle, slug=slug, deleted_at__isnull=True)
    car.status = "available"
    car.save(update_fields=["status"])
    messages.success(request, f"ดึง {car.title} กลับมาขายแล้ว ✓")
    return redirect("car_sold")


@staff_member_required(login_url="login")
@require_POST
def car_image_upload(request, slug):
    car = get_object_or_404(Vehicle, slug=slug)
    files = request.FILES.getlist("images")
    has_cover = car.images.filter(is_cover=True).exists()
    for i, f in enumerate(files):
        VehicleImage.objects.create(vehicle=car, image=f, is_cover=(not has_cover and i == 0))
    messages.success(request, f"อัปโหลด {len(files)} รูปแล้ว ✓")
    return redirect("car_edit", slug=slug)


@staff_member_required(login_url="login")
@require_POST
def car_image_delete(request, pk):
    img = get_object_or_404(VehicleImage, pk=pk)
    slug = img.vehicle.slug
    img.delete()
    return redirect("car_edit", slug=slug)


@staff_member_required(login_url="login")
@require_POST
def car_image_cover(request, pk):
    img = get_object_or_404(VehicleImage, pk=pk)
    img.vehicle.images.update(is_cover=False)
    img.is_cover = True
    img.save()
    return redirect("car_edit", slug=img.vehicle.slug)


# ---------- โปรโมชัน (front-end CRUD) ----------

@staff_member_required(login_url="login")
def promo_add(request):
    if request.method == "POST":
        form = PromotionForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "เพิ่มโปรโมชันแล้ว ✓")
            return redirect("promotion")
    else:
        form = PromotionForm()
    return render(request, "manage/object_form.html", {
        "form": form, "title": "➕ เพิ่มโปรโมชัน", "cancel_url": reverse("promotion")})


@staff_member_required(login_url="login")
def promo_edit(request, pk):
    promo = get_object_or_404(Promotion, pk=pk)
    if request.method == "POST":
        form = PromotionForm(request.POST, request.FILES, instance=promo)
        if form.is_valid():
            form.save()
            messages.success(request, "บันทึกโปรโมชันแล้ว ✓")
            return redirect("promotion")
    else:
        form = PromotionForm(instance=promo)
    return render(request, "manage/object_form.html", {
        "form": form, "title": "✏️ แก้ไขโปรโมชัน", "cancel_url": reverse("promotion"),
        "delete_url": reverse("promo_delete", args=[promo.pk])})


@staff_member_required(login_url="login")
@require_POST
def promo_delete(request, pk):
    get_object_or_404(Promotion, pk=pk).delete()
    messages.success(request, "ลบโปรโมชันแล้ว ✓")
    return redirect("promotion")


# ---------- สาขา / ที่อยู่ (front-end CRUD) ----------

@staff_member_required(login_url="login")
def branch_add(request):
    if request.method == "POST":
        form = BranchForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "เพิ่มสาขาแล้ว ✓")
            return redirect("contact")
    else:
        form = BranchForm()
    return render(request, "manage/object_form.html", {
        "form": form, "title": "➕ เพิ่มสาขา", "cancel_url": reverse("contact")})


@staff_member_required(login_url="login")
def branch_edit(request, pk):
    branch = get_object_or_404(Branch, pk=pk)
    if request.method == "POST":
        form = BranchForm(request.POST, instance=branch)
        if form.is_valid():
            form.save()
            messages.success(request, "บันทึกสาขาแล้ว ✓")
            return redirect("contact")
    else:
        form = BranchForm(instance=branch)
    return render(request, "manage/object_form.html", {
        "form": form, "title": "✏️ แก้ไขสาขา", "cancel_url": reverse("contact"),
        "delete_url": reverse("branch_delete", args=[branch.pk])})


@staff_member_required(login_url="login")
@require_POST
def branch_delete(request, pk):
    get_object_or_404(Branch, pk=pk).delete()
    messages.success(request, "ลบสาขาแล้ว ✓")
    return redirect("contact")


# ---------- FAQ (front-end CRUD) ----------

@staff_member_required(login_url="login")
def faq_add(request):
    if request.method == "POST":
        form = FAQForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "เพิ่มคำถามแล้ว ✓")
            return redirect("faq")
    else:
        form = FAQForm()
    return render(request, "manage/object_form.html", {
        "form": form, "title": "➕ เพิ่มคำถาม-คำตอบ", "cancel_url": reverse("faq")})


@staff_member_required(login_url="login")
def faq_edit(request, pk):
    obj = get_object_or_404(FAQ, pk=pk)
    if request.method == "POST":
        form = FAQForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "บันทึกคำถามแล้ว ✓")
            return redirect("faq")
    else:
        form = FAQForm(instance=obj)
    return render(request, "manage/object_form.html", {
        "form": form, "title": "✏️ แก้ไขคำถาม-คำตอบ", "cancel_url": reverse("faq"),
        "delete_url": reverse("faq_delete", args=[obj.pk])})


@staff_member_required(login_url="login")
@require_POST
def faq_delete(request, pk):
    get_object_or_404(FAQ, pk=pk).delete()
    messages.success(request, "ลบคำถามแล้ว ✓")
    return redirect("faq")


# ---------- ตั้งค่าเว็บ (ชื่อ/เบอร์/LINE/เวลา/เนื้อหา About) ----------

@staff_member_required(login_url="login")
def site_settings(request):
    s = SiteSetting.get()
    if request.method == "POST":
        form = SiteSettingForm(request.POST, instance=s)
        if form.is_valid():
            form.save()
            messages.success(request, "บันทึกข้อมูลร้านแล้ว ✓")
            return redirect("site_settings")
    else:
        form = SiteSettingForm(instance=s)
    return render(request, "manage/object_form.html", {
        "form": form, "title": "⚙️ ตั้งค่าเว็บ / ข้อมูลร้าน", "cancel_url": reverse("home")})


# ---------- ช่องทางติดต่อ (front-end CRUD) ----------

@staff_member_required(login_url="login")
def social_add(request):
    if request.method == "POST":
        form = SocialLinkForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "เพิ่มช่องทางแล้ว ✓")
            return redirect("contact")
    else:
        form = SocialLinkForm()
    return render(request, "manage/object_form.html", {
        "form": form, "title": "➕ เพิ่มช่องทางติดต่อ", "cancel_url": reverse("contact")})


@staff_member_required(login_url="login")
def social_edit(request, pk):
    obj = get_object_or_404(SocialLink, pk=pk)
    if request.method == "POST":
        form = SocialLinkForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "บันทึกช่องทางแล้ว ✓")
            return redirect("contact")
    else:
        form = SocialLinkForm(instance=obj)
    return render(request, "manage/object_form.html", {
        "form": form, "title": "✏️ แก้ไขช่องทางติดต่อ", "cancel_url": reverse("contact"),
        "delete_url": reverse("social_delete", args=[obj.pk])})


@staff_member_required(login_url="login")
@require_POST
def social_delete(request, pk):
    get_object_or_404(SocialLink, pk=pk).delete()
    messages.success(request, "ลบช่องทางแล้ว ✓")
    return redirect("contact")


# ============================================================
#  ป้ายทะเบียนขาย (เลขสวย/เลขมงคล)
# ============================================================

def plate_list(request):
    """หน้ารวมป้ายทะเบียน (สาธารณะ) + ตัวกรอง: ประเภท/ราคา/ผลรวม/ค้นหา"""
    qs = LicensePlate.objects.all()
    if not request.user.is_staff:
        qs = qs.exclude(status="sold")

    plate_type = request.GET.get("type")
    price_range = request.GET.get("price")
    keyword = request.GET.get("q")
    sort = request.GET.get("sort")
    own_only = request.GET.get("own") == "1"

    if own_only:
        qs = qs.filter(is_own=True)
    if plate_type in dict(LicensePlate.TYPE_CHOICES):
        qs = qs.filter(plate_type=plate_type)
    if price_range:
        for key, _label, lo, hi in constants.PLATE_PRICE_RANGES:
            if key == price_range:
                qs = qs.filter(price__gte=lo, price__lt=hi)
                break
    if keyword:
        qs = qs.filter(
            Q(prefix__icontains=keyword)
            | Q(number__icontains=keyword)
            | Q(province__icontains=keyword)
        )

    plates = list(qs)

    # ผลรวมเลข (digit_sum เป็น property จึงกรอง/เรียงใน Python)
    sum_val = request.GET.get("sum")
    if sum_val and sum_val.isdigit():
        plates = [p for p in plates if p.digit_sum == int(sum_val)]

    # ป้ายของร้านมาก่อนเสมอ ไม่ว่าจะเรียงแบบไหน (not p.is_own -> False มาก่อน True)
    if sort == "price":
        plates.sort(key=lambda p: (not p.is_own, p.price))
    elif sort == "-price":
        plates.sort(key=lambda p: (not p.is_own, -p.price))
    elif sort == "sum":
        plates.sort(key=lambda p: (not p.is_own, p.digit_sum))

    # ตัวเลือกผลรวมที่มีของจริง (ให้ dropdown โชว์เฉพาะที่มี)
    base = LicensePlate.objects.all()
    if not request.user.is_staff:
        base = base.exclude(status="sold")
    available_sums = sorted({p.digit_sum for p in base})

    # แยกป้ายของร้านออกมาโชว์เป็นบล็อกเด่นด้านบน ที่เหลือต่อท้าย
    own_plates = [p for p in plates if p.is_own]
    other_plates = [p for p in plates if not p.is_own]

    ctx = {
        "plates": plates,
        "own_plates": own_plates,
        "other_plates": other_plates,
        "total": len(plates),
        "own_total": base.filter(is_own=True).count(),
        "plate_types": LicensePlate.TYPE_CHOICES,
        "price_ranges": constants.PLATE_PRICE_RANGES,
        "available_sums": available_sums,
        "current": request.GET,
    }
    return render(request, "plates.html", ctx)


@staff_member_required(login_url="login")
def plate_add(request):
    if request.method == "POST":
        form = LicensePlateForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "เพิ่มป้ายทะเบียนแล้ว ✓")
            return redirect("plate_list")
    else:
        form = LicensePlateForm()
    return render(request, "manage/object_form.html", {
        "form": form, "title": "➕ เพิ่มป้ายทะเบียน", "cancel_url": reverse("plate_list")})


@staff_member_required(login_url="login")
def plate_edit(request, pk):
    obj = get_object_or_404(LicensePlate, pk=pk)
    if request.method == "POST":
        form = LicensePlateForm(request.POST, request.FILES, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "บันทึกป้ายทะเบียนแล้ว ✓")
            return redirect("plate_list")
    else:
        form = LicensePlateForm(instance=obj)
    return render(request, "manage/object_form.html", {
        "form": form, "title": "✏️ แก้ไขป้ายทะเบียน", "cancel_url": reverse("plate_list"),
        "delete_url": reverse("plate_delete", args=[obj.pk])})


@staff_member_required(login_url="login")
@require_POST
def plate_delete(request, pk):
    get_object_or_404(LicensePlate, pk=pk).delete()
    messages.success(request, "ลบป้ายทะเบียนแล้ว ✓")
    return redirect("plate_list")
