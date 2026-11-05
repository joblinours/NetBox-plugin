"""Read-only MCP server for the homelab CMDB, served by NetBox at /api/plugins/mcp/."""

from netbox.plugins import PluginConfig

__version__ = "0.1.0"


class CMDBMCPConfig(PluginConfig):
    name = "netbox_cmdb_mcp"
    verbose_name = "CMDB MCP server"
    description = "Read-only Model Context Protocol endpoint for Claude"
    version = __version__
    author = "Lucas Joblin"
    base_url = "mcp"
    min_version = "4.7.0"
    max_version = "4.7.99"
    default_settings = {
        # IP ranges never proposed as free (DHCP pool, static reservations), e.g. ["192.168.1.100-192.168.1.199"]
        "reserved_ip_ranges": [],
        # Default prefix for find_free_ips when none is given
        "default_prefix": "192.168.1.0/24",
    }


config = CMDBMCPConfig
