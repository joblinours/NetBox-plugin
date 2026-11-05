from django.urls import include, path
from utilities.urls import get_model_urls

from . import views

urlpatterns = [
    path("sync/", views.SyncNowView.as_view(), name="sync"),
    path("tunnels/", include(get_model_urls("netbox_cloudflare_tunnel", "tunnel", detail=False))),
    path("tunnels/<int:pk>/", include(get_model_urls("netbox_cloudflare_tunnel", "tunnel"))),
    path("hostnames/", include(get_model_urls("netbox_cloudflare_tunnel", "publichostname", detail=False))),
    path("hostnames/<int:pk>/", include(get_model_urls("netbox_cloudflare_tunnel", "publichostname"))),
]
