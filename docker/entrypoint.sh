#!/bin/bash

# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

set -e
MAKE_MIGRATIONS=${MAKE_MIGRATIONS:=false}
MIGRATE=${MIGRATE:=true}
TEST=${TEST:=false}
MAKEMESSAGES=${MAKEMESSAGES:=false}
PULL_IDP_METADATA=${PULL_IDP_METADATA:=false}
CREATE_DUMMY_ADMIN=${CREATE_DUMMY_ADMIN:=false}
LOAD_CALCULATION_METHOD=${LOAD_CALCULATION_METHOD:=true}

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
  python manage.py create_user admin admin -S
fi



python manage.py createcachetable
if [ "${PULL_IDP_METADATA,,}" = true ]; then
  echo "Updating metadata"
  python manage.py update_mitid_idp_metadata
fi

if [ "${LOAD_CALCULATION_METHOD}" = true ]; then
  echo "Loading calculation method"
  python manage.py load_dummy_calculation_method
fi

if [ "${MAKEMESSAGES,,}" = true ]; then
  echo 'making messages'
  python manage.py makemessages --locale=kl --no-obsolete --add-location file
  python manage.py makemessages --locale=da --no-obsolete --add-location file
fi
if [ "${TEST,,}" = true ]; then
    echo 'running tests'
    coverage run manage.py test
    coverage combine
    coverage report --show-missing
  fi

exec "$@"
