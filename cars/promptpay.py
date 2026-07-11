"""สร้าง payload PromptPay QR (มาตรฐาน EMVCo) — ไม่ต้องพึ่งไลบรารี/เว็บนอก
คืนเป็นสตริง แล้วเอาไป render เป็น QR ฝั่งเบราว์เซอร์ (qrcode.js) ได้เลย
"""


def _tlv(tag, value):
    return f"{tag}{len(value):02d}{value}"


def _crc16(data):
    """CRC16-CCITT (0xFFFF, poly 0x1021) — ต่อท้าย payload ตามสเปก"""
    crc = 0xFFFF
    for b in data.encode("ascii"):
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def _account(target):
    """คืน (tag, value) ของบัญชีปลายทาง: 01=เบอร์มือถือ, 02=เลขบัตร ปชช./ผู้เสียภาษี"""
    digits = "".join(c for c in target if c.isdigit())
    if len(digits) >= 13:                       # เลขบัตร ปชช./ผู้เสียภาษี 13 หลัก
        return "02", digits[:13]
    # เบอร์มือถือ -> 66 + 9 หลัก (ตัด 0 นำหน้า) เติม 0 ให้ครบ 13 หลัก
    return "01", ("66" + digits.lstrip("0")).zfill(13)


def promptpay_payload(target, amount=None):
    """สตริง payload ของ QR PromptPay

    target = เบอร์มือถือ หรือ เลขบัตร ปชช./ผู้เสียภาษี ของร้าน
    amount = ยอดเงิน (บาท) — ใส่ = QR ระบุยอด, เว้น = QR เปล่า
    """
    tag, value = _account(target)
    merchant = _tlv("00", "A000000677010111") + _tlv(tag, value)
    p = _tlv("00", "01")
    p += _tlv("01", "12" if amount else "11")   # 12=ระบุยอด(จ่ายครั้งเดียว), 11=เปล่า
    p += _tlv("29", merchant)
    p += _tlv("53", "764")                       # สกุลเงิน THB
    if amount:
        p += _tlv("54", f"{float(amount):.2f}")
    p += _tlv("58", "TH")
    p += "6304" + _crc16(p + "6304")
    return p
