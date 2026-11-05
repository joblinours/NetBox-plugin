from netbox.api.routers import NetBoxRouter

from . import views

app_name = "netbox_cloudflare_tunnel-api"

router = NetBoxRouter()
router.register("tunnels", views.TunnelViewSet)
router.register("hostnames", views.PublicHostnameViewSet)
urlpatterns = router.urls
