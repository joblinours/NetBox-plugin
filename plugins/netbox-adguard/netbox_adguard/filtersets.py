import django_filters
from django.db.models import Q
from netbox.filtersets import NetBoxModelFilterSet

from .models import AnswerTypeChoices, DNSRewrite


class DNSRewriteFilterSet(NetBoxModelFilterSet):
    answer_type = django_filters.MultipleChoiceFilter(choices=AnswerTypeChoices.choices)

    class Meta:
        model = DNSRewrite
        fields = ("id", "domain", "answer", "enabled", "instance", "ip_address_id", "virtual_machine_id", "device_id")

    def search(self, queryset, name, value):
        return queryset.filter(Q(domain__icontains=value) | Q(answer__icontains=value))
