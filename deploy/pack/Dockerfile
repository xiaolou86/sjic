# 打包机：Python 3.10 编字节码，Node 构建前端。只在厂商侧构建一次。
FROM python:3.10-slim-bookworm

ARG NODE_VERSION=22.19.0
ARG TARGETARCH

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl xz-utils \
    && case "${TARGETARCH}" in \
         amd64) NODE_ARCH=x64 ;; \
         arm64) NODE_ARCH=arm64 ;; \
         *) echo "unsupported arch: ${TARGETARCH}" && exit 1 ;; \
       esac \
    && curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz" -o /tmp/node.tar.xz \
    && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 \
    && rm /tmp/node.tar.xz \
    && apt-get purge -y curl xz-utils \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
