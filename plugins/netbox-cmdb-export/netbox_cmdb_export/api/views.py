from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from ..exporter import http_response


class ExportAPIView(APIView):
    """GET /api/plugins/export/<fmt>/ (md, pdf, json, mmd, dot, png, svg). ?containers=1 for container nodes."""

    permission_classes = [IsAuthenticated]

    def get(self, request, fmt):
        return http_response(request.user, fmt, request.query_params.get("containers") == "1")
