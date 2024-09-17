import os

PRISME = {
    "host": os.environ["PRISME_HOST"],
    "port": int(os.environ.get("PRISME_PORT") or 22),
    "username": os.environ["PRISME_USER"],
    "password": os.environ["PRISME_PASSWORD"],
    "known_hosts": os.environ.get("PRISME_KNOWN_HOSTS") or None,
    "dirs": {
        "production": os.environ["PRISME_PROD_PATH"],
        "development": os.environ["PRISME_TEST_PATH"],
    },
    "destinations": {
        # Our prod server can use both prod and dev on the Prisme server
        "production": ["production", "development"],
        # Our dev server can only use dev on the Prisme server
        "development": ["development"],
        # Our staging server can only use dev on the Prisme server
        "staging": ["development"],
    },
}