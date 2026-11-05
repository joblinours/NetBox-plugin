ARG NGINX_VERSION=1.29-alpine
FROM docker.io/library/nginx:${NGINX_VERSION}
LABEL org.opencontainers.image.source="https://github.com/joblinours/NetBox-plugin" \
      org.opencontainers.image.description="Diode gRPC entry point (nginx) for the NetBox CMDB stack" \
      org.opencontainers.image.licenses="MIT"
COPY image/diode-gateway/nginx.conf /etc/nginx/conf.d/default.conf
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1/healthz || exit 1
