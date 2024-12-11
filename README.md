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
docker exec suila-db bash -c 'psql -U suila -c "SELECT * FROM common_user;"'
```

If we want access to the database through a program like PgAdmin, we need to portforward the `suila-db` container ports.
This can be done by creating a `docker-compose.override.yml`-file:

```yml
services:
    suila-db:
        ports:
        - "5432:5432"
```

## Testing

To run the tests run
```
docker exec suila-web bash -c 'coverage run manage.py test ; coverage combine ; coverage report --show-missing'
```

To run tests only in a specific file run
```
docker exec suila-web bash -c 'coverage run manage.py test data_analysis.tests.test_views'
```

To run type checks run:

```
docker exec suila-web mypy --config ../mypy.ini suila/
```

# Development

## First time running

**NOTE:** The first time `docker compose up -d` is invoked, an error from the `suila-cron`-container can occur. This happens because the container uses the image `suila:latest`, which is build by the `suila`-container in this project. The `suila-cron`-container fails since we have never build the `suila`-container yet. To "fix" this, just `down` all containers and `up` them again a second time, since the `suila`-container has now been build.

## Running in network mode "bridge"

Below `docker-compose.override.yml` can be used to run the project in `network_mode: "bridge"` on OS'es which don't support `network_mode: "host"` (Windows and MacOS).

The configuration replaces all host-domains, set to `localhost`, with `host.docker.internal`, which is a "magic" domain used inside docker:

```yml
services:
  suila:
    network_mode: "bridge"
    ports:
      - "8000:8000"
    environment:
      POSTGRES_HOST: host.docker.internal
      EMAIL_HOST: host.docker.internal
      PRISME_HOST: host.docker.internal
      SAML_SP_ENTITY_ID: http://host.docker.internal:8000/mitid/saml/metadata/
      SAML_SP_LOGIN_CALLBACK_URI: http://host.docker.internal:8000/mitid/login/callback/
      SAML_SP_LOGOUT_CALLBACK_URI: http://host.docker.internal:8000/mitid/logout/callback/
      SAML_IDP_LOGIN_URI: http://host.docker.internal:8080/simplesaml/saml2/idp/SSOService.php
      SAML_IDP_LOGOUT_URI: http://host.docker.internal:8080/simplesaml/saml2/idp/SingleLogoutService.php
      SAML_IDP_METADATA: http://host.docker.internal:8080/simplesaml/saml2/idp/metadata.php

  suila-db:
    network_mode: "bridge"
    ports:
      - "5432:5432"

  suila-mailhog:
    network_mode: "bridge"
    ports:
      - "1025:1025"
      - "8025:8025"

  suila-test-idp:
    network_mode: "bridge"
    ports:
      - "8080:8080"
    environment:
      SIMPLESAMLPHP_SP_ENTITY_ID: http://host.docker.internal:8000/mitid/saml/metadata/
      SIMPLESAMLPHP_SP_ASSERTION_CONSUMER_SERVICE: http://host.docker.internal:8000/mitid/login/callback/
      SIMPLESAMLPHP_SP_SINGLE_LOGOUT_SERVICE: http://host.docker.internal:8000/mitid/logout/callback/

  suila-sftp:
    network_mode: "bridge"
    ports:
      - "22:22"

```

**Problems:**

The `suila-test-idp`-container does not currently work with this setup, due to it using environment-variables both client- & server-side (`SAML_IDP_LOGIN_URI`) which makes us unable to redirect correctly in each scope. However, since the project is mostly CLI and run in a cron-container + have normal django authentication enabled, this should only be a problem if you are trying to do something with MitID.
