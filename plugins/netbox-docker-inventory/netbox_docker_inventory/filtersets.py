import django_filters
from django.db.models import Q
from netbox.filtersets import NetBoxModelFilterSet

from .models import DockerContainer, DockerHost, DockerNetwork


class DockerHostFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = DockerHost
        fields = ("id", "name", "engine_version")

    def search(self, queryset, name, value):
        return queryset.filter(Q(name__icontains=value) | Q(hostname__icontains=value))


class DockerNetworkFilterSet(NetBoxModelFilterSet):
    host_id = django_filters.ModelMultipleChoiceFilter(queryset=DockerHost.objects.all(), field_name="host")

    class Meta:
        model = DockerNetwork
        fields = ("id", "name", "driver", "internal", "stack")

    def search(self, queryset, name, value):
        return queryset.filter(Q(name__icontains=value) | Q(stack__icontains=value))


class DockerContainerFilterSet(NetBoxModelFilterSet):
    host_id = django_filters.ModelMultipleChoiceFilter(queryset=DockerHost.objects.all(), field_name="host")
    network_id = django_filters.ModelMultipleChoiceFilter(queryset=DockerNetwork.objects.all(), field_name="networks")

    class Meta:
        model = DockerContainer
        fields = ("id", "name", "image", "state", "stack", "compose_service")

    def search(self, queryset, name, value):
        return queryset.filter(Q(name__icontains=value) | Q(image__icontains=value) | Q(stack__icontains=value))
