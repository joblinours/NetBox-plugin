from netbox.search import SearchIndex, register_search

from .models import PublicHostname


@register_search
class PublicHostnameIndex(SearchIndex):
    model = PublicHostname
    fields = (("hostname", 100), ("origin", 300), ("upstream", 300))
    display_attrs = ("tunnel", "exposure", "service")
