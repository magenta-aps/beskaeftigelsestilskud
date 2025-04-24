#!/bin/bash

# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

set -e
MAKE_MIGRATIONS=${MAKE_MIGRATIONS:=false}
MIGRATE=${MIGRATE:=false}
TEST=${TEST:=false}
MAKEMESSAGES=${MAKEMESSAGES:=false}
PULL_IDP_METADATA=${PULL_IDP_METADATA:=false}
CREATE_API_GROUP=${CREATE_API_GROUP:=false}
CREATE_USER_GROUPS=${CREATE_USER_GROUPS:=false}
CREATE_DUMMY_ADMIN=${CREATE_DUMMY_ADMIN:=false}
CREATE_DUMMY_USERS=${CREATE_DUMMY_USERS:=false}
CREATE_API_USER=${CREATE_API_USER:=false}
LOAD_CALCULATION_METHOD=${LOAD_CALCULATION_METHOD:=false}
LOAD_PRISME_ACCOUNT_ALIASES=${LOAD_PRISME_ACCOUNT_ALIASES:=false}

python manage.py wait_for_db

python manage.py collectstatic --no-input --clear
python manage.py compress --force

if [ "${MAKE_MIGRATIONS,,}" = true ]; then
  echo 'generating migrations'
  python manage.py makemigrations --no-input
fi
if [ "${MIGRATE,,}" = true ]; then
  echo 'running migrations'
  python manage.py migrate
fi

if [ "${CREATE_API_GROUP,,}" = true ]; then
  echo 'creating api group'
  python manage.py create_api_group api
fi

if [ "${CREATE_USER_GROUPS,,}" = true ]; then
  echo 'creating api group'
  python manage.py create_groups
fi
if [ "${CREATE_DUMMY_ADMIN,,}" = true ]; then
  echo 'creating superuser'
  python manage.py create_user admin admin --is_superuser
fi
if [ "${CREATE_DUMMY_USERS,,}" = true ]; then
  echo 'creating borgerservice user'
  python manage.py create_user borgerservice borgerservice -g Borgerservice
  echo 'creating skattestyrelsen user'
  python manage.py create_user skattestyrelsen skattestyrelsen -g Skattestyrelsen

  echo 'creating dummy citizen users and generating data'
  python manage.py create_dummy_data
fi

if [ "${CREATE_API_USER,,}" = true ]; then
  echo 'creating api user'
  python manage.py create_user rest rest --cert-subject "${API_USER_SUBJECT}" --groups api
fi

python manage.py createcachetable
if [ "${PULL_IDP_METADATA,,}" = true ]; then
  echo "Updating metadata"
  python manage.py update_mitid_idp_metadata
fi

if [ "${LOAD_CALCULATION_METHOD,,}" = true ]; then
  echo "Loading calculation method"
  python manage.py load_dummy_calculation_method
fi

if [ "${LOAD_PRISME_ACCOUNT_ALIASES,,}" = true ]; then
  echo "Loading prisme account aliases"
  python manage.py load_prisme_account_aliases
fi

if [ "${MAKEMESSAGES,,}" = true ]; then
  echo 'making messages'
  python manage.py make_messages --locale=kl --locale=da --no-obsolete --add-location file
  python manage.py make_messages --locale=kl --locale=da --no-obsolete --add-location file --domain djangojs
  python manage.py compilemessages --locale=da --locale=kl --verbosity=2
fi
if [ "${TEST,,}" = true ]; then
    echo 'running tests'
    coverage run manage.py test
    coverage combine
    coverage report --show-missing
  fi

exec "$@"
