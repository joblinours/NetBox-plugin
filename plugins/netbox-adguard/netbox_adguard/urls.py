from django.urls import include, path
from utilities.urls import get_model_urls

from . import views

urlpatterns = [
    path("sync/", views.SyncNowView.as_view(), name="sync"),
    path("rewrites/", include(get_model_urls("netbox_adguard", "dnsrewrite", detail=False))),
    path("rewrites/<int:pk>/", include(get_model_urls("netbox_adguard", "dnsrewrite"))),
]
