# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

FROM python:3.12
ENV SUPERCRONIC_URL=https://github.com/aptible/supercronic/releases/download/v0.2.27/supercronic-linux-amd64 \
    SUPERCRONIC=supercronic-linux-amd64 \
    SUPERCRONIC_SHA1SUM=7dadd4ac827e7bd60b386414dfefc898ae5b6c63\
    PYTHONUNBUFFERED=1
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN mkdir /app && \
    mkdir -p /var/cache/bf && \
    mkdir /static && \
    #gid/uid from salt
    groupadd -g 75180 -r bf && \
    groupadd -g 75100 -r certificate_exporter && \
    useradd -u 75180 --no-log-init -r -g bf -G certificate_exporter bf && \
    chown -R bf:bf /static && \
    chown -R bf:bf /var/cache/bf && \
    chmod a+w /var/cache/bf

# supercronic
RUN curl -fsSLO "$SUPERCRONIC_URL" && \
    echo "${SUPERCRONIC_SHA1SUM}  ${SUPERCRONIC}" | sha1sum -c - && \
    chmod +x "$SUPERCRONIC" && \
    mv "$SUPERCRONIC" "/usr/local/bin/${SUPERCRONIC}" && \
    ln -s "/usr/local/bin/${SUPERCRONIC}" /usr/local/bin/supercronic

# hadolint ignore=DL3008
RUN apt-get update && \
    apt-get install -y --no-install-recommends gettext python3-distutils libxmlsec1-dev xmlsec1 libssl-dev libsasl2-dev && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
COPY mypy.ini /app/mypy.ini

RUN pip install --no-cache-dir -r /app/requirements.txt

ARG COMMIT_TAG
ENV COMMIT_TAG=${COMMIT_TAG:-HEAD}

COPY ./docker/entrypoint.sh /entrypoint.sh
COPY --chown=bf:bf ./bf /app
RUN chown bf:bf /app
USER bf
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
WORKDIR /app
RUN django-admin compilemessages

# temporary use of dev env to make manage.py work
COPY --chown=bf:bf ./dev-environment/bf.env bf.env
# hadolint ignore=SC1091
RUN set -a && \
    source bf.env && \
    set +a && \
    python manage.py collectstatic --no-input --clear && \
    rm bf.env

CMD ["gunicorn","-b","0.0.0.0:8000","project.wsgi:application","-w","4","--timeout","120","--error-logfile","-","--capture-output"]
