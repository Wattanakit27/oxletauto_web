# DEPLOY — ขึ้น HostAtom VPS (standalone)

เว็บ `oxlet_web` แบบแยกเดี่ยว: **Django + Supabase (DB) + Cloudflare R2 (รูป) + Caddy (HTTPS)**

---

## 0. ของที่ต้องเตรียม
- [ ] **HostAtom Cloud VPS** (เลือก *VPS* ไม่ใช่ shared hosting) — Ubuntu 22.04, RAM ≥1GB
- [ ] **Supabase** project (เอา connection string ตัว *pooler*)
- [ ] **Cloudflare R2** bucket + API token (Access Key / Secret)
- [ ] โดเมน **track.oxletauto.co.th** (HostAtom) ชี้ A record → IP ของ VPS

---

## 1. เตรียม VPS
```bash
ssh root@<VPS_IP>
apt update && apt upgrade -y
curl -fsSL https://get.docker.com | sh        # ติดตั้ง Docker + compose
git clone <repo ของ oxlet_web> /opt/oxlet && cd /opt/oxlet
```

## 2. ตั้งค่า .env (โปรดักชัน)
```bash
cp .env.example .env && nano .env
```
ใส่ค่า:
```
SECRET_KEY=<สุ่มใหม่ยาวๆ>
DEBUG=False
ALLOWED_HOSTS=track.oxletauto.co.th
SITE_URL=https://track.oxletauto.co.th
CORS_ALLOWED_ORIGINS=https://track.oxletauto.co.th

# Supabase (pooler)
DB_HOST=aws-0-ap-southeast-1.pooler.supabase.com
DB_NAME=postgres
DB_USER=postgres.<ref>
DB_PASSWORD=<supabase password>
DB_PORT=6543

# Cloudflare R2
R2_BUCKET=oxlet-media
R2_ACCESS_KEY_ID=<key>
R2_SECRET_ACCESS_KEY=<secret>
R2_ENDPOINT=https://<acct>.r2.cloudflarestorage.com
R2_PUBLIC_DOMAIN=cdn.oxletauto.co.th
```
> สุ่ม SECRET_KEY: `python -c "import secrets;print(secrets.token_urlsafe(50))"`

## 3. แก้โดเมนใน Caddyfile
แก้ `track.oxletauto.co.th` ให้ตรงกับโดเมนจริง (ไฟล์ `Caddyfile`)

## 4. รัน
```bash
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_demo       # ข้อมูลตัวอย่าง (ข้ามได้)
docker compose exec web python manage.py import_media    # อัปโลโก้+รูปขึ้น R2 อัตโนมัติ
docker compose exec web python manage.py createsuperuser
```
Caddy จะออกใบ HTTPS ให้เองภายในไม่กี่วิ → เปิด **https://track.oxletauto.co.th**

---

## 5. ตรวจหลังขึ้น
- [ ] เปิดเว็บได้ + เป็น https (กุญแจเขียว)
- [ ] รูปรถโหลดจาก R2 (ดู URL รูปต้องเป็น `cdn.oxletauto.co.th/...`)
- [ ] `/admin/` เข้าได้ เพิ่มรถได้
- [ ] ส่งฟอร์มขอราคา → มี Lead ใน admin

## 6. อัปเดตเว็บรอบหน้า
```bash
cd /opt/oxlet && git pull
docker compose up -d --build
docker compose exec web python manage.py migrate
```

---

## หมายเหตุ
- **รูปเก่า 253MB** ใน `oxlet_images/` → `import_media` จะดึงเข้า R2 ให้เอง (อ่านจากโฟลเดอร์ข้างโปรเจกต์)
- **DB กับ VPS ควร region เดียวกัน** — ตั้ง Supabase ที่ Singapore (`ap-southeast-1`) ให้ใกล้ HostAtom (ไทย)
- ยังไม่ต่อ R2 ก็รันได้ (เก็บรูปใน volume `media`) แต่ production แนะนำ R2
