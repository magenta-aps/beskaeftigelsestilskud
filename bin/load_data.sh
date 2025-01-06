# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

calculate_benefit="true"
count=$1
profile_flag=""

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
      echo "- Requires a_og_b_202[0,1,2,3].csv files to be present in /app/data/ in the container."
      echo "- Requires forskud_202[0,1,2,3].csv files to be present in /app/data/ in the container."
      echo "- The files are attached to https://redmine.magenta.dk/issues/61921"
      echo "- These files are sorted by CPR number."
      exit 0
      ;;
    -c | --calculate_benefit)
      # Calculate benefit for all citizens
      calculate_benefit=$2
      ;;
    --profile)
      # Display profiler results
      profile_flag="--profile"
      ;;
  esac
  shift
done

if [ "$count" == "" ]; then
  count_arg=""
else
  count_arg="--count=$count"
fi

docker exec bf-web bash -c "python manage.py load_csv $count_arg /app/data/a_og_b_2020.csv income 2020 $profile_flag"
docker exec bf-web bash -c "python manage.py load_csv $count_arg /app/data/a_og_b_2021.csv income 2021 $profile_flag"
docker exec bf-web bash -c "python manage.py load_csv $count_arg /app/data/a_og_b_2022.csv income 2022 $profile_flag"
docker exec bf-web bash -c "python manage.py load_csv $count_arg /app/data/a_og_b_2023.csv income 2023 $profile_flag"

docker exec bf-web bash -c "python manage.py load_csv $count_arg /app/data/forskud_2020.csv assessment 2020 $profile_flag"
docker exec bf-web bash -c "python manage.py load_csv $count_arg /app/data/forskud_2021.csv assessment 2021 $profile_flag"
docker exec bf-web bash -c "python manage.py load_csv $count_arg /app/data/forskud_2022.csv assessment 2022 $profile_flag"
docker exec bf-web bash -c "python manage.py load_csv $count_arg /app/data/forskud_2023.csv assessment 2023 $profile_flag"

docker exec bf-web bash -c "python manage.py load_csv $count_arg /app/data/ligning_2020.csv final_settlement 2020 $profile_flag"
docker exec bf-web bash -c "python manage.py load_csv $count_arg /app/data/ligning_2021.csv final_settlement 2021 $profile_flag"
docker exec bf-web bash -c "python manage.py load_csv $count_arg /app/data/ligning_2022.csv final_settlement 2022 $profile_flag"
docker exec bf-web bash -c "python manage.py load_csv $count_arg /app/data/ligning_2023.csv final_settlement 2023 $profile_flag"


docker exec bf-web bash -c "python manage.py estimate_income --verbosity=2 $profile_flag"

if [ "$calculate_benefit" == "true" ] ; then
    docker exec bf-web bash -c "python manage.py calculate_stability_score 2020 --verbosity=2 $profile_flag"
    docker exec bf-web bash -c "python manage.py calculate_stability_score 2021 --verbosity=2 $profile_flag"
    docker exec bf-web bash -c "python manage.py calculate_stability_score 2022 --verbosity=2 $profile_flag"
    docker exec bf-web bash -c "python manage.py calculate_stability_score 2023 --verbosity=2 $profile_flag"

    docker exec bf-web bash -c "python manage.py calculate_benefit 2020 --verbosity=2 $profile_flag"
    docker exec bf-web bash -c "python manage.py autoselect_estimation_engine 2021 --verbosity=2 $profile_flag"
    docker exec bf-web bash -c "python manage.py calculate_benefit 2021 --verbosity=2 $profile_flag"
    docker exec bf-web bash -c "python manage.py autoselect_estimation_engine 2022 --verbosity=2 $profile_flag"
    docker exec bf-web bash -c "python manage.py calculate_benefit 2022 --verbosity=2 $profile_flag"
    docker exec bf-web bash -c "python manage.py autoselect_estimation_engine 2023 --verbosity=2 $profile_flag"
    docker exec bf-web bash -c "python manage.py calculate_benefit 2023 --verbosity=2 $profile_flag"
fi
