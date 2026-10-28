# Workshop dev container: CalculiX, Gmsh, Python 3.12, uv, Node.js LTS and Claude Code (see INSTRUCTOR.md).
# Everything is installed here, at build time; nothing third-party is stored in the repository.
FROM mcr.microsoft.com/devcontainers/base:3.0.10-ubuntu24.04

ARG CALCULIX_VERSION=2.21-1
ARG GMSH_VERSION=4.12.1+ds1-1.1build2
ARG NODE_MAJOR=24
ARG CLAUDE_CODE_VERSION=2.1.308
ARG DEBIAN_FRONTEND=noninteractive

# CalculiX (GPL-2) and Gmsh (GPL) from the Ubuntu 24.04 archive; python3 is 3.12 on Ubuntu 24.04.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      calculix-ccx=${CALCULIX_VERSION} gmsh=${GMSH_VERSION} python3 ca-certificates curl gnupg \
 && rm -rf /var/lib/apt/lists/*

# Node.js LTS from NodeSource: https://github.com/nodesource/distributions/blob/master/DEV_README.md
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x -o /tmp/nodesource_setup.sh \
 && bash /tmp/nodesource_setup.sh \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/* /tmp/nodesource_setup.sh

# Claude Code, pinned: https://code.claude.com/docs/en/devcontainer (with DISABLE_AUTOUPDATER=1 in devcontainer.json)
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}

# uv, pinned: https://docs.astral.sh/uv/guides/integration/docker/
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/
