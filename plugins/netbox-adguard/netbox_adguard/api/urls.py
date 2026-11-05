from netbox.api.routers import NetBoxRouter

from . import views

app_name = "netbox_adguard-api"
router = NetBoxRouter()
router.register("rewrites", views.DNSRewriteViewSet)
urlpatterns = router.urls
