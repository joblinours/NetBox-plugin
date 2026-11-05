from netbox.plugins import PluginMenu, PluginMenuItem

menu = PluginMenu(
    label="Docker",
    icon_class="mdi mdi-docker",
    groups=(
        (
            "Inventory",
            (
                PluginMenuItem(
                    link="plugins:netbox_docker_inventory:dockerhost_list",
                    link_text="Docker hosts",
                    permissions=["netbox_docker_inventory.view_dockerhost"],
                ),
                PluginMenuItem(
                    link="plugins:netbox_docker_inventory:dockercontainer_list",
                    link_text="Containers",
                    permissions=["netbox_docker_inventory.view_dockercontainer"],
                ),
                PluginMenuItem(
                    link="plugins:netbox_docker_inventory:dockernetwork_list",
                    link_text="Networks",
                    permissions=["netbox_docker_inventory.view_dockernetwork"],
                ),
            ),
        ),
    ),
)
