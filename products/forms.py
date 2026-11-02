from decimal import Decimal

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


class RecommendationForm(forms.Form):
    BUDGET_CHOICES = (
        ("", "Choose a budget"),
        ("0-5000", "Under ₹5,000"),
        ("5000-10000", "₹5,000 – ₹10,000"),
        ("10000-20000", "₹10,000 – ₹20,000"),
        ("20000-30000", "₹20,000 – ₹30,000"),
        ("30000-50000", "₹30,000 – ₹50,000"),
        ("custom", "Custom budget"),
    )

    category = forms.ChoiceField(label="What do you want to buy?")
    budget_range = forms.ChoiceField(label="What is your budget?", choices=BUDGET_CHOICES)
    min_budget = forms.DecimalField(label="Minimum budget", min_value=Decimal("0"), required=False, decimal_places=2, max_digits=10)
    max_budget = forms.DecimalField(label="Maximum budget", min_value=Decimal("0"), required=False, decimal_places=2, max_digits=10)

    def __init__(self, *args, categories=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].choices = [("", "Choose a category")] + list(categories)
        self.fields["category"].widget.attrs["class"] = "assistant-select"
        self.fields["budget_range"].widget.attrs["class"] = "assistant-select"
        for name in ("min_budget", "max_budget"):
            self.fields[name].widget.attrs.update({"class": "assistant-input", "placeholder": "₹", "inputmode": "decimal"})

    def clean(self):
        cleaned = super().clean()
        budget_range = cleaned.get("budget_range")
        if not budget_range:
            return cleaned
        if budget_range == "custom":
            minimum, maximum = cleaned.get("min_budget"), cleaned.get("max_budget")
            if minimum is None or maximum is None:
                raise forms.ValidationError("Enter both a minimum and maximum budget.")
        else:
            minimum, maximum = (Decimal(value) for value in budget_range.split("-"))
            cleaned["min_budget"], cleaned["max_budget"] = minimum, maximum
        if minimum > maximum:
            raise forms.ValidationError("Minimum budget cannot be greater than maximum budget.")
        return cleaned
