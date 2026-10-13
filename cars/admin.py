from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Booking,
    Brand,
    Branch,
    CarType,
    Lead,
    Promotion,
    Review,
    ReviewImage,
    SiteSetting,
    SocialLink,
    Vehicle,
    VehicleImage,
    VehicleOption,
    Video,
)


class VehicleImageInline(admin.TabularInline):
    model = VehicleImage
    extra = 3
    fields = ("preview", "image", "is_cover", "order")
    readonly_fields = ("preview",)

    def preview(self, obj):
        if obj and obj.image:
            return format_html(
                '<img src="{}" style="height:64px;width:96px;object-fit:cover;border-radius:6px">',
                obj.image.url,
            )
        return "—"
    preview.short_description = "ตัวอย่าง"


class VehicleOptionInline(admin.TabularInline):
    model = VehicleOption
    extra = 5


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("thumb", "title", "brand", "year", "price_baht", "installment_min", "status", "listed", "is_featured", "view_link")
    list_display_links = ("thumb", "title")
    # listed = ปุ่ม Active จากระบบหลังบ้าน (ไม่ใส่ list_editable — แก้ที่นี่จะโดน sync ทับ)
    list_filter = ("status", "listed", "is_featured", "brand", "car_type", "transmission", "condition", "branch")
    search_fields = ("model", "submodel", "brand__name", "plate", "stock_code")
    list_editable = ("status", "is_featured")
    list_per_page = 30
    save_on_top = True
    inlines = [VehicleImageInline, VehicleOptionInline]
    readonly_fields = ("slug", "view_link", "created_at", "updated_at", "stock_code")
    fieldsets = (
        ("ข้อมูลรถ", {"fields": (("brand", "model"), ("submodel", "year"), ("car_type", "plate"))}),
        ("สเปก", {"fields": (("transmission", "drivetrain", "fuel"),
                              ("engine_cc", "mileage"),
                              ("color_exterior", "color_interior"))}),
        ("ราคา / ไฟแนนซ์", {"fields": (("price", "installment_min", "interest_rate"),)}),
        ("สถานะ / สาขา", {"fields": (("status", "condition", "branch"), "is_featured")}),
        ("รายละเอียด / รับประกัน", {"fields": ("warranty", "inspection_points", "description")}),
        ("ระบบ (อัตโนมัติ)", {"classes": ("collapse",),
                              "fields": ("slug", "view_link", ("stock_code", "listed"), "created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        return (super().get_queryset(request)
                .select_related("brand", "branch")
                .prefetch_related("images"))

    def thumb(self, obj):
        imgs = list(obj.images.all())
        cover = next((im for im in imgs if im.is_cover), imgs[0] if imgs else None)
        if cover and cover.image:
            return format_html(
                '<img src="{}" style="height:42px;width:64px;object-fit:cover;border-radius:5px">',
                cover.image.url,
            )
        return format_html('<span style="color:#bbb">— ไม่มีรูป —</span>')
    thumb.short_description = "รูป"

    def price_baht(self, obj):
        return f"{obj.price:,} ฿"
    price_baht.short_description = "ราคา"
    price_baht.admin_order_field = "price"

    def view_link(self, obj):
        if obj.pk:
            return format_html('<a href="{}" target="_blank">🔗 ดูหน้าเว็บ</a>', obj.get_absolute_url())
        return "—"
    view_link.short_description = "หน้าเว็บ"


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "order", "logo_tag")
    list_editable = ("order",)

    def logo_tag(self, obj):
        if obj.logo:
            return format_html('<img src="{}" height="28">', obj.logo.url)
        return "-"
    logo_tag.short_description = "โลโก้"


@admin.register(CarType)
class CarTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "order")
    list_editable = ("order",)


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ("title", "vehicle", "active", "order")
    list_editable = ("active", "order")
    list_filter = ("active",)


class ReviewImageInline(admin.TabularInline):
    model = ReviewImage
    extra = 3


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("customer_name", "branch", "rating", "source", "active", "created_at")
    list_editable = ("active",)
    list_filter = ("active", "branch", "rating", "source")
    inlines = [ReviewImageInline]


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "vehicle", "source_page", "is_handled", "created_at")
    list_editable = ("is_handled",)
    list_filter = ("is_handled", "source_page")
    search_fields = ("name", "phone", "email")


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "vehicle", "deposit_amount", "status", "slip_tag", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("name", "phone", "vehicle__model", "vehicle__brand__name")
    readonly_fields = ("created_at",)
    actions = ["confirm_booking", "cancel_booking"]

    def slip_tag(self, obj):
        if obj.slip:
            return format_html('<a href="{}" target="_blank">🧾 ดูสลิป</a>', obj.slip.url)
        return format_html('<span style="color:#bbb">— ยังไม่แนบ —</span>')
    slip_tag.short_description = "สลิป"

    @admin.action(description="✓ ยืนยันการจอง")
    def confirm_booking(self, request, queryset):
        n = queryset.update(status="confirmed")
        self.message_user(request, f"ยืนยันการจอง {n} รายการแล้ว")

    @admin.action(description="✗ ยกเลิก + ปล่อยรถกลับมาขาย")
    def cancel_booking(self, request, queryset):
        for b in queryset:
            if b.vehicle and b.vehicle.status == "reserved":
                b.vehicle.status = "available"
                b.vehicle.save(update_fields=["status"])
        n = queryset.update(status="cancelled")
        self.message_user(request, f"ยกเลิก {n} รายการ และปล่อยรถกลับมาขายแล้ว")


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ("title", "source", "active", "order", "published_at")
    list_editable = ("active", "order")
    list_filter = ("source", "active")


admin.site.register(Branch)


@admin.register(SiteSetting)
class SiteSettingAdmin(admin.ModelAdmin):
    list_display = ("site_name", "phone", "line_id", "hours")

    def has_add_permission(self, request):
        return not SiteSetting.objects.exists()  # มีได้แถวเดียว

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SocialLink)
class SocialLinkAdmin(admin.ModelAdmin):
    list_display = ("label", "value", "url", "icon", "order", "active")
    list_editable = ("order", "active")


admin.site.site_header = "Oxlet Auto — จัดการเว็บไซต์"
admin.site.site_title = "Oxlet Auto Admin"
admin.site.index_title = "แผงควบคุม"
