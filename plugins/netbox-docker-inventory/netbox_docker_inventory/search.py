from netbox.search import SearchIndex, register_search

from .models import DockerContainer, DockerNetwork


@register_search
class DockerContainerIndex(SearchIndex):
    model = DockerContainer
    fields = (("name", 100), ("image", 300), ("stack", 300))
    display_attrs = ("host", "stack", "state")


@register_search
class DockerNetworkIndex(SearchIndex):
    model = DockerNetwork
    fields = (("name", 100), ("stack", 300))
    display_attrs = ("host", "driver")
