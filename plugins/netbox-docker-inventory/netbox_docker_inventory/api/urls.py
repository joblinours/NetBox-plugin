from django.urls import path
from netbox.api.routers import NetBoxRouter

from . import views

app_name = "netbox_docker_inventory-api"

router = NetBoxRouter()
router.register("hosts", views.DockerHostViewSet)
router.register("networks", views.DockerNetworkViewSet)
router.register("containers", views.DockerContainerViewSet)
urlpatterns = [path("snapshot/", views.SnapshotView.as_view(), name="snapshot")] + router.urls
