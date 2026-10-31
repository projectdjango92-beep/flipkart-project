

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password

from crispy_forms.helper import FormHelper
from crispy_forms.layout import (
    Layout,
    Row,
    Column,
    Submit,
)

from .models import Address, Customer


class ProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField()

    class Meta:
        model = Customer
        fields = ("mobile", "street", "address", "city", "postcode", "country")

    def save(self, commit=True):
        customer = super().save(commit=False)
        user = customer.user
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.email = self.cleaned_data["email"]
        if commit:
            user.save(update_fields=["first_name", "last_name", "email"])
            customer.save()
        return customer


class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ("full_name", "mobile", "house", "street", "city", "state", "pin_code", "landmark", "is_default")


class RegistrationForm(forms.ModelForm):
    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "First name",
        })
    )

    last_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Last name",
        })
    )

    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            "class": "form-control",
            "placeholder": "Email address",
        })
    )

    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Username",
        })
    )

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Password",
        }),
        validators=[validate_password],
    )

    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Confirm password",
        })
    )

    class Meta:
        model = Customer
        fields = [
            "mobile",
            "street",
            "address",
            "city",
            "postcode",
            "country",
        ]

        widgets = {
            "mobile": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Mobile number",
            }),
            "street": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Street",
            }),
            "address": forms.Textarea(attrs={
                "class": "form-control",
                "placeholder": "Address",
                "rows": 4,
            }),
            "city": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "City",
            }),
            "postcode": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Postcode",
            }),
            "country": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Country",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_method = "post"

        self.helper.layout = Layout(
            Row(
                Column("first_name", css_class="col-md-6"),
                Column("last_name", css_class="col-md-6"),
                css_class="g-3",
            ),

            Row(
                Column("username", css_class="col-md-6"),
                Column("email", css_class="col-md-6"),
                css_class="g-3",
            ),

            Row(
                Column("password", css_class="col-md-6"),
                Column("password_confirm", css_class="col-md-6"),
                css_class="g-3",
            ),

            Row(
                Column("address", css_class="col-md-12"),
                css_class="g-3",
            ),

            Row(
                Column("street", css_class="col-md-4"),
                Column("city", css_class="col-md-4"),
                Column("postcode", css_class="col-md-4"),
                css_class="g-3",
            ),

            Row(
                Column("country", css_class="col-md-6"),
                Column("mobile", css_class="col-md-6"),
                css_class="g-3",
            ),

            Submit(
                "submit",
                "Create Account",
                css_class="btn btn-flipkart mt-3",
            ),
        )

    def clean_username(self):
        username = self.cleaned_data["username"]

        if User.objects.filter(username=username).exists():
            raise forms.ValidationError(
                "This username is already taken."
            )

        return username

    def clean_email(self):
        email = self.cleaned_data["email"]

        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(
                "An account with this email already exists."
            )

        return email

    def clean(self):
        cleaned_data = super().clean()

        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        if password and password_confirm and password != password_confirm:
            self.add_error(
                "password_confirm",
                "Passwords do not match."
            )

        return cleaned_data

    def save(self, commit=True):
        customer = super().save(commit=False)

        user = User.objects.create_user(
            username=self.cleaned_data["username"],
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password"],
            first_name=self.cleaned_data["first_name"],
            last_name=self.cleaned_data["last_name"],
        )

        customer.user = user

        if commit:
            customer.save()

        return customer
