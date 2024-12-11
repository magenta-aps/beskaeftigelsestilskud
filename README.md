# Beskaeftigelsestilskud

# Testing
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

# Development

## First time running

**NOTE:** The first time `docker compose up -d` is invoked, an error from the `bf-cron`-container can occur. This happens because the container uses the image `bf:latest`, which is build by the `bf`-container in this project. The `bf-cron`-container fails since we have never build the `bf`-container yet. To "fix" this, just `down` all containers and `up` them again a second time, since the `bf`-container has now been build.

## Running in network mode "bridge"

Below `docker-compose.override.yml` can be used to run the project in `network_mode: "bridge"` on OS'es which don't support `network_mode: "host"` (Windows and MacOS).

The configuration replaces all host-domains, set to `localhost`, with `host.docker.internal`, which is a "magic" domain used inside docker:

```yml
services:
  bf:
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

  bf-db:
    network_mode: "bridge"
    ports:
      - "5432:5432"

  bf-mailhog:
    network_mode: "bridge"
    ports:
      - "1025:1025"
      - "8025:8025"

  bf-test-idp:
    network_mode: "bridge"
    ports:
      - "8080:8080"
    environment:
      SIMPLESAMLPHP_SP_ENTITY_ID: http://host.docker.internal:8000/mitid/saml/metadata/
      SIMPLESAMLPHP_SP_ASSERTION_CONSUMER_SERVICE: http://host.docker.internal:8000/mitid/login/callback/
      SIMPLESAMLPHP_SP_SINGLE_LOGOUT_SERVICE: http://host.docker.internal:8000/mitid/logout/callback/

  bf-sftp:
    network_mode: "bridge"
    ports:
      - "22:22"

```

**Problems:**

The `bf-test-idp`-container does not currently work with this setup, due to it using environment-variables both client- & server-side (`SAML_IDP_LOGIN_URI`) which makes us unable to redirect correctly in each scope. However, since the project is mostly CLI and run in a cron-container + have normal django authentication enabled, this should only be a problem if you are trying to do something with MitID.