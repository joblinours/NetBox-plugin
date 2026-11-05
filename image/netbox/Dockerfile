# syntax=docker/dockerfile:1.7
# NetBox CMDB image: official netbox-docker image + third-party plugins (PyPI)
# + home-made plugins (this repository). Built by GitHub Actions, pushed to GHCR.
ARG NETBOX_VERSION=v4.7.4
FROM docker.io/netboxcommunity/netbox:${NETBOX_VERSION}

LABEL org.opencontainers.image.source="https://github.com/joblinours/NetBox-plugin" \
      org.opencontainers.image.description="NetBox CMDB homelab (NetBox + Diode plugin + homelab plugins)" \
      org.opencontainers.image.licenses="MIT"

# Third-party plugins. NetBox's own requirements are used as constraints so a
# plugin can never silently upgrade a NetBox dependency.
COPY image/netbox/plugin_requirements.txt /opt/netbox/plugin_requirements.txt
# Home-made plugins, installed from this repository in the same build.
COPY plugins/ /opt/netbox/local_plugins/
RUN --mount=type=secret,id=ca,required=false \
    if [ -s /run/secrets/ca ]; then export SSL_CERT_FILE=/run/secrets/ca; fi; \
    /usr/local/bin/uv pip install --no-cache \
      -c /opt/netbox/requirements.txt \
      -r /opt/netbox/plugin_requirements.txt \
      /opt/netbox/local_plugins/netbox-cloudflare-tunnel \
      /opt/netbox/local_plugins/netbox-cmdb \
 && rm -rf /opt/netbox/local_plugins

COPY image/netbox/config/plugins.py /etc/netbox/config/plugins.py
COPY image/netbox/launch-cmdb.sh /opt/netbox/launch-cmdb.sh

# Static files of every plugin are generated at build time. The dummy key is
# only used for this build step and never reaches a running container.
RUN SECRET_KEY="build-only-dummy-key-build-only-dummy-key-build-only-dummy" \
    /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py collectstatic --no-input \
 && mkdir -p /opt/netbox/netbox/static/netbox_topology_views/img

CMD ["/opt/netbox/docker-entrypoint.sh", "/opt/netbox/launch-cmdb.sh"]
