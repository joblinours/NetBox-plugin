from netbox.plugins import PluginMenu, PluginMenuItem

menu = PluginMenu(
    label="CMDB",
    icon_class="mdi mdi-database-check",
    groups=(
        (
            "Sources",
            (
                PluginMenuItem(
                    link="plugins:netbox_cmdb:sourcestatus_list",
                    link_text="Source health",
                    permissions=["netbox_cmdb.view_sourcestatus"],
                ),
            ),
        ),
    ),
)
