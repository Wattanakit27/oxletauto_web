"""AI ผู้ช่วยขาย (Google Gemini)

หัวใจ: ตอบโดยอิง "ข้อมูลรถจริง" จากสต็อกเท่านั้น —
ดึงรถที่เกี่ยวกับคำถามจาก DB ส่งเป็นบริบทให้ Gemini + สั่งห้ามแต่งรถที่ไม่มี
ไม่ต้องลงไลบรารีเพิ่ม (เรียก REST API ผ่าน urllib ของ Python)
"""
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.db.models import Q

from .models import Brand, Vehicle

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

SYSTEM_PROMPT = """คุณคือ "น้องอ๊อกเล็ต" ผู้ช่วยขายของ Oxlet Auto โชว์รูมรถมือสองพร้อมศูนย์บริการ
ตอบเป็นภาษาไทย สุภาพ เป็นกันเอง กระชับ (ปกติไม่เกิน 6 บรรทัด) ใส่อีโมจิได้นิดหน่อย

กฎเหล็ก (ห้ามฝ่าฝืนเด็ดขาด):
1. ใช้เฉพาะ "ข้อมูลรถจริง" ที่ระบบแนบมาในแต่ละข้อความเท่านั้น — ห้ามแต่ง/เดา รุ่น ราคา สเปก สี ปี ประเภท หรือจำนวนรถ ที่ไม่มีในข้อมูล. ระบุประเภทรถ (เช่น PPV, SUV, เก๋ง, กระบะ, MPV) ตาม "ประเภท" ที่ระบุในข้อมูลเท่านั้น ห้ามเรียกผิดประเภท (เช่น PPV ห้ามเรียกว่า SUV)
2. ถ้าลูกค้าถามถึงรุ่นที่ไม่มีในรายการที่แนบมา ให้บอกตรงๆ ว่าตอนนี้ยังไม่มีคันนั้นในสต็อก แล้วเสนอรถที่ "มีจริง" ที่ใกล้เคียง หรือชวนทักไลน์ ห้ามสมมติว่ามี
3. เรื่องค่างวด/เงินดาวน์: อ้างอิงราคา ค่างวดเริ่มต้น และดอกเบี้ยที่แนบมาเท่านั้น ถ้าต้องประมาณตัวเลข ให้บอกชัดว่าเป็น "ประมาณการ" และแนะนำให้ยืนยันยอดจริงกับเซลล์ทางไลน์ (ยอดจริงขึ้นกับการอนุมัติไฟแนนซ์) — ห้ามฟันธงตัวเลขเป๊ะ
4. ตอบเฉพาะเรื่องรถ/บริการ/สาขาของร้าน ถ้าถูกถามนอกเรื่อง ให้ปฏิเสธอย่างสุภาพแล้วชวนกลับมาเรื่องรถ
5. ถ้าแนะนำรถคันไหน ให้แนบลิงก์หน้ารถ (ฟิลด์ url) มาด้วย และถ้าลูกค้าสนใจ ให้ชวนกดปุ่ม LINE หรือโทรหาร้าน"""


# ---------- ดึงข้อมูลรถจริง ----------

def _available():
    return (Vehicle.objects.filter(deleted_at__isnull=True)
            .exclude(status="sold").select_related("brand", "car_type", "branch"))


# คำที่ลูกค้าใช้ -> คำที่ไปเทียบกับชื่อ car_type ใน DB (icontains)
TYPE_KEYWORDS = {
    "กระบะ": "กระบะ", "ปิคอัพ": "กระบะ", "ปิกอัพ": "กระบะ", "pickup": "กระบะ",
    "เก๋ง": "เก๋ง", "ซีดาน": "เก๋ง", "sedan": "เก๋ง",
    "แฮทช์แบค": "แฮทช์", "แฮทช์": "แฮทช์", "hatchback": "แฮทช์",
    "suv": "suv", "เอสยูวี": "suv", "อเนกประสงค์": "suv",
    "ppv": "ppv",
    "mpv": "mpv", "ครอบครัว": "mpv", "7 ที่นั่ง": "mpv", "เจ็ดที่นั่ง": "mpv",
    "ตู้": "ตู้", "van": "ตู้",
    "มินิแวน": "มินิแวน",
    "เปิดประทุน": "เปิดประทุน", "convertible": "เปิดประทุน",
    "ซูเปอร์คาร์": "ซูเปอร์", "supercar": "ซูเปอร์",
}


