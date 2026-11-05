from django import forms
from netbox.forms import NetBoxModelFilterSetForm

from .models import ExposureChoices, PublicHostname, Tunnel


class TunnelFilterForm(NetBoxModelFilterSetForm):
    model = Tunnel


class PublicHostnameFilterForm(NetBoxModelFilterSetForm):
    model = PublicHostname
    exposure = forms.MultipleChoiceField(choices=ExposureChoices.choices, required=False)
