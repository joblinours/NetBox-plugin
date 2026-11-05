from django.utils.dateparse import parse_datetime
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..health import build_health
from ..models import SourceStatus


class ReportSerializer(serializers.Serializer):
    source = serializers.SlugField(max_length=64)
    status = serializers.ChoiceField(choices=["ok", "failed"])
    message = serializers.CharField(required=False, allow_blank=True, default="")
    details = serializers.JSONField(required=False, default=dict)
    time = serializers.CharField(required=False, allow_blank=True)


class SourceStatusSerializer(serializers.ModelSerializer):
    healthy = serializers.BooleanField(read_only=True)
    stale = serializers.BooleanField(source="is_stale", read_only=True)
    age_hours = serializers.FloatField(read_only=True, allow_null=True)

    class Meta:
        model = SourceStatus
        fields = (
            "id",
            "name",
            "status",
            "message",
            "details",
            "last_run",
            "last_success",
            "run_count",
            "failure_count",
            "healthy",
            "stale",
            "age_hours",
        )


class HealthView(APIView):
    """GET: overall CMDB health (database + every automatic source). Used by Zabbix."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.has_perm("netbox_cmdb.view_sourcestatus"):
            raise PermissionDenied("Requires netbox_cmdb.view_sourcestatus")
        return Response(build_health())


class SourceReportView(APIView):
    """POST: an external source (orb-agent reporter, Nginx agent) reports the outcome of a run."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.has_perm("netbox_cmdb.view_sourcestatus"):
            raise PermissionDenied("Requires netbox_cmdb.view_sourcestatus")
        return Response(SourceStatusSerializer(SourceStatus.objects.all(), many=True).data)

    def post(self, request):
        if not request.user.has_perm("netbox_cmdb.change_sourcestatus"):
            raise PermissionDenied("Requires netbox_cmdb.change_sourcestatus")
        data = ReportSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        when = parse_datetime(v["time"]) if v.get("time") else None
        obj = SourceStatus.report(v["source"], v["status"] == "ok", v.get("message", ""), v.get("details"), when)
        return Response(SourceStatusSerializer(obj).data, status=status.HTTP_201_CREATED)