def find_relevant_cars(query, limit=8):
    """หารถในสต็อกที่เกี่ยวกับคำถาม (ยี่ห้อ/ประเภท/คีย์เวิร์ดรุ่น) — คืน list อาจว่างถ้าไม่มีตรง"""
    qs = _available()
    q = (query or "").lower()

    brand_hits = [b for b in Brand.objects.all() if b.name and b.name.lower() in q]
    if brand_hits:
        qs = qs.filter(brand__in=brand_hits)

    # ประเภทรถ (car_type) เช่น กระบะ / SUV / เก๋ง / ครอบครัว
    substrs = {sub for word, sub in TYPE_KEYWORDS.items() if word in q}
    if substrs:
        type_q = Q()
        for sub in substrs:
            type_q |= Q(car_type__name__icontains=sub)
        qs = qs.filter(type_q)

    # คีย์เวิร์ดรุ่น (คำยาว >= 2 ตัว ที่ไม่ใช่ยี่ห้อ)
    brand_names = {b.name.lower() for b in Brand.objects.all()}
    tokens = [w for w in q.replace(",", " ").split() if len(w) >= 2 and w not in brand_names]
    model_q = Q()
    for w in tokens[:6]:
        model_q |= Q(model__icontains=w) | Q(submodel__icontains=w)
    if model_q:
        narrowed = qs.filter(model_q)
        if narrowed.exists():
            qs = narrowed

    # คำถามเชิงราคา/ความหรู — เรียงตามราคาให้ถูกต้อง
    if any(k in q for k in ("แพง", "สูงสุด", "ราคาสูง", "หรู", "ดีที่สุด", "เรือธง", "topสุด")):
        qs = qs.order_by("-price")
    elif any(k in q for k in ("ถูก", "ประหยัด", "ต่ำสุด", "งบน้อย", "ราคาต่ำ", "เริ่มต้น")):
        qs = qs.filter(price__gt=0).order_by("price")

    return list(qs[:limit])


def inventory_snapshot():
    """สรุปสต็อกแบบกว้างๆ ใช้ให้บอตตอบ 'เรามีอะไรบ้าง' ได้แม้ไม่เจอรุ่นที่ถาม"""
    qs = _available()
    total = qs.count()
    brands = list(
        qs.values_list("brand__name", flat=True).distinct().order_by("brand__name")
    )
    prices = qs.values_list("price", flat=True)
    prices = [p for p in prices if p]
    low = f"{min(prices):,}" if prices else "-"
    high = f"{max(prices):,}" if prices else "-"
    return total, [b for b in brands if b], low, high


