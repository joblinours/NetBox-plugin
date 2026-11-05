from django import forms
from netbox.forms import NetBoxModelFilterSetForm

from .models import AnswerTypeChoices, DNSRewrite


class DNSRewriteFilterForm(NetBoxModelFilterSetForm):
    model = DNSRewrite
    answer_type = forms.MultipleChoiceField(choices=AnswerTypeChoices.choices, required=False)
