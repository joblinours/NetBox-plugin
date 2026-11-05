from netbox.search import SearchIndex, register_search

from .models import DNSRewrite


@register_search
class DNSRewriteIndex(SearchIndex):
    model = DNSRewrite
    fields = (("domain", 100), ("answer", 300))
    display_attrs = ("answer", "virtual_machine", "device")
