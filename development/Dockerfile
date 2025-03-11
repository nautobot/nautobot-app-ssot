# -------------------------------------------------------------------------------------
# Nautobot App Developement Dockerfile Template
# Version: 1.1.0
#
# Apps that need to add additional steps or packages can do in the section below.
# -------------------------------------------------------------------------------------
# !!! USE CAUTION WHEN MODIFYING LINES BELOW

# Accepts a desired Nautobot version as build argument, default to 2.0.0
ARG NAUTOBOT_VER="2.0.0"

# Accepts a desired Python version as build argument, default to 3.11
ARG PYTHON_VER="3.11"

# Retrieve published development image of Nautobot base which should include most CI dependencies
FROM ghcr.io/nautobot/nautobot-dev:${NAUTOBOT_VER}-py${PYTHON_VER}

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Runtime argument and environment setup
ARG NAUTOBOT_ROOT=/opt/nautobot

ENV prometheus_multiproc_dir=/prom_cache
ENV NAUTOBOT_ROOT=${NAUTOBOT_ROOT}
ENV INVOKE_NAUTOBOT_SSOT_LOCAL=true

# Install Poetry manually via its installer script;
# We might be using an older version of Nautobot that includes an older version of Poetry
# and CI and local development may have a newer version of Poetry
# Since this is only used for development and we don't ship this container, pinning Poetry back is not expressly necessary
# We also don't need virtual environments in container
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Place executables in the environment at the front of the path
ENV PATH="/source/.venv/bin:$PATH"

RUN source $HOME/.local/bin/env

# !!! USE CAUTION WHEN MODIFYING LINES ABOVE
# -------------------------------------------------------------------------------------
# App-specifc system build/test dependencies.
#
# Example: LDAP requires `libldap2-dev` to be apt-installed before the Python package.
# -------------------------------------------------------------------------------------
# --> Start safe to modify section

# Uncomment the lines below if you are apt-installing any package.
# RUN apt-get -y update && apt-get -y install \
#     libldap2-dev \
#     && rm -rf /var/lib/apt/lists/*

# --> Stop safe to modify section
# -------------------------------------------------------------------------------------
# Install Nautobot App
# -------------------------------------------------------------------------------------
# !!! USE CAUTION WHEN MODIFYING LINES BELOW

# Copy in the source code
WORKDIR /source

# Build args must be declared in each stage
ARG NAUTOBOT_VER
ARG PYTHON_VER

# Constrain the Nautobot version to NAUTOBOT_VER, fall back to installing from git branch if not available on PyPi
# In CI, this should be done outside of the Dockerfile to prevent cross-compile build failures
ARG CI
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    /root/.local/bin/uv sync --frozen --no-install-project --no-dev

# Then, add the rest of the project source code and install it
# Installing separately from its dependencies allows optimal layer caching
ADD . /source
RUN --mount=type=cache,target=/root/.cache/uv \
/root/.local/bin/uv sync --frozen --no-dev

COPY development/nautobot_config.py ${NAUTOBOT_ROOT}/nautobot_config.py
# !!! USE CAUTION WHEN MODIFYING LINES ABOVE
