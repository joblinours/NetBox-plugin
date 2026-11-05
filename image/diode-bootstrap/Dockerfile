ARG DIODE_VERSION=2.4.0
FROM docker.io/netboxlabs/diode-auth:${DIODE_VERSION}
LABEL org.opencontainers.image.source="https://github.com/joblinours/NetBox-plugin" \
      org.opencontainers.image.description="Creates Diode OAuth2 clients from environment variables" \
      org.opencontainers.image.licenses="MIT"
COPY --chmod=0755 image/diode-bootstrap/bootstrap-clients.sh /usr/local/bin/bootstrap-clients.sh
ENTRYPOINT ["/bin/sh", "/usr/local/bin/bootstrap-clients.sh"]
CMD []
