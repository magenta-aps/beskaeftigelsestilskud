# syntax=docker/dockerfile:1
# Keep the syntax directive above on line 1; it is ignored if any comment precedes it.

# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

FROM python:3.14
ENV SUPERCRONIC_URL=https://github.com/aptible/supercronic/releases/download/v0.2.27/supercronic-linux-amd64 \
    SUPERCRONIC=supercronic-linux-amd64 \
    SUPERCRONIC_SHA1SUM=7dadd4ac827e7bd60b386414dfefc898ae5b6c63\
    PYTHONUNBUFFERED=1
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN mkdir /app && \
    mkdir -p /var/cache/idp && \
    mkdir -p /upload/note && \
    mkdir -p /upload/eboks && \
    mkdir -p /upload/prisme && \
    mkdir /static && \
    #gid/uid from salt
    groupadd -g 75180 -r suila && \
    groupadd -g 75100 -r certificate_exporter && \
    useradd -u 75180 --no-log-init -r -g suila -G certificate_exporter suila && \
    chown -R suila:suila /static && \
    chown -R suila:suila /var/cache/idp && \
    chown -R suila:suila /upload && \
    chmod a+w /var/cache/idp

# Font cache for pdf generation
RUN mkdir -p /home/suila/.cache/fontconfig && \
    chown -R suila /home/suila/.cache/fontconfig

# supercronic
RUN curl -fsSLO "$SUPERCRONIC_URL" && \
    echo "${SUPERCRONIC_SHA1SUM}  ${SUPERCRONIC}" | sha1sum -c - && \
    chmod +x "$SUPERCRONIC" && \
    mv "$SUPERCRONIC" "/usr/local/bin/${SUPERCRONIC}" && \
    ln -s "/usr/local/bin/${SUPERCRONIC}" /usr/local/bin/supercronic

# hadolint ignore=DL3008
RUN sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list' && \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /etc/apt/trusted.gpg.d/postgresql.gpg && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        gettext graphviz libxmlsec1-dev xmlsec1 libssl-dev libsasl2-dev postgresql-client-common postgresql-client-16 logrotate && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

# Keep pip's http/wheel cache in a build cache mount instead of throwing it away.
# Anything that has to be built from source (or downloaded again) is then reused
# by later builds, so editing requirements.txt no longer costs a full rebuild.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r /app/requirements.txt

ARG COMMIT_TAG
ENV COMMIT_TAG=${COMMIT_TAG:-HEAD}

COPY mypy.ini /app/mypy.ini
COPY ./docker/entrypoint.sh /entrypoint.sh
COPY --chown=suila:suila ./suila /app
RUN chown suila:suila /app
# hadolint ignore=DL3066
USER suila
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
WORKDIR /app
RUN django-admin compilemessages --locale=da --locale=kl --locale=en --verbosity=0

CMD ["gunicorn","-b","0.0.0.0:8000","project.wsgi:application","-w","4","--timeout","120","--error-logfile","-","--capture-output"]
