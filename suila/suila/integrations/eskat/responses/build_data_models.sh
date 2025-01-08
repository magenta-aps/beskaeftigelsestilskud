#!/usr/bin/env bash
set -eux
cd ./suila/integrations/eskat/responses
datamodel-codegen \
    --input ./openapi_spec.yaml \
    --input-file-type openapi \
    --output ./data_models.py \
    --output-model-type dataclasses.dataclass \
    --base-class "" \
    --target-python-version=3.12 \
    --snake-case-field \
    --wrap-string-literal \
    --use-double-quotes \
    --use-schema-description \
    --use-standard-collections \
    --use-union-operator \
    --disable-appending-item-suffix \
    --collapse-root-models \
    --reuse-model \
    --allow-population-by-field-name \
    --strict-nullable
