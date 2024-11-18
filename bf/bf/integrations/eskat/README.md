# Eskat integration

For at køre eskat-integration kommandoer i udviklingsmiljø skal man oprette en
docker-compose.override.yml fil:

```
services:
  bf:
    environment:
      - ESKAT_BASE_URL=https://eskattest/eTaxCommonDataApi
      - ESKAT_USERNAME=<username>
      - ESKAT_PASSWORD=<password>
      - ESKAT_VERIFY=/app/knno_ca.cert
```

Hvor `<username>` og `<password>` er de samme som man bruger for at forbinde til
Skattestyrelsens VPN. `knno_ca.cert` ligger i kas-test secrets i salt-repoet.
Man bør også sætte `eskattest` til at pege på 10.240.79.31 i sin `/etc/hosts`.

Man kan køre kommandoer med docker-compose. For eksempel:

```
docker exec -it bf python manage.py load_eskat 2022 taxinformation
```