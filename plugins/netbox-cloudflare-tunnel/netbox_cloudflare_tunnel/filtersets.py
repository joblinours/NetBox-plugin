import django_filters
from django.db.models import Q
from netbox.filtersets import NetBoxModelFilterSet

from .models import ExposureChoices, PublicHostname, Tunnel


class TunnelFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = Tunnel
        fields = ("id", "name", "tunnel_id", "status", "remote_config")

    def search(self, queryset, name, value):
        return queryset.filter(Q(name__icontains=value) | Q(status__icontains=value))


class PublicHostnameFilterSet(NetBoxModelFilterSet):
    tunnel_id = django_filters.ModelMultipleChoiceFilter(queryset=Tunnel.objects.all(), field_name="tunnel")
    exposure = django_filters.MultipleChoiceFilter(choices=ExposureChoices.choices)

    class Meta:
        model = PublicHostname
        fields = ("id", "hostname", "path", "origin_host", "origin_port", "service_id", "proxy_service_id")

    def search(self, queryset, name, value):
        return queryset.filter(Q(hostname__icontains=value) | Q(origin__icontains=value) | Q(upstream__icontains=value))
