from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Layout, Row, Submit

from .models import Product, Review


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "name", "category", "brand", "sku", "description", "price", "image",
            "is_available", "stock_quantity", "low_stock_threshold",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Product name"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "brand": forms.TextInput(attrs={"class": "form-control", "placeholder": "Brand (optional)"}),
            "sku": forms.TextInput(attrs={"class": "form-control", "placeholder": "SKU / product code"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
            "price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "image": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "stock_quantity": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "low_stock_threshold": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "is_available": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.form_enctype = "multipart/form-data"
        self.helper.layout = Layout(
            Row(Column("name", css_class="col-md-8"), Column("category", css_class="col-md-4"), css_class="g-3"),
            Row(Column("brand", css_class="col-md-6"), Column("sku", css_class="col-md-6"), css_class="g-3"),
            Row(Column("price", css_class="col-md-4"), Column("stock_quantity", css_class="col-md-4"), Column("low_stock_threshold", css_class="col-md-4"), css_class="g-3"),
            "is_available", "description", "image",
            Submit("submit", "Save Product", css_class="btn btn-primary mt-3"),
        )


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ["rating", "comment"]
        widgets = {
            "rating": forms.RadioSelect(choices=[(number, f"{number} star{'s' if number > 1 else ''}") for number in range(1, 6)]),
            "comment": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Share your experience (optional)"}),
        }

    def clean_rating(self):
        rating = self.cleaned_data["rating"]
        if rating not in range(1, 6):
            raise forms.ValidationError("Please choose a rating from 1 to 5.")
        return rating
