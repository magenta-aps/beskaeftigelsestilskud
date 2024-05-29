#!/bin/bash

# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

set -e
MAKE_MIGRATIONS=${MAKE_MIGRATIONS:=false}
MIGRATE=${MIGRATE:=false}
TEST=${TEST:=false}
MAKEMESSAGES=${MAKEMESSAGES:=false}
COMPILEMESSAGES=${COMPILEMESSAGES:=false}
PULL_IDP_METADATA=${PULL_IDP_METADATA:=false}
CREATE_DUMMY_ADMIN=${CREATE_DUMMY_ADMIN:=false}

python manage.py wait_for_db

if [ "${MAKE_MIGRATIONS,,}" = true ]; then
  echo 'generating migrations'
  python manage.py makemigrations --no-input
fi
if [ "${MIGRATE,,}" = true ]; then
  echo 'running migrations'
  python manage.py migrate
fi

if [ "${CREATE_DUMMY_ADMIN}" = true ]; then
  echo 'creating superuser'
  DJANGO_SUPERUSER_PASSWORD=admin DJANGO_SUPERUSER_USERNAME=admin DJANGO_SUPERUSER_EMAIL=admin@admin.admin ./manage.py createsuperuser --noinput
fi

echo 'collecting static files'
python manage.py collectstatic --no-input --clear

python manage.py createcachetable
if [ "${PULL_IDP_METADATA,,}" = true ]; then
  echo "Updating metadata"
  python manage.py update_mitid_idp_metadata
fi

if [ "${MAKEMESSAGES,,}" = true ]; then
  echo 'making messages'
  python manage.py makemessages --locale=kl --no-obsolete --add-location file
  python manage.py makemessages --locale=da --no-obsolete --add-location file
fi
if [ "${COMPILEMESSAGES,,}" = true ]; then
  echo 'compiling messages'
  python manage.py compilemessages --locale=kl
  python manage.py compilemessages --locale=da
fi
if [ "${TEST,,}" = true ]; then
    echo 'running tests'
    coverage run manage.py test
    coverage combine
    coverage report --show-missing
  fi

exec "$@"
