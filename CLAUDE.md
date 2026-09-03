# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Oxlet Auto — a Thai used-car dealership website (a functional clone of oxletauto.co.th). Django 5, single app, Bootstrap 5 templates served server-side (no JS build step). UI, model `verbose_name`s, and content are Thai; `LANGUAGE_CODE = "th"`, `TIME_ZONE = "Asia/Bangkok"`.

## Commands

```bash
# Dev setup (SQLite — leave DB_HOST blank in .env; Postgres — see below)
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py seed_demo          # demo brands/cars/promos/reviews/branches
python manage.py createsuperuser
python manage.py runserver           # http://127.0.0.1:8000  ·  admin at /admin/

# Postgres for dev (แทน SQLite) — ตั้ง DB_HOST=127.0.0.1 ใน .env ก่อน
docker compose -f docker-compose.dev.yml up -d    # postgres:16 บน :5432 (oxlet/oxlet/oxlet)

# Data import (real data lives outside the repo)
python manage.py import_listings     # cars from scraped_cars.json
python manage.py import_media         # brand logos + car photos from ../oxlet_images/
python manage.py import_plates        # ป้ายทะเบียน + รูป จาก ~/Documents/tabien-scraper/
python manage.py backup_data          # zip of DB dump + media (for Postgres/Supabase migration)

# Sync jobs (need GOOGLE_MAPS_API_KEY / YOUTUBE_CHANNEL_ID; safe to run repeatedly)
python manage.py sync_google_reviews  # Google reviews per Branch (max 5/place, Google's limit)
python manage.py sync_google_photos
python manage.py sync_youtube         # via free RSS feed, no API key
python manage.py add_tiktok <url>
python manage.py purge_trash          # hard-delete vehicles trashed > 30 days (cron this)
```

There is no test suite, linter, or formatter configured. `python manage.py test` runs Django's runner against zero tests. Frontend deps (Bootstrap, icons, fonts) load from CDN — nothing to build.

## Environment-driven behavior

Two settings toggles change infrastructure with no code change (see `config/settings.py`):

- **Database**: `DB_HOST` set → PostgreSQL (prod/Supabase, or the local `docker-compose.dev.yml` container); blank → SQLite `db.sqlite3` (dev). Postgres enforces `max_length`, SQLite does not — check field widths against seeded/imported data before assuming a migration that passed on SQLite will pass on Postgres.
- **Media storage**: `R2_BUCKET` set → Cloudflare R2 via `django-storages` S3 backend; blank → local `media/` (dev). `ImageField`s are storage-agnostic, so nothing else changes.

`GEMINI_API_KEY` blank disables the AI chatbot gracefully (it returns a "not enabled" message, never errors). `DEBUG` defaults to `True` and `SECRET_KEY` to an insecure dev value — both must be set for production.

## Architecture

Everything lives in the single **`cars`** app; `config/` holds only settings/urls/wsgi. Key cross-cutting patterns that span multiple files:

- **Two admin surfaces.** Django's `/admin/` (`cars/admin.py`) is the full backend. Separately, `cars/views.py` implements a lightweight **front-end CRUD** ("manage" views, all `@staff_member_required`) so staff edit cars/promos/branches/FAQs/plates/socials/settings directly from the public site via the "⚙️ จัดการ" navbar menu. These manage views render `templates/manage/*` using ModelForms in `cars/forms.py` (all use `BootstrapMixin` to auto-apply Bootstrap classes). When adding an editable model, wire up all three: model → form → manage view + URL.

- **AI sales assistant, grounded in live inventory** (`cars/ai.py`). `chat()` view → `chat_reply()` calls Google Gemini over raw REST (`urllib`, no SDK). `build_context()` queries the DB for relevant vehicles and injects them as context; the system prompt forbids inventing any car/price/spec not in that context. `find_relevant_cars()` maps Thai body-type keywords (`TYPE_KEYWORDS`) and brand/model tokens to queryset filters. Rate-limited to 15 msgs/min/session. Widget is `templates/_chat_widget.html`, included globally via `base.html`.

- **Soft-delete + status filtering.** `Vehicle.deleted_at` implements a trash (restore within `PURGE_DAYS = 30`). The canonical public queryset is `views._available()` = `deleted_at__isnull=True` AND `status != "sold"`. Use it (or replicate both conditions) for any customer-facing listing; sold/trashed cars are staff-only (`car_sold`, `car_trash` views). The AI's `_available()` in `cars/ai.py` mirrors this.

- **Site globals via context processor.** `cars/context_processors.py:site_globals` exposes `SITE_NAME/PHONE/LINE/HOURS`, `branches`, and `SOCIALS` to every template, sourced from the singleton `SiteSetting` (`SiteSetting.get()`, pk=1) and `SocialLink`/`Branch`. Editable in admin — do not hardcode contact info in templates.

- **LINE contact links** (`cars/contact_links.py`). All "chat with us" buttons are deep links that pre-fill a LINE message (`line_message_url`, `car_inquiry_text`). Facebook/Instagram can only open a chat (Meta blocks prefill), so those pair with a copy-details button.

- **License plates are scraped, not hand-entered.** `import_plates` reads `plates.csv` + `images/` from the tabien-scraper folder and upserts `LicensePlate` on `(source, source_id)` (unique constraint, blank for hand-added plates) — rerunning it updates in place instead of duplicating. Images land in `media/plates/<source>-<source_id>.png` (git-ignored; re-import to rebuild). `plate_type` is derived from the source's `plate_style`/`vehicle_type` strings; the raw values are kept in `style`/`vehicle_type`/`category`. `is_own` marks the shop's own plates (default `True`, forced `False` for imported rows via `create_defaults` so a re-import never overrides a staff toggle) — they sort first (`Meta.ordering`, and the Python sorts in `plate_list`) and render in their own highlighted block above the rest. The shop's 16 own plates live in `cars/fixtures/own_plates.json` (`loaddata own_plates`) — they were rebuilt by reading the plate photos in `media/plates/*.jpg`, so that fixture is the only copy of that data.

- **Slugs & titles.** `Vehicle`/`Brand`/`CarType` auto-generate unique slugs on save via `models._unique_slug`. Vehicle slugs are forced ASCII (`unicode=False`) for clean URLs; brand/type slugs allow Thai. `Vehicle.title` is a computed property (dedupes submodel already contained in model). Detail URLs are `/listings/<slug>/`.

- **Leads are not yet pushed anywhere.** `views._save_lead` stores `Lead` rows; the LINE-push integration (`cars/line.py`) is a planned TODO and does not exist. Env vars `LINE_CHANNEL_TOKEN`/`LINE_GROUP_ID` are placeholders.

## Deployment

Docker Compose: `web` (Gunicorn) + `caddy` (reverse proxy, automatic HTTPS). `Dockerfile` runs `collectstatic` at build; WhiteNoise serves static in-process. Target is a HostAtom VPS with Supabase (Postgres) + Cloudflare R2. Edit the domain in `Caddyfile`. Full runbook in `DEPLOY.md`.
