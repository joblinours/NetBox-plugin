from netbox.plugins import PluginMenuItem

menu_items = (
    PluginMenuItem(
        link="plugins:netbox_cloudflare_tunnel:tunnel_list",
        link_text="Cloudflare tunnels",
        permissions=["netbox_cloudflare_tunnel.view_tunnel"],
    ),
    PluginMenuItem(
        link="plugins:netbox_cloudflare_tunnel:publichostname_list",
        link_text="Public hostnames",
        permissions=["netbox_cloudflare_tunnel.view_publichostname"],
    ),
)
