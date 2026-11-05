from netbox.api.viewsets import NetBoxReadOnlyModelViewSet

from ..filtersets import DNSRewriteFilterSet
from ..models import DNSRewrite
from .serializers import DNSRewriteSerializer


class DNSRewriteViewSet(NetBoxReadOnlyModelViewSet):
    queryset = DNSRewrite.objects.prefetch_related("tags")
    serializer_class = DNSRewriteSerializer
    filterset_class = DNSRewriteFilterSet
