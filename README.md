# Beskaeftigelsestilskud

# Testing
To run the tests run
```
docker exec bf bash -c 'coverage run manage.py test --parallel 4 ; coverage combine ; coverage report --show-missing'
```

To run tests only in a specific file run
```
docker exec bf bash -c 'coverage run manage.py test data_analysis.tests.test_views'
``