def build_context(query):
    """ประกอบบริบทข้อมูลจริง (ร้าน + สต็อก + รถที่เกี่ยว) ส่งให้โมเดล"""
    total, brands, low, high = inventory_snapshot()
    lines = [
        "[ข้อมูลร้าน]",
        "ชื่อ: Oxlet Auto (อ๊อกเล็ตร์ ออโต) — โชว์รูมรถมือสอง พร้อมศูนย์บริการ",
        "โทร: 097-821-8888 · LINE: @oxletauto · เวลาทำการ: 08.00 - 18.30",
        "บริการ: รับประกันเครื่อง+เกียร์ 1 ปี, ตรวจสภาพ 150+ จุด, คืนเงินใน 7 วันถ้าไม่พอใจ, จัดไฟแนนซ์ได้ทุกธนาคาร, ดอกเบี้ยเริ่มต้น 2.79%, Car Spa ฟรี",
        "",
        "[สรุปสต็อกตอนนี้]",
        f"รถพร้อมขายทั้งหมด {total} คัน",
        f"ยี่ห้อที่มี: {', '.join(brands) if brands else '-'}",
        f"ช่วงราคา: {low} - {high} บาท",
    ]
    # รถแพงสุด/ถูกสุด — ให้บอตตอบคำถามเชิงราคาได้แม้คำถามไม่ระบุรุ่น
    top = _available().order_by("-price").first()
    cheap = _available().filter(price__gt=0).order_by("price").first()
    if top:
        lines.append(f"รถราคาสูงสุดตอนนี้: {top.title} — {top.price:,} บาท ({settings.SITE_URL}{top.get_absolute_url()})")
    if cheap:
        lines.append(f"รถราคาถูกสุดตอนนี้: {cheap.title} — {cheap.price:,} บาท ({settings.SITE_URL}{cheap.get_absolute_url()})")
    lines += ["", "[รถที่เกี่ยวข้องกับคำถามนี้]"]

    cars = find_relevant_cars(query)
    if not cars:
        lines.append("(ไม่พบรถที่ตรงกับคำถามในสต็อก — ห้ามสมมติว่ามี ให้เสนอยี่ห้อ/รุ่นที่มีจริงด้านบนแทน)")
    else:
        for i, c in enumerate(cars, 1):
            specs = " · ".join(
                p for p in [
                    f"ประเภท {c.car_type.name}" if c.car_type else "",
                    f"ปี {c.year}",
                    f"{c.mileage:,} กม." if c.mileage else "",
                    c.get_transmission_display(),
                    c.get_drivetrain_display(),
                    c.get_fuel_display(),
                    c.color_exterior,
                ] if p
            )
            inst = f"ผ่อนเริ่ม {c.installment_min:,}/เดือน" if c.installment_min else "สอบถามค่างวด"
            branch = c.branch.name if c.branch else "-"
            lines.append(
                f"{i}. {c.title} | ราคา {c.price:,} บาท | {inst} ดอกเบี้ย {c.interest_rate}% "
                f"| {specs} | สาขา {branch} | url: {settings.SITE_URL}{c.get_absolute_url()}"
            )
    return "\n".join(lines)


# ---------- เรียก Gemini ----------

def chat_reply(message, history=None):
    """ส่งคำถาม + บริบทรถจริง ให้ Gemini แล้วคืนข้อความตอบ"""
    key = settings.GEMINI_API_KEY
    if not key:
        return ("ตอนนี้ผู้ช่วย AI ยังไม่เปิดใช้งานค่ะ 🙏 สอบถามรถได้ที่ปุ่ม LINE @oxletauto "
                "หรือโทร 097-821-8888 ได้เลยนะคะ")

    context = build_context(message)
    contents = []
    for h in (history or [])[-6:]:
        role = "user" if h.get("role") == "user" else "model"
        text = (h.get("text") or "")[:1200]
        if text:
            contents.append({"role": role, "parts": [{"text": text}]})
    contents.append({
        "role": "user",
        "parts": [{"text": f"{context}\n\n[คำถามลูกค้า]\n{message}"}],
    })

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.3,
            "topP": 0.9,
            "maxOutputTokens": 1024,
            # Flash เป็นโมเดล "thinking" — โทเคนคิดกินเพดานจนคำตอบโดนตัด
            # บอตขายไม่ต้องคิดลึก เลยปิด thinking (เร็ว/ถูก/คำตอบเต็ม)
            # NOTE: ถ้าเปลี่ยนไปใช้ -pro อาจต้องลบบรรทัด thinkingConfig นี้ออก
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    url = ENDPOINT.format(model=settings.GEMINI_MODEL, key=key)
    req = Request(url, data=json.dumps(payload).encode("utf-8"),
                  headers={"Content-Type": "application/json"})

    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        print("[Gemini HTTPError]", e.code, detail)
        return "ขออภัยค่ะ ระบบ AI ขัดข้องชั่วคราว 🙏 ลองใหม่อีกครั้ง หรือทักไลน์ @oxletauto ได้เลยนะคะ"
    except (URLError, TimeoutError) as e:
        print("[Gemini URLError]", e)
        return "ขออภัยค่ะ ตอนนี้เชื่อมต่อ AI ไม่ได้ 🙏 ทักไลน์ @oxletauto หรือโทร 097-821-8888 ได้เลยค่ะ"

    # แกะคำตอบ (กันกรณีโดน safety block / โครงสร้างแปลก)
    try:
        cand = data["candidates"][0]
        parts = cand.get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts).strip()
        if text:
            return text
    except (KeyError, IndexError):
        pass
    return "ขออภัยค่ะ ตอบคำถามนี้ไม่ได้ 🙏 รบกวนถามใหม่ หรือทักไลน์ @oxletauto เพื่อสอบถามรายละเอียดได้เลยค่ะ"
