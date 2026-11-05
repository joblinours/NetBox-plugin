"""CMDB export: Markdown, PDF, JSON and topology graphs (Mermaid / PNG / SVG)."""

from netbox.plugins import PluginConfig

__version__ = "0.1.0"


class CMDBExportConfig(PluginConfig):
    name = "netbox_cmdb_export"
    verbose_name = "CMDB export"
    description = "Export the CMDB as Markdown, PDF, JSON or a topology graph"
    version = __version__
    author = "Lucas Joblin"
    base_url = "export"
    min_version = "4.7.0"
    max_version = "4.7.99"
    required_settings = []
    default_settings = {
        "title": "CMDB homelab",
        "graphviz_dot": "dot",
        "pdf_font": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "pdf_font_bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    }


config = CMDBExportConfig
