from django.db import migrations

FAQS = [
    ("รถทุกคันผ่านการตรวจสภาพไหม?", "ทุกคันตรวจมาตรฐานสถาบันญี่ปุ่นกว่า 150 จุด การันตีโครงสร้างเดิม ไม่ชนหนัก ไม่จมน้ำ"),
    ("จัดไฟแนนซ์ได้ไหม ดอกเบี้ยเท่าไร?", "จัดได้ทุกธนาคาร ดอกเบี้ยเริ่มต้น 2.79% ขึ้นอยู่กับเครดิตและรุ่นรถ"),
    ("มีรับประกันหลังการขายไหม?", "รับประกันเครื่อง+เกียร์ 1 ปี หรือ 20,000 กม. พร้อมศูนย์บริการดูแล"),
    ("ซื้อออนไลน์/ต่างจังหวัดได้ไหม?", "ได้ มีบริการรถสไลด์ส่งทั่วประเทศ และคืนเงินภายใน 7 วันถ้าไม่พอใจ"),
    ("มีกี่สาขา เปิดกี่โมง?", "2 สาขา (ชลบุรี / สมุทรปราการ) เปิด 08.00 - 18.30 ทุกวัน"),
]


def seed(apps, schema_editor):
    FAQ = apps.get_model("cars", "FAQ")
    if not FAQ.objects.exists():
        for i, (q, a) in enumerate(FAQS):
            FAQ.objects.create(question=q, answer=a, order=i)


def unseed(apps, schema_editor):
    apps.get_model("cars", "FAQ").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("cars", "0013_faq_sitesetting_about_text")]
    operations = [migrations.RunPython(seed, unseed)]
