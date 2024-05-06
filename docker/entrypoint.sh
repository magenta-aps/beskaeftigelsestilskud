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

python manage.py wait_for_db

if [ "${MAKE_MIGRATIONS,,}" = true ]; then
  echo 'generating migrations'
  python manage.py makemigrations --no-input
fi
if [ "${MIGRATE,,}" = true ]; then
  echo 'running migrations'
  python manage.py migrate
fi

if [ "${TEST,,}" = true ]; then
  echo 'running tests'
  coverage run manage.py test
#  coverage combine
#  coverage report --show-missing
fi
if [ "${MAKEMESSAGES,,}" = true ]; then
  echo 'making messages'
  python manage.py makemessages --locale=kl --no-obsolete --add-location file
  python manage.py makemessages --locale=da --no-obsolete --add-location file
  python manage.py makemessages --locale=en --no-obsolete --add-location file
fi
if [ "${COMPILEMESSAGES,,}" = true ]; then
  echo 'compiling messages'
  python manage.py compilemessages --locale=kl
  python manage.py compilemessages --locale=da
  python manage.py compilemessages --locale=en
fi

exec "$@"
