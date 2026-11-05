ARG ORB_AGENT_VERSION=2.17.0
FROM docker.io/netboxlabs/orb-agent:${ORB_AGENT_VERSION}
LABEL org.opencontainers.image.source="https://github.com/joblinours/NetBox-plugin" \
      org.opencontainers.image.description="orb-agent network scan for the NetBox CMDB stack (config from env vars)" \
      org.opencontainers.image.licenses="MIT"
COPY --chmod=0755 image/orb-agent/cmdb-entry.sh /usr/local/bin/cmdb-entry.sh
COPY --chmod=0755 image/orb-agent/cmdb-reporter.py /usr/local/bin/cmdb-reporter.py
ENTRYPOINT ["/sbin/tini", "--", "/usr/local/bin/cmdb-entry.sh"]
CMD []
