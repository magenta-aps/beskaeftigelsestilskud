# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

FROM python:3.12
ENV PYTHONUNBUFFERED=1
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN mkdir /app && \
    mkdir -p /var/cache/bf && \
    mkdir /static && \
    #gid/uid from salt
    groupadd -g 75170 -r bf && \
    groupadd -g 75100 -r certificate_exporter && \
    useradd -u 75170 --no-log-init -r -g bf -G certificate_exporter bf && \
    chown -R bf:bf /static && \
    chown -R bf:bf /var/cache/bf && \
    chmod a+w /var/cache/bf

# hadolint ignore=DL3008
RUN apt-get update && \
    apt-get install -y --no-install-recommends gettext python3-distutils libxmlsec1-dev xmlsec1 libssl-dev libsasl2-dev && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
COPY mypy.ini /app/mypy.ini

RUN pip install --no-cache-dir -r /app/requirements.txt

ARG COMMIT_TAG
ENV COMMIT_TAG=${COMMIT_TAG:-HEAD}

USER bf
COPY ./docker/entrypoint.sh /entrypoint.sh
COPY --chown=bf:bf ./bf /app
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
WORKDIR /app
CMD ["gunicorn","-b","0.0.0.0:8000","project.wsgi:application","-w","4","--timeout","120","--error-logfile","-","--capture-output"]
