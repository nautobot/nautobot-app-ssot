
ARG PYTHON_VER
ARG NAUTOBOT_VER
FROM ghcr.io/nautobot/nautobot-dev:${NAUTOBOT_VER}-py${PYTHON_VER}

ENV prometheus_multiproc_dir=/prom_cache

ARG NAUTOBOT_ROOT=/opt/nautobot

ENV NAUTOBOT_ROOT ${NAUTOBOT_ROOT}

WORKDIR $NAUTOBOT_ROOT

# Configure poetry
RUN poetry config virtualenvs.create false \
    && poetry config installer.parallel false

# -------------------------------------------------------------------------------------
# Install Nautobot Plugin
# -------------------------------------------------------------------------------------

WORKDIR /source

# Copy in only pyproject.toml/poetry.lock to help with caching this layer if no updates to dependencies
COPY poetry.lock pyproject.toml /source/

# --no-root declares not to install the project package since we're wanting to take advantage of caching dependency installation
# and the project is copied in and installed after this step
RUN poetry install --no-interaction --no-ansi --no-root

# Copy in the rest of the source code and install local Nautobot plugin
COPY . /source
RUN poetry install --no-interaction --no-ansi

COPY development/nautobot_config.py /opt/nautobot/nautobot_config.py
