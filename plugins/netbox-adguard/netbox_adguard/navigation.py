from netbox.plugins import PluginMenuItem

menu_items = (
    PluginMenuItem(
        link="plugins:netbox_adguard:dnsrewrite_list",
        link_text="AdGuard DNS rewrites",
        permissions=["netbox_adguard.view_dnsrewrite"],
    ),
)
