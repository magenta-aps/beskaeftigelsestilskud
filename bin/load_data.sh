# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0


if [ "$1" == "-h" ]; then
  echo "Usage: bash `basename $0` [amount of lines to load]"
  echo "Note: Requires 2022_a.csv and 2023_a.csv files to be present in /bf. The files are attached to https://redmine.magenta.dk/issues/61082"
  exit 0
fi


if [ "$1" == "" ]; then
  docker exec bf bash -c "python manage.py load_csv /app/2022_a.csv 2022"
  docker exec bf bash -c "python manage.py load_csv /app/2023_a.csv 2023"
else
  docker exec bf bash -c "python manage.py load_csv --count=$1 /app/2022_a.csv 2022"
  docker exec bf bash -c "python manage.py load_csv --count=$1 /app/2023_a.csv 2023"
fi

docker exec bf bash -c "python manage.py estimate_income 2022"
docker exec bf bash -c "python manage.py estimate_income 2023"
