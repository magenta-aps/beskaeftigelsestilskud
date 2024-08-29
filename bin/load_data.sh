# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

calculate_benefit="true"
count=$1

while [ $# -gt 0 ]; do
  case $1 in
    -h | --help)
      echo "Usage" 
      echo "---------------"
      echo "- ./`basename $0` [amount of lines to load]"
      echo "- ./`basename $0` [amount of lines to load] --calculate_benefit false"
      echo ""
      echo "Notes"
      echo "---------------"
      echo "- Requires 2022_a.csv and 2023_a.csv files to be present in /bf. "
      echo "- The files are attached to https://redmine.magenta.dk/issues/61082"
      echo "- Sorted files are here: https://redmine.magenta.dk/issues/61082#note-29"
      exit 0
      ;;
    -c | --calculate_benefit)
      # Calculate benefit for all citizens
      calculate_benefit=$2
      ;;
  esac
  shift
done

if [ "$count" == "" ]; then
  docker exec bf bash -c "python manage.py load_csv /app/2022_a.csv 2022"
  docker exec bf bash -c "python manage.py load_csv /app/2023_a.csv 2023"
else
  docker exec bf bash -c "python manage.py load_csv --count=$count /app/2022_a.csv 2022"
  docker exec bf bash -c "python manage.py load_csv --count=$count /app/2023_a.csv 2023"
fi

docker exec bf bash -c "python manage.py estimate_income 2022 --verbosity=2"
docker exec bf bash -c "python manage.py estimate_income 2023 --verbosity=2"


if [ "$calculate_benefit" == "true" ] ; then
    docker exec bf bash -c "python manage.py autoselect_estimation_engine"
    
    docker exec bf bash -c "python manage.py calculate_benefit 2022 --verbosity=2"
    docker exec bf bash -c "python manage.py calculate_benefit 2023 --verbosity=2"
fi
