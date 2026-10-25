from django import forms
from django.contrib.auth.models import User

from home.models import Address


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "email")
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control", "autocomplete": "given-name"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "autocomplete": "email"}),
        }


class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ("label", "line1", "line2", "city", "state", "zip_code")
        widgets = {
            "label": forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}),
            "line1": forms.TextInput(attrs={"class": "form-control", "autocomplete": "address-line1"}),
            "line2": forms.TextInput(attrs={"class": "form-control", "autocomplete": "address-line2"}),
            "city": forms.TextInput(attrs={"class": "form-control", "autocomplete": "address-level2"}),
            "state": forms.TextInput(attrs={"class": "form-control", "autocomplete": "address-level1"}),
            "zip_code": forms.TextInput(attrs={"class": "form-control", "autocomplete": "postal-code"}),
        }
