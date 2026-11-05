from netbox.api.viewsets import NetBoxReadOnlyModelViewSet

from .. import filtersets
from ..models import PublicHostname, Tunnel
from .serializers import PublicHostnameSerializer, TunnelSerializer


class TunnelViewSet(NetBoxReadOnlyModelViewSet):
    queryset = Tunnel.objects.prefetch_related("tags")
    serializer_class = TunnelSerializer
    filterset_class = filtersets.TunnelFilterSet


class PublicHostnameViewSet(NetBoxReadOnlyModelViewSet):
    queryset = PublicHostname.objects.select_related("tunnel", "service", "proxy_service").prefetch_related("tags")
    serializer_class = PublicHostnameSerializer
    filterset_class = filtersets.PublicHostnameFilterSet
