# Beskaeftigelsestilskud

## Development

To start the project, `up` the docker containers using compose:

```bash
docker compose up -d
```

You can then log in with one of the following:

| Username         | Password         | Description                         |
|------------------|------------------|-------------------------------------|
| `admin`          | `admin`          | Admin poweruser                     |
| `anders`         | `anders`         | Citizen user without a person-year  |
| `bruce`          | `bruce`          | Citizen user with a person-year     |
| `borgerservice`  | `borgerservice`  | Citizen-service user                |
| `skattestyrelsen`| `skattestyrelsen`| Tax-department user                 |


## Loading data
The system will start out with some dummy data. To load real test-data into the
database, you can use the eskat-api:

```
docker exec -it suila-web-private python manage.py load_eskat 2025 monthlyincome
```

See `suila/suila/integrations/eskat/README.md` for details regarding the eskat
integration.

You can now estimate annual income for the data which you loaded from eskat:

```bash
docker exec suila-web-private python manage.py estimate_income
```

And calculate Suila tapit according to the estimated incomes:
```bash
docker exec suila-web-private python manage.py calculate_benefit 2025
```

You can now access the web-ui at: http://localhost:8120/

### Accessing the database

The database can be accessed through CLI like so:

```bash
docker exec suila-db bash -c 'psql -U bf -c "SELECT * FROM common_user;"'
```

If we want access to the database through a program like PgAdmin, we need to portforward the `suila-db` container ports.
This can be done by creating a `docker-compose.override.yml`-file:

```yml
services:
    suila-db:
        ports:
        - "5432:5432"
```

### Import of U1A data from AKA-Selvbetjening

By default the host-domain for AKA-Selvbetjening is set to the prod-server, `https://akap.sullissivik.gl`, but our `./dev-environment/suila.env`-settings will set this to `https://test.akap.sullissivik.gl`.

if we want to interact with our local development version instead of the test-server, we need to connect
the `suila-web`-container to AKA-Selvbetjening's container network. This can be done by adding the following
to a `docker-compose.override.yml`-file:

```yml
networks:
  aka-selvbetjening_default:
    external: true

services:
  suila-web:
    networks:
      - aka-selvbetjening_default
    environment:
      AKAP_HOST: http://akap-web:8010
```

**NOTE:** This assumes you use the default setup for the aka-selvbetjening's project,
configured in the `docker-compose.yml`-file.

Now run the `import_u1a_data`-command:

```bash
docker exec suila-web python manage.py import_u1a_data --verbose
```

**IMPORTANT:** U1A data is used when running the `estimate_income`-command.
This means that if the `import_u1a_data`-command is executed after the `estimate_income`-command, we need to run the
`estimate_income`-command again.

### Export to Prisme

To send data to Prisme, use the following management command: `export_benefits_to_prisme`.

If you are working with test data from the CSV files, some minor configurations need to be
made for the command to work in a development environment:

* Edit `suila/suila/management/commands/load_prisme_account_aliases.py` and set `TAX_YEARS = range(2020, 2031)`
  * This ensures that `PrismeAccountAlias` rows are created for the years covered by the CSV test data.
* Run the `load_prisme_account_aliases`-command
  * ```bash
    docker exec suila-web python manage.py load_prisme_account_aliases
    ```
* Update all rows in the `suila_person` table with a `location_code` that exists in the `suila_prismeaccountalias` table (column `tax_municipality_location_code`):
  * ```bash
    docker exec suila-db psql -U suila -c 'UPDATE suila_person SET location_code = 961'
    ```
  * **Note:** The available `location_code` values can be found in `suila/suila/management/commands/load_prisme_account_aliases.py`.

Once these steps are complete, you can run the `export_benefits_to_prisme` command:

```bash
docker exec suila-web python manage.py export_benefits_to_prisme --year=2023 --month=01
```

Note: The `export_benefits_to_prisme` command requires that the `calculate_benefit` command has been executed beforehand for the
year you want to export data to Prisme.

## Testing

To run the tests run
```shell
docker exec suila-web-private bash -c 'coverage run manage.py test --parallel ; coverage combine ; coverage report --show-missing'
```

To run tests only in a specific file run
```shell
docker exec suila-web-private bash -c 'coverage run manage.py test data_analysis.tests.test_views'
```

To run type checks run:

```shell
docker exec suila-web-private mypy --config ../mypy.ini suila/
```

