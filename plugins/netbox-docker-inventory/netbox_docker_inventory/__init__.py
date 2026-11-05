"""Docker inventory plugin: hosts, stacks, containers, networks pushed by cmdb-docker-agent."""

from netbox.plugins import PluginConfig

__version__ = "0.1.0"


class DockerInventoryConfig(PluginConfig):
    name = "netbox_docker_inventory"
    verbose_name = "Docker inventory"
    description = "Docker hosts, stacks, containers and networks pushed by an agent"
    version = __version__
    author = "Lucas Joblin"
    base_url = "docker-inventory"
    min_version = "4.7.0"
    max_version = "4.7.99"
    default_settings = {
        # Create / update an ipam.Service on the host VM for each container publishing ports.
        "create_services": True,
        # Tag put on the services managed by this plugin.
        "service_tag": "docker",
    }


config = DockerInventoryConfig
