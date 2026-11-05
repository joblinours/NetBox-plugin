# syntax=docker/dockerfile:1.7
FROM docker.io/library/python:3.13-alpine
LABEL org.opencontainers.image.source="https://github.com/joblinours/NetBox-plugin" \
      org.opencontainers.image.description="CMDB Docker agent: pushes containers, stacks and networks of a Docker host to NetBox" \
      org.opencontainers.image.licenses="MIT"
COPY agents/docker-agent /src/docker-agent
RUN --mount=type=secret,id=ca,required=false \
    if [ -s /run/secrets/ca ]; then export PIP_CERT=/run/secrets/ca; fi; \
    pip install --no-cache-dir /src/docker-agent && rm -rf /src
ENTRYPOINT ["cmdb-docker-agent"]
