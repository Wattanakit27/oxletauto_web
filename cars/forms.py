"""ฟอร์มสำหรับแก้ไขเนื้อหาจากหน้าเว็บ (โหมดแอดมิน)"""
from django import forms

from .models import (
    FAQ,
    Booking,
    Branch,
    LicensePlate,
    Promotion,
    SiteSetting,
    SocialLink,
    Vehicle,
)


class BootstrapMixin:
    """ใส่คลาส Bootstrap ให้ทุกช่องอัตโนมัติ"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            w = field.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs.setdefault("class", "form-check-input")
            elif isinstance(w, (forms.Select, forms.SelectMultiple)):
                w.attrs.setdefault("class", "form-select")
            else:
                w.attrs.setdefault("class", "form-control")


class VehicleForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = [
            "stock_code",  # ผูกกับรถจริงในสต็อก backend (Car.code) — sync สถานะ realtime · ว่าง = ไม่ผูก
            "brand", "model", "submodel", "plate", "year", "car_type",
            "transmission", "drivetrain", "fuel", "engine_cc", "mileage",
            "color_exterior", "color_interior",
            "price", "installment_min", "interest_rate",
            "condition", "status", "branch",
            "warranty", "inspection_points", "description", "is_featured",
        ]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}


class PromotionForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Promotion
        fields = ["title", "vehicle", "detail", "image", "active", "order"]
        widgets = {"detail": forms.Textarea(attrs={"rows": 3})}


class BranchForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Branch
        fields = [
            "name", "address", "phone", "hours",
            "map_url", "google_maps_url", "lat", "lng",
        ]
        widgets = {"address": forms.Textarea(attrs={"rows": 2})}


class FAQForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = FAQ
        fields = ["question", "answer", "order", "active"]
        widgets = {"answer": forms.Textarea(attrs={"rows": 3})}


class SiteSettingForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = SiteSetting
        fields = ["site_name", "tagline", "phone", "line_id", "hours", "about_text",
                  "visitor_count", "promptpay_id", "deposit_amount"]
        widgets = {"about_text": forms.Textarea(attrs={"rows": 5})}


class BookingForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Booking
        fields = ["name", "phone", "slip"]
        widgets = {"slip": forms.ClearableFileInput(attrs={"accept": "image/*"})}


class SocialLinkForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = SocialLink
        fields = ["label", "value", "url", "icon", "color", "order", "active"]


class LicensePlateForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = LicensePlate
        fields = ["prefix", "number", "province", "plate_type",
                  "price", "status", "image", "note", "is_featured"]
        widgets = {"note": forms.Textarea(attrs={"rows": 2})}
