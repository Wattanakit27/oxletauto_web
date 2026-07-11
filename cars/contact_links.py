"""ตัวช่วยสร้างลิงก์ติดต่อ — รวมไว้ที่เดียว ใช้ซ้ำได้ทุกที่"""
from urllib.parse import quote

# LINE Official Account id (ขึ้นต้นด้วย @)
LINE_OA = "@oxletauto"

# ข้อความตั้งต้นเวลากดทักจากหน้าทั่วไป (ไม่เจาะจงคัน)
LINE_DEFAULT_MSG = "สนใจออกรถครับ/ค่ะ รบกวนขอรายละเอียดเพิ่มเติม 🙏"


def line_message_url(text=LINE_DEFAULT_MSG, oa_id=LINE_OA):
    """ลิงก์เปิดแชต LINE OA พร้อมพิมพ์ข้อความรอไว้ในช่อง (ลูกค้าแค่กดส่ง)

    รูปแบบ: https://line.me/R/oaMessage/<oa_id>/?<ข้อความ encode>
    """
    return f"https://line.me/R/oaMessage/{quote(oa_id)}/?{quote(text)}"


# Facebook Page / Instagram สำหรับ "เปิดแชต" — FB/IG prefill ข้อความผ่านลิงก์ไม่ได้
# (Meta ปิดกันสแปม) เปิดแชตได้อย่างเดียว เลยใช้คู่กับปุ่มคัดลอกรายละเอียดรถ
FB_PAGE = "oxlet.bankao"
IG_USER = "oxletauto"
MESSENGER_URL = f"https://m.me/{FB_PAGE}"
INSTAGRAM_DM_URL = f"https://ig.me/m/{IG_USER}"


def car_inquiry_text(title, url="", price=None, plate=""):
    """ข้อความทักถามรถเฉพาะคัน (plain text) — ใช้ทั้งลิงก์ LINE และปุ่มคัดลอกไปวางใน Messenger/IG"""
    lines = ["สนใจออกรถคันนี้ครับ/ค่ะ 🚗", title]
    if plate:
        lines.append(f"ทะเบียน {plate}")
    if price:
        lines.append(f"ราคา {price:,} บาท")
    if url:
        lines.append(url)
    lines.append("รบกวนติดต่อกลับด้วยครับ/ค่ะ 🙏")
    return "\n".join(lines)


def line_car_inquiry_url(title, url="", price=None, plate=""):
    """ลิงก์ LINE พร้อมข้อความรถ (พิมพ์รอในช่องแชตให้เลย)"""
    return line_message_url(car_inquiry_text(title, url, price, plate))
