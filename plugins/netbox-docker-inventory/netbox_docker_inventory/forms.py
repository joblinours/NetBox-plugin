from netbox.forms import NetBoxModelFilterSetForm

from .models import DockerContainer, DockerHost, DockerNetwork


class DockerHostFilterForm(NetBoxModelFilterSetForm):
    model = DockerHost


class DockerNetworkFilterForm(NetBoxModelFilterSetForm):
    model = DockerNetwork


class DockerContainerFilterForm(NetBoxModelFilterSetForm):
    model = DockerContainer
