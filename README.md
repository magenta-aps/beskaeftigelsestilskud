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

## Testing

To run the tests run
```
docker exec bf bash -c 'coverage run manage.py test ; coverage combine ; coverage report --show-missing'
```

To run tests only in a specific file run
```
docker exec bf bash -c 'coverage run manage.py test data_analysis.tests.test_views'
```

To run type checks run:

```
docker exec bf mypy --config ../mypy.ini bf/
```