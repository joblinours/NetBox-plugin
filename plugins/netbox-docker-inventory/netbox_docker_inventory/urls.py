from django.urls import include, path
from utilities.urls import get_model_urls

from . import views  # noqa: F401  (registers the views)

APP = "netbox_docker_inventory"

urlpatterns = []
for prefix, model in (("hosts", "dockerhost"), ("networks", "dockernetwork"), ("containers", "dockercontainer")):
    urlpatterns += [
        path(f"{prefix}/", include(get_model_urls(APP, model, detail=False))),
        path(f"{prefix}/<int:pk>/", include(get_model_urls(APP, model))),
    ]
