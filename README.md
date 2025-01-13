# Beskaeftigelsestilskud

## Development

To start the project, `up` the docker containers using compose:

```bash
docker compose up -d
```

The system will start out empty. To load test-data into the database run the following command:

```bash
./bin/load_data.sh 200
```

**NOTE:** The `200`-argument is how many lines from the CSV files are loaded into the database.
If none is specified, all lines will be loaded, which can take awhile.

You can now access the web-ui at: http://localhost:8120/

### Accessing the database

The database can be accessed through CLI like so:

```bash
docker exec bf-db bash -c 'psql -U bf -c "SELECT * FROM common_user;"'
```

If we want access to the database through a program like PgAdmin, we need to portforward the `bf-db` container ports.
This can be done by creating a `docker-compose.override.yml`-file:

```yml
services:
    bf-db:
        ports:
        - "5432:5432"
```

### Import of U1A data from AKA-Selvbetjening

By default the host-domain for AKA-Selvbetjening is set to the test-server: https://akap.sullissivik.gl

if we want to interact with our local development version instead of the test-server, we need to connect
the `bf-web`-container to AKA-Selvbetjening's container network. This can be done by adding the following
to a `docker-compose.override.yml`-file:

```yml
networks:
  aka-selvbetjening_default:
    external: true

services:
  bf-web:
    networks:
      - aka-selvbetjening_default
    environment:
      AKAP_HOST: http://akap-web:8010
```

**NOTE:** This assumes you use the default setup for the aka-selvbetjening's project,
configured in the `docker-compose.yml`-file.

Now run the `import_u1a_data`-command:

```bash
docker exec bf-web python manage.py import_u1a_data --verbose
```

**IMPORTANT:** U1A data is used when running the `estimate_income`-command, which is done through the `load_data.sh`-script.
This means that if the `import_u1a_data`-command is executed after the `load_data.sh`-script, we need to run the
`estimate_income`-command again, so the newly imported U1A data avaialble to the calculations.

## Testing

To run the tests run
```
docker exec bf-web bash -c 'coverage run manage.py test ; coverage combine ; coverage report --show-missing'
```

To run tests only in a specific file run
```
docker exec bf-web bash -c 'coverage run manage.py test data_analysis.tests.test_views'
```

To run type checks run:

```
docker exec bf-web mypy --config ../mypy.ini bf/
```