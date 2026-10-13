"""Django settings — Oxlet Auto website (clone)."""
from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(key, default=False):
    return os.getenv(key, str(default)).lower() in ("1", "true", "yes", "on")


SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-key")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
YOUTUBE_CHANNEL_ID = os.getenv("YOUTUBE_CHANNEL_ID", "UCjEjYmV1cjQUBLiZosRUmEw")

# AI ผู้ช่วยขาย (Google Gemini) — ใส่คีย์ใน .env (เว้นว่าง = ปิดบอท ไม่ error)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# gemini-flash-latest = เกาะรุ่น Flash ล่าสุดอัตโนมัติ (ตอนนี้คือ Gemini 3.5 Flash)
# เปลี่ยนเป็น gemini-3.1-pro ได้ถ้าอยากเน้นฉลาดสุด (ช้า/แพงกว่า)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
DEBUG = env_bool("DEBUG", True)
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "*").split(",") if h.strip()]
SITE_URL = os.getenv("SITE_URL", "http://127.0.0.1:8000")

# Secret ยืนยัน webhook sync สต็อกจาก backend (SaleforceOxletauto) — ตั้งให้ตรงกัน 2 ฝั่ง
# ว่าง = ปิดรับ (endpoint /api/stock-update/ จะตอบ 401 จนกว่าจะตั้ง)
STOCK_SYNC_SECRET = os.getenv("STOCK_SYNC_SECRET", "")

# หน้าจองรถออนไลน์ (สแกน QR พร้อมเพย์ มัดจำ) — ปิดไว้ก่อน (ต.ค.69 เจ้าของสั่ง):
# ปุ่มจองเปิดแชท LINE @oxletauto พร้อมพิมพ์ "สนใจรุ่นนี้ มาจากเว็บ Oxlet" รอไว้แทน · ON = กลับไปใช้หน้า QR
ONLINE_BOOKING = env_bool("ONLINE_BOOKING", False)

# ฟอร์ม "ขอราคาพิเศษ / นัดดูรถ" → ส่งต่อเข้าห้องพัก Lead ของ SaleForce (กลุ่ม LINE "ADMIN เก็บ Lead")
# เช่น https://srv1793506.hstgr.cloud/api/showroom/lead · ใช้ STOCK_SYNC_SECRET ตัวเดียวกัน · ว่าง = ไม่ส่ง (เก็บในเว็บนี้อย่างเดียว)
SALEFORCE_LEAD_URL = os.getenv("SALEFORCE_LEAD_URL", "")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "rest_framework",
    "corsheaders",
    "cars",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "cars.context_processors.site_globals",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# DB switch: ตั้ง DB_HOST = Postgres, ไม่งั้น SQLite
if os.getenv("DB_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "oxlet"),
            "USER": os.getenv("DB_USER", "oxlet"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST"),
            "PORT": os.getenv("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Auth: ล็อกอิน/ออกจากระบบ ผ่านหน้าเว็บ (ไม่ใช่หน้า admin) แล้วเด้งกลับหน้าแรก
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

LANGUAGE_CODE = "th"
TIME_ZONE = "Asia/Bangkok"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# เก็บรูป/วิดีโอ: ถ้าตั้งค่า R2 (env) = ใช้ Cloudflare R2, ไม่งั้นเก็บในเครื่อง (dev)
R2_BUCKET = os.getenv("R2_BUCKET")
if R2_BUCKET:
    AWS_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = R2_BUCKET
    AWS_S3_ENDPOINT_URL = os.getenv("R2_ENDPOINT")  # https://<acct>.r2.cloudflarestorage.com
    AWS_S3_CUSTOM_DOMAIN = os.getenv("R2_PUBLIC_DOMAIN")  # cdn.oxletauto... (โดเมนสาธารณะของ bucket)
    AWS_S3_REGION_NAME = "auto"
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = False
    AWS_S3_FILE_OVERWRITE = False
    STORAGES = {
        "default": {"BACKEND": "storages.backends.s3.S3Storage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
    }
else:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CORS: dev เปิดหมด, prod ปิดตาม origin
if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True
else:
    CORS_ALLOWED_ORIGINS = [
        o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()
    ]
    CSRF_TRUSTED_ORIGINS = [SITE_URL]
