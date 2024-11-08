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