from django.apps import apps
from netbox.api.viewsets import NetBoxReadOnlyModelViewSet
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .. import filtersets
from ..ingest import SnapshotError, apply_snapshot
from ..models import DockerContainer, DockerHost, DockerNetwork
from .serializers import DockerContainerSerializer, DockerHostSerializer, DockerNetworkSerializer


def _report(name, ok, message, details=None):
    if apps.is_installed("netbox_cmdb"):
        from netbox_cmdb.models import SourceStatus

        SourceStatus.report(name, ok, message, details)


class SnapshotView(APIView):
    """POST: full inventory of one Docker host, sent by cmdb-docker-agent."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if not (
            user.has_perm("netbox_docker_inventory.add_dockerhost")
            and user.has_perm("netbox_docker_inventory.change_dockerhost")
        ):
            raise PermissionDenied("Requires add/change permission on netbox_docker_inventory.dockerhost")
        name = str((request.data.get("host") or {}).get("name") or "unknown")[:50]
        source = f"docker-{name}".lower().replace(" ", "-").replace(".", "-")
        try:
            result = apply_snapshot(request.data)
        except SnapshotError as exc:
            _report(source, False, f"invalid snapshot: {exc}")
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            _report(source, False, repr(exc))
            raise
        summary = result.as_dict()
        _report(source, True, f"{result.containers} containers, {result.networks} networks", summary)
        return Response(summary, status=status.HTTP_200_OK)


class DockerHostViewSet(NetBoxReadOnlyModelViewSet):
    queryset = DockerHost.objects.prefetch_related("tags")
    serializer_class = DockerHostSerializer
    filterset_class = filtersets.DockerHostFilterSet


class DockerNetworkViewSet(NetBoxReadOnlyModelViewSet):
    queryset = DockerNetwork.objects.select_related("host").prefetch_related("tags")
    serializer_class = DockerNetworkSerializer
    filterset_class = filtersets.DockerNetworkFilterSet


class DockerContainerViewSet(NetBoxReadOnlyModelViewSet):
    queryset = DockerContainer.objects.select_related("host", "service").prefetch_related("tags", "networks")
    serializer_class = DockerContainerSerializer
    filterset_class = filtersets.DockerContainerFilterSet
